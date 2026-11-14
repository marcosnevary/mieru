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
    QIcon,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPixmap,
    QPushButton,
    QSize,
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
from ..core.images import ImageResult, InvalidApiKeyError
from .note_type import (
    AUDIO_FIELD,
    ENGLISH_FIELD,
    IMAGE_FIELD,
    WORD_FIELD,
    ensure_note_type,
)

_GEOMETRY_KEY = "mieru"
_THUMBNAIL_SIZE = QSize(150, 150)
_THUMBNAIL_DOWNLOADS = 8
_MEANINGS_SHOWN = 3
_MISSING_KEY_MESSAGE = (
    "To choose pictures, add a free Pixabay API key in "
    'Tools › Add-ons › mieru › Config (get one at <a href="https://pixabay.com/api/docs/">'
    "pixabay.com/api/docs</a>)."
)
# Pixabay's API terms require showing where search results come from.
_IMAGES_LABEL = 'Picture — from <a href="https://pixabay.com/">Pixabay</a>'
_INVALID_KEY_MESSAGE = "Pixabay rejected the API key. Check it in Tools › Add-ons › mieru › Config."


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
        self._images: list[ImageResult] = []
        self._setup_ui()
        restoreGeom(self, _GEOMETRY_KEY)

    def _setup_ui(self) -> None:
        self.setWindowTitle("mieru — new Japanese card")
        disable_help_button(self)
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self._query_input = QLineEdit()
        self._query_input.setPlaceholderText("English word, e.g. dog")
        self._query_input.returnPressed.connect(self._search)
        search_button = QPushButton("Search")
        search_button.clicked.connect(self._search)
        search_row.addWidget(self._query_input)
        search_row.addWidget(search_button)
        layout.addLayout(search_row)

        layout.addWidget(QLabel("Japanese word"))
        self._candidate_list = QListWidget()
        self._candidate_list.currentRowChanged.connect(self._on_candidate_changed)
        layout.addWidget(self._candidate_list, stretch=1)

        audio_row = QHBoxLayout()
        self._audio_status = QLabel()
        self._play_button = QPushButton("▶ Play")
        self._play_button.clicked.connect(self._play_audio)
        audio_row.addWidget(self._audio_status, stretch=1)
        audio_row.addWidget(self._play_button)
        layout.addLayout(audio_row)

        self._images_label = QLabel()
        self._images_label.setOpenExternalLinks(True)
        self._images_label.setWordWrap(True)
        layout.addWidget(self._images_label)
        self._image_list = QListWidget()
        self._image_list.setViewMode(QListView.ViewMode.IconMode)
        self._image_list.setIconSize(_THUMBNAIL_SIZE)
        self._image_list.setResizeMode(QListView.ResizeMode.Adjust)
        self._image_list.setMovement(QListView.Movement.Static)
        self._image_list.setSpacing(6)
        self._image_list.currentRowChanged.connect(lambda _row: self._update_add_button())
        layout.addWidget(self._image_list, stretch=3)

        deck_row = QWidget()
        self._deck_chooser = DeckChooser(self.mw, deck_row)
        layout.addWidget(deck_row)

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
        self._images = []
        self._candidate_list.clear()
        self._image_list.clear()
        self._audio_status.setText("")
        self._play_button.setEnabled(False)
        self._update_add_button()
        self._images_label.setText(
            _IMAGES_LABEL if self._pixabay_api_key() else _MISSING_KEY_MESSAGE
        )
        self._query_input.setFocus()
        self._query_input.selectAll()

    # Search: candidates and pictures both depend only on the English word.

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

        if api_key := self._pixabay_api_key():
            QueryOp(
                parent=self,
                op=lambda _col: _search_images_with_thumbnails(query, api_key),
                success=lambda found: self._show_images(query, found),
            ).without_collection().failure(self._on_image_search_failed).run_in_background()

    def _show_candidates(self, query: str, candidates: list[Candidate]) -> None:
        if query != self._query:
            return
        if not candidates:
            tooltip(f"No Japanese words found for “{query}”.", parent=self)
            return
        self._candidates = candidates
        for candidate in candidates:
            label = f"{candidate.word}【{candidate.reading}】"
            if candidate.is_common:
                label += "  · common"
            meanings = "; ".join(candidate.meanings[:_MEANINGS_SHOWN])
            self._candidate_list.addItem(f"{label}\n    {meanings}")
        self._candidate_list.setCurrentRow(0)

    def _show_images(self, query: str, found: list[tuple[ImageResult, bytes | None]]) -> None:
        if query != self._query:
            return
        if not found:
            tooltip(f"No pictures found for “{query}”.", parent=self)
        for result, thumbnail in found:
            pixmap = QPixmap()
            if thumbnail is not None:
                pixmap.loadFromData(thumbnail)
            item = QListWidgetItem(QIcon(pixmap), "")
            item.setSizeHint(_THUMBNAIL_SIZE + QSize(12, 12))
            self._image_list.addItem(item)
            self._images.append(result)

    def _on_image_search_failed(self, error: Exception) -> None:
        if isinstance(error, InvalidApiKeyError):
            self._images_label.setText(_INVALID_KEY_MESSAGE)
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
            self._audio_status.setText("")
            return
        self._audio_status.setText("Audio: loading…")
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
        self._audio_status.setText("Audio: ready" if found else "Audio: not found")
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

    def _pixabay_api_key(self) -> str:
        # Read on every use so a key saved while the window is open takes effect.
        config = self.mw.addonManager.getConfig(__name__) or {}
        return str(config.get("pixabay_api_key", "")).strip()

    def _show_network_error(self, error: Exception) -> None:
        if isinstance(error, requests.RequestException):
            showWarning(f"Could not reach the server: {error}", parent=self)
        else:
            raise error

    def reject(self) -> None:
        saveGeom(self, _GEOMETRY_KEY)
        self._reset()
        super().reject()


def _search_images_with_thumbnails(
    query: str, api_key: str
) -> list[tuple[ImageResult, bytes | None]]:
    results = images.search(query, api_key)
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
