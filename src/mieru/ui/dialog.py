"""The mieru window: English word -> Japanese candidate -> picture -> new note."""

from __future__ import annotations

import html
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath
from urllib.parse import urlparse

import requests
from anki.notes import NoteFieldsCheckResult
from anki.utils import tmpfile
from aqt.deckchooser import DeckChooser
from aqt.main import AnkiQt
from aqt.operations import QueryOp
from aqt.operations.note import add_note
from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPixmap,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from aqt.sound import av_player
from aqt.utils import (
    askUser,
    disable_help_button,
    restoreGeom,
    saveGeom,
    showWarning,
    tooltip,
)

from ..core import audio, dictionary, images
from ..core.dictionary import Candidate
from ..core.furigana import to_anki_furigana
from ..core.images import SOURCES, ImageResult, InvalidApiKeyError, Source
from .note_type import (
    AUDIO_FIELD,
    ENGLISH_FIELD,
    IMAGE_FIELD,
    WORD_FIELD,
    ensure_note_type,
)
from .widgets import CandidateList, PictureGrid

_GEOMETRY_KEY = "mieru"
_DEFAULT_WIDTH = 760
_ROW_SPACING = 6
_SECTION_SPACING = 16
_TEXT_MARGIN = 4
_THUMBNAIL_DOWNLOADS = 8
_MISSING_KEY_MESSAGE = (
    "To choose pictures, add a free Pixabay API key in "
    'Tools › Add-ons › mieru › Config (get one at <a href="https://pixabay.com/api/docs/">'
    "pixabay.com/api/docs</a>)."
)


class MieruDialog(QDialog):
    """Kept alive and reused across openings, so late network results land on a
    hidden window (and are discarded by the query check) instead of a deleted one."""

    def __init__(self, mw: AnkiQt) -> None:
        super().__init__(mw)
        self.mw = mw
        self._query = ""
        self._candidates: list[Candidate] = []
        self._candidate: Candidate | None = None
        self._audio: bytes | None = None
        self._image_query = ""
        self._images: list[ImageResult] = []
        self._setup_ui()
        restoreGeom(self, _GEOMETRY_KEY, default_size=(_DEFAULT_WIDTH, self.sizeHint().height()))

    def _setup_ui(self) -> None:
        self.setWindowTitle("mieru")
        disable_help_button(self)
        layout = QVBoxLayout(self)
        layout.setSpacing(_ROW_SPACING)

        deck_row = QWidget()
        self._deck_chooser = DeckChooser(self.mw, deck_row)
        layout.addWidget(deck_row)

        search_row = QHBoxLayout()
        self._query_input = QLineEdit()
        self._query_input.setPlaceholderText("English word, e.g. dog")
        self._query_input.setTextMargins(_TEXT_MARGIN, 0, _TEXT_MARGIN, 0)
        self._query_input.returnPressed.connect(self._search)
        search_button = QPushButton("Search")
        search_button.clicked.connect(self._search)
        search_row.addWidget(self._query_input)
        search_row.addWidget(search_button)
        layout.addLayout(search_row)
        layout.addSpacing(_SECTION_SPACING)

        word_row = QHBoxLayout()
        self._play_button = QPushButton("▶ Play")
        self._play_button.clicked.connect(self._play_audio)
        word_row.addWidget(QLabel("<b>Japanese word</b>"), stretch=1)
        word_row.addWidget(self._play_button)
        layout.addLayout(word_row)
        self._candidate_list = CandidateList()
        self._candidate_list.currentRowChanged.connect(self._on_candidate_changed)
        layout.addWidget(self._candidate_list, stretch=1)
        layout.addSpacing(_SECTION_SPACING)

        self._images_label = QLabel()
        self._images_label.setOpenExternalLinks(True)
        self._images_label.setWordWrap(True)
        layout.addWidget(self._images_label)
        image_search_row = QHBoxLayout()
        self._image_query_input = QLineEdit()
        self._image_query_input.setPlaceholderText("Picture search term")
        self._image_query_input.setTextMargins(_TEXT_MARGIN, 0, _TEXT_MARGIN, 0)
        self._image_query_input.returnPressed.connect(self._search_images)
        image_search_button = QPushButton("Search")
        image_search_button.clicked.connect(self._search_images)
        image_search_row.addWidget(self._image_query_input)
        image_search_row.addWidget(image_search_button)
        layout.addLayout(image_search_row)
        self._image_list = PictureGrid()
        self._image_list.currentRowChanged.connect(lambda _row: self._update_add_button())
        layout.addWidget(self._image_list, stretch=3)
        layout.addSpacing(_SECTION_SPACING)

        buttons = QDialogButtonBox()
        add_button = buttons.addButton("Add", QDialogButtonBox.ButtonRole.AcceptRole)
        assert add_button is not None
        add_button.clicked.connect(self._add)
        self._add_button = add_button
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._reset()

    def _reset(self) -> None:
        self._query = ""
        self._candidates = []
        self._candidate = None
        self._audio = None
        self._candidate_list.clear()
        self._play_button.setEnabled(False)
        self._image_query_input.clear()
        self._clear_images()
        self._images_label.setText(_images_label(self._configured_sources()))
        self._query_input.setFocus()
        self._query_input.selectAll()

    # Search: candidates come from the English word; pictures from their own
    # search term, which starts as the English word and can be refined.

    def _search(self) -> None:
        query = self._query_input.text().strip()
        if not query:
            return
        self._reset()
        self._query = query

        QueryOp(
            parent=self,
            op=lambda _col: dictionary.search(query),
            success=lambda candidates: self._show_candidates(query, candidates),
        ).without_collection().with_progress("Looking up Japanese words…").failure(
            self._show_network_error
        ).run_in_background()

        self._image_query_input.setText(query)
        self._search_images()

    def _search_images(self) -> None:
        image_query = self._image_query_input.text().strip()
        if not image_query:
            return
        self._clear_images()
        self._image_query = image_query
        sources = self._configured_sources()
        self._images_label.setText(_images_label(sources))
        for source, api_key in sources:
            self._search_source(source, api_key, image_query)

    def _search_source(self, source: Source, api_key: str, image_query: str) -> None:
        QueryOp(
            parent=self,
            op=lambda _col: _search_with_thumbnails(source, api_key, image_query),
            success=lambda found: self._show_images(source, image_query, found),
        ).without_collection().failure(self._on_image_search_failed).run_in_background()

    def _clear_images(self) -> None:
        self._image_query = ""
        self._images = []
        self._image_list.clear()
        self._update_add_button()

    def _show_candidates(self, query: str, candidates: list[Candidate]) -> None:
        if query != self._query:
            return
        if not candidates:
            tooltip(f"No Japanese words found for “{query}”.", parent=self)
            return
        self._candidates = candidates
        for candidate in candidates:
            self._candidate_list.add_candidate(candidate)
        self._candidate_list.setCurrentRow(0)

    def _show_images(
        self, source: Source, image_query: str, found: list[tuple[ImageResult, bytes | None]]
    ) -> None:
        if image_query != self._image_query:
            return
        if not found:
            tooltip(f"No pictures found on {source.name} for “{image_query}”.", parent=self)
        for result, thumbnail in found:
            pixmap = QPixmap()
            if thumbnail is not None:
                pixmap.loadFromData(thumbnail)
            self._image_list.add_picture(pixmap, result.credit)
            self._images.append(result)

    def _on_image_search_failed(self, error: Exception) -> None:
        if isinstance(error, InvalidApiKeyError):
            # Appended rather than replacing the label: the other source's
            # attribution must stay visible next to its results.
            self._images_label.setText(
                f"{self._images_label.text()}<br>{error.source} rejected the API key. "
                "Check it in Tools › Add-ons › mieru › Config."
            )
        else:
            self._show_network_error(error)

    # Audio follows the chosen candidate.

    def _on_candidate_changed(self, row: int) -> None:
        self._audio = None
        self._play_button.setEnabled(False)
        self._candidate = self._candidates[row] if 0 <= row < len(self._candidates) else None
        self._update_add_button()
        candidate = self._candidate
        if candidate is None:
            return
        QueryOp(
            parent=self,
            op=lambda _col: audio.fetch_audio(candidate.word, candidate.reading),
            success=lambda found: self._on_audio(candidate, found),
        ).without_collection().run_in_background()

    def _on_audio(self, candidate: Candidate, found: bytes | None) -> None:
        if candidate != self._candidate:
            return
        self._audio = found
        self._play_button.setEnabled(found is not None)
        if found:
            self._play_audio()

    def _play_audio(self) -> None:
        if self._audio is None:
            return
        path = tmpfile(prefix="mieru", suffix=".mp3")
        with open(path, "wb") as file:
            file.write(self._audio)
        av_player.play_file(path)

    # Adding the note.

    def _update_add_button(self) -> None:
        self._add_button.setEnabled(
            self._candidate is not None and self._image_list.currentRow() >= 0
        )

    def _add(self) -> None:
        candidate = self._candidate
        row = self._image_list.currentRow()
        if candidate is None or row < 0:
            return
        note = self.mw.col.new_note(ensure_note_type(self.mw.col))
        note[WORD_FIELD] = to_anki_furigana(candidate.word, candidate.reading)
        note[ENGLISH_FIELD] = self._query
        if note.fields_check() == NoteFieldsCheckResult.DUPLICATE and not askUser(
            f"You already have a mieru card for {candidate.word}. Add it anyway?",
            parent=self,
            defaultno=True,
        ):
            return

        image = self._images[row]
        audio_data = self._audio
        deck_id = self._deck_chooser.selected_deck_id

        def save_note(image_data: bytes) -> None:
            media = self.mw.col.media
            image_name = media.write_data(
                f"mieru_{candidate.word}{_extension(image.image_url)}", image_data
            )
            note[IMAGE_FIELD] = f'<img src="{html.escape(image_name)}">'
            if audio_data is not None:
                audio_name = media.write_data(f"mieru_{candidate.word}.mp3", audio_data)
                note[AUDIO_FIELD] = f"[sound:{audio_name}]"
            add_note(parent=self, note=note, target_deck_id=deck_id).success(
                lambda _: self._on_added(candidate)
            ).run_in_background()

        QueryOp(
            parent=self,
            op=lambda _col: images.download(image.image_url),
            success=save_note,
        ).without_collection().with_progress("Downloading picture…").failure(
            self._show_network_error
        ).run_in_background()

    def _on_added(self, candidate: Candidate) -> None:
        tooltip(f"Added {candidate.word}", parent=self.mw)
        self._reset()

    def _configured_sources(self) -> list[tuple[Source, str]]:
        # Read on every use so a key saved while the window is open takes effect.
        config = self.mw.addonManager.getConfig(__name__) or {}
        keys = ((source, str(config.get(source.config_key, "")).strip()) for source in SOURCES)
        return [(source, key) for source, key in keys if key]

    def _show_network_error(self, error: Exception) -> None:
        if isinstance(error, requests.RequestException):
            showWarning(f"Could not reach the server: {error}", parent=self)
        else:
            raise error

    def reject(self) -> None:
        saveGeom(self, _GEOMETRY_KEY)
        self._reset()
        super().reject()


def _images_label(sources: list[tuple[Source, str]]) -> str:
    if not sources:
        return _MISSING_KEY_MESSAGE
    # Pixabay's API terms require showing where search results come from.
    links = " and ".join(f'<a href="{source.url}">{source.name}</a>' for source, _key in sources)
    return f"<b>Picture</b> (from {links})"


def _search_with_thumbnails(
    source: Source, api_key: str, image_query: str
) -> list[tuple[ImageResult, bytes | None]]:
    results = source.search(image_query, api_key)
    with ThreadPoolExecutor(max_workers=_THUMBNAIL_DOWNLOADS) as pool:
        thumbnails = pool.map(lambda result: _try_download(result.preview_url), results)
        return list(zip(results, thumbnails))


def _try_download(url: str) -> bytes | None:
    try:
        return images.download(url)
    except requests.RequestException:
        return None


def _extension(url: str) -> str:
    return PurePosixPath(urlparse(url).path).suffix or ".jpg"
