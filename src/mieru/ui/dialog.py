"""The mieru window: English word -> Japanese candidate -> picture -> new note."""

from __future__ import annotations

import html
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import urlparse

import requests
from anki.errors import AbortSchemaModification
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
from ..core.dictionary import Candidate, split_queries
from ..core.furigana import to_anki_furigana
from ..core.images import SOURCES, ImageResult, InvalidApiKeyError, Source
from .note_type import (
    AUDIO_FIELD,
    ENGLISH_FIELD,
    IMAGE_FIELD,
    PERSONAL_CONNECTION_FIELD,
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


@dataclass(eq=False)
class _Word:
    """One English word of the list with everything loaded and chosen for it, so
    moving between words keeps their state."""

    query: str
    image_query: str
    # None while the dictionary lookup runs.
    candidates: list[Candidate] | None = None
    candidate_row: int = 0
    audio: dict[Candidate, bytes | None] = field(default_factory=dict)
    audio_requested: set[Candidate] = field(default_factory=set)
    pictures: list[tuple[ImageResult, QPixmap]] = field(default_factory=list)
    picture_row: int = -1
    personal_connection: str = ""
    added: bool = False

    @property
    def candidate(self) -> Candidate | None:
        if self.candidates and 0 <= self.candidate_row < len(self.candidates):
            return self.candidates[self.candidate_row]
        return None

    @property
    def is_ready(self) -> bool:
        return (
            self.candidate is not None
            and self.picture_row >= 0
            and bool(self.personal_connection.strip())
        )


class MieruDialog(QDialog):
    """Kept alive and reused across openings, so late network results land on a
    hidden window instead of a deleted one."""

    def __init__(self, mw: AnkiQt) -> None:
        super().__init__(mw)
        self.mw = mw
        self._words: list[_Word] = []
        self._index = 0
        self._rejected_sources: set[str] = set()
        self._warning_open = False
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
        self._query_input.setPlaceholderText("English words, e.g. dog, cat, bank")
        self._query_input.setTextMargins(_TEXT_MARGIN, 0, _TEXT_MARGIN, 0)
        self._query_input.returnPressed.connect(self._search)
        search_button = QPushButton("Search")
        search_button.clicked.connect(self._search)
        search_row.addWidget(self._query_input)
        search_row.addWidget(search_button)
        layout.addLayout(search_row)

        self._list_row = QWidget()
        list_layout = QHBoxLayout(self._list_row)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self._previous_button = QPushButton("‹ Previous")
        self._previous_button.clicked.connect(lambda: self._go_to(self._index - 1))
        self._list_label = QLabel()
        self._list_label.setWordWrap(True)
        self._list_label.linkActivated.connect(lambda href: self._go_to(int(href)))
        self._next_button = QPushButton("Next ›")
        self._next_button.clicked.connect(lambda: self._go_to(self._index + 1))
        list_layout.addWidget(self._previous_button)
        list_layout.addWidget(self._list_label, stretch=1)
        list_layout.addWidget(self._next_button)
        layout.addWidget(self._list_row)
        layout.addSpacing(_SECTION_SPACING)

        word_row = QHBoxLayout()
        self._word_label = QLabel()
        self._play_button = QPushButton("▶ Play")
        self._play_button.clicked.connect(self._play_audio)
        word_row.addWidget(self._word_label, stretch=1)
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
        self._image_query_input.returnPressed.connect(self._refine_images)
        image_search_button = QPushButton("Search")
        image_search_button.clicked.connect(self._refine_images)
        image_search_row.addWidget(self._image_query_input)
        image_search_row.addWidget(image_search_button)
        layout.addLayout(image_search_row)
        self._image_list = PictureGrid()
        self._image_list.currentRowChanged.connect(self._on_picture_changed)
        layout.addWidget(self._image_list, stretch=3)
        layout.addSpacing(_SECTION_SPACING)

        layout.addWidget(QLabel("<b>Personal connection</b>"))
        self._connection_input = QLineEdit()
        self._connection_input.setPlaceholderText(
            "A memory, place or person this word brings to mind"
        )
        self._connection_input.setTextMargins(_TEXT_MARGIN, 0, _TEXT_MARGIN, 0)
        self._connection_input.textEdited.connect(self._on_connection_edited)
        layout.addWidget(self._connection_input)
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

    @property
    def _word(self) -> _Word | None:
        return self._words[self._index] if self._words else None

    def _reset(self) -> None:
        self._words = []
        self._index = 0
        self._rejected_sources = set()
        self._show_word()
        self._query_input.setFocus()
        self._query_input.selectAll()

    # Search: every word of the list is looked up at once, so moving between
    # words never waits. Candidates come from the English word; pictures from
    # their own search term, which starts as the English word and can be refined.
    # Results are stored on their word, and shown only if it is the current one.

    def _search(self) -> None:
        queries = split_queries(self._query_input.text())
        if not queries:
            return
        self._reset()
        self._words = [_Word(query=query, image_query=query) for query in queries]
        for word in self._words:
            self._look_up(word)
            self._search_images(word)
        self._go_to(0)

    def _look_up(self, word: _Word) -> None:
        def on_failure(error: Exception) -> None:
            self._on_candidates(word, [])
            self._show_network_error(error)

        QueryOp(
            parent=self,
            op=lambda _col: dictionary.search(word.query),
            success=lambda candidates: self._on_candidates(word, candidates),
        ).without_collection().failure(on_failure).run_in_background()

    def _on_candidates(self, word: _Word, candidates: list[Candidate]) -> None:
        word.candidates = candidates
        if candidates:
            self._fetch_audio(word, candidates[0])
        if word is self._word:
            self._show_candidates()

    def _refine_images(self) -> None:
        word = self._word
        image_query = self._image_query_input.text().strip()
        if word is None or not image_query:
            return
        word.image_query = image_query
        word.pictures = []
        word.picture_row = -1
        self._search_images(word)
        self._show_pictures()

    def _search_images(self, word: _Word) -> None:
        for source, api_key in self._configured_sources():
            self._search_source(word, source, api_key)

    def _search_source(self, word: _Word, source: Source, api_key: str) -> None:
        image_query = word.image_query
        QueryOp(
            parent=self,
            op=lambda _col: _search_with_thumbnails(source, api_key, image_query),
            success=lambda found: self._on_pictures(word, source, image_query, found),
        ).without_collection().failure(self._on_image_search_failed).run_in_background()

    def _on_pictures(
        self,
        word: _Word,
        source: Source,
        image_query: str,
        found: list[tuple[ImageResult, bytes | None]],
    ) -> None:
        if image_query != word.image_query:
            return
        is_current = word is self._word
        if not found and is_current:
            tooltip(f"No pictures found on {source.name} for “{image_query}”.", parent=self)
        for result, thumbnail in found:
            pixmap = QPixmap()
            if thumbnail is not None:
                pixmap.loadFromData(thumbnail)
            word.pictures.append((result, pixmap))
            if is_current:
                self._image_list.add_picture(pixmap, result.credit)

    def _on_image_search_failed(self, error: Exception) -> None:
        if isinstance(error, InvalidApiKeyError):
            self._rejected_sources.add(error.source)
            self._show_images_label()
        else:
            self._show_network_error(error)

    # Moving between words.

    def _go_to(self, index: int) -> None:
        if not 0 <= index < len(self._words):
            return
        self._index = index
        self._show_word()
        if len(self._words) > 1:
            self._candidate_list.setFocus()

    def _next_pending(self) -> int | None:
        count = len(self._words)
        for offset in range(1, count + 1):
            index = (self._index + offset) % count
            if not self._words[index].added:
                return index
        return None

    def _show_word(self) -> None:
        word = self._word
        self._show_list()
        self._image_query_input.setText(word.image_query if word else "")
        self._connection_input.setText(word.personal_connection if word else "")
        self._show_candidates()
        self._show_pictures()
        self._show_images_label()

    def _show_list(self) -> None:
        is_list = len(self._words) > 1
        self._list_row.setVisible(is_list)
        if is_list:
            self._list_label.setText(_list_label(self._words, self._index))
            self._previous_button.setEnabled(self._index > 0)
            self._next_button.setEnabled(self._index < len(self._words) - 1)

    def _show_candidates(self) -> None:
        word = self._word
        self._word_label.setText(_word_label(word))
        # Filling the list would otherwise report row changes as the user's choice.
        self._candidate_list.blockSignals(True)
        self._candidate_list.clear()
        if word is not None and word.candidates:
            for candidate in word.candidates:
                self._candidate_list.add_candidate(candidate)
            self._candidate_list.setCurrentRow(word.candidate_row)
        self._candidate_list.blockSignals(False)
        self._show_candidate()

    def _show_pictures(self) -> None:
        word = self._word
        self._image_list.blockSignals(True)
        self._image_list.clear()
        if word is not None:
            for result, pixmap in word.pictures:
                self._image_list.add_picture(pixmap, result.credit)
            self._image_list.setCurrentRow(word.picture_row)
        self._image_list.blockSignals(False)
        self._update_add_button()

    def _show_images_label(self) -> None:
        text = _images_label(self._configured_sources())
        for source in sorted(self._rejected_sources):
            text += (
                f"<br>{source} rejected the API key. Check it in Tools › Add-ons › mieru › Config."
            )
        self._images_label.setText(text)

    # Audio follows the chosen candidate; each word's first candidate is fetched
    # along with the lookup, so it plays as soon as the word is shown.

    def _on_candidate_changed(self, row: int) -> None:
        word = self._word
        if word is None or row < 0:
            return
        word.candidate_row = row
        self._show_candidate()

    def _show_candidate(self) -> None:
        word = self._word
        candidate = word.candidate if word else None
        self._update_add_button()
        self._play_button.setEnabled(False)
        if word is None or candidate is None:
            return
        if candidate in word.audio:
            self._play_button.setEnabled(word.audio[candidate] is not None)
            self._play_audio()
        else:
            self._fetch_audio(word, candidate)

    def _fetch_audio(self, word: _Word, candidate: Candidate) -> None:
        if candidate in word.audio_requested:
            return
        word.audio_requested.add(candidate)
        QueryOp(
            parent=self,
            op=lambda _col: audio.fetch_audio(candidate.word, candidate.reading),
            success=lambda found: self._on_audio(word, candidate, found),
        ).without_collection().run_in_background()

    def _on_audio(self, word: _Word, candidate: Candidate, found: bytes | None) -> None:
        word.audio[candidate] = found
        if word is self._word and candidate == word.candidate:
            self._play_button.setEnabled(found is not None)
            self._play_audio()

    def _play_audio(self) -> None:
        word = self._word
        candidate = word.candidate if word else None
        data = word.audio.get(candidate) if word and candidate else None
        if data is None:
            return
        path = tmpfile(prefix="mieru", suffix=".mp3")
        with open(path, "wb") as file:
            file.write(data)
        av_player.play_file(path)

    # Adding the note.

    def _on_picture_changed(self, row: int) -> None:
        word = self._word
        if word is not None:
            word.picture_row = row
        self._update_add_button()

    def _on_connection_edited(self, text: str) -> None:
        word = self._word
        if word is not None:
            word.personal_connection = text
        self._update_add_button()

    def _update_add_button(self) -> None:
        word = self._word
        self._add_button.setEnabled(word is not None and word.is_ready)

    def _add(self) -> None:
        word = self._word
        if word is None or not word.is_ready:
            return
        candidate = word.candidate
        assert candidate is not None
        try:
            notetype = ensure_note_type(self.mw.col)
        except AbortSchemaModification:
            return
        note = self.mw.col.new_note(notetype)
        note[WORD_FIELD] = to_anki_furigana(candidate.word, candidate.reading)
        note[ENGLISH_FIELD] = word.query
        note[PERSONAL_CONNECTION_FIELD] = html.escape(word.personal_connection.strip())
        if note.fields_check() == NoteFieldsCheckResult.DUPLICATE and not askUser(
            f"You already have a mieru card for {candidate.word}. Add it anyway?",
            parent=self,
            defaultno=True,
        ):
            return

        image = word.pictures[word.picture_row][0]
        audio_data = word.audio.get(candidate)
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
                lambda _: self._on_added(word, candidate)
            ).run_in_background()

        QueryOp(
            parent=self,
            op=lambda _col: images.download(image.image_url),
            success=save_note,
        ).without_collection().with_progress("Downloading picture…").failure(
            self._show_network_error
        ).run_in_background()

    def _on_added(self, word: _Word, candidate: Candidate) -> None:
        tooltip(f"Added {candidate.word}", parent=self.mw)
        word.added = True
        if word is not self._word:
            # The user moved to another word while the picture downloaded.
            self._show_list()
            return
        index = self._next_pending()
        if index is None:
            self._reset()
        else:
            self._go_to(index)

    def _configured_sources(self) -> list[tuple[Source, str]]:
        # Read on every use so a key saved while the window is open takes effect.
        config = self.mw.addonManager.getConfig(__name__) or {}
        keys = ((source, str(config.get(source.config_key, "")).strip()) for source in SOURCES)
        return [(source, key) for source, key in keys if key]

    def _show_network_error(self, error: Exception) -> None:
        if not isinstance(error, requests.RequestException):
            raise error
        # Offline, every word of a list fails at once; one warning at a time is enough.
        if self._warning_open:
            return
        self._warning_open = True
        try:
            showWarning(f"Could not reach the server: {error}", parent=self)
        finally:
            self._warning_open = False

    def reject(self) -> None:
        saveGeom(self, _GEOMETRY_KEY)
        self._reset()
        super().reject()


def _list_label(words: list[_Word], index: int) -> str:
    parts = []
    for i, word in enumerate(words):
        text = html.escape(word.query)
        if word.added:
            text = f"✓ {text}"
        parts.append(f"<b>{text}</b>" if i == index else f'<a href="{i}">{text}</a>')
    return f"{index + 1} of {len(words)}: {' · '.join(parts)}"


def _word_label(word: _Word | None) -> str:
    label = "<b>Japanese word</b>"
    if word is None:
        return label
    if word.candidates is None:
        return f"{label} · looking up…"
    if not word.candidates:
        return f"{label} · none found for “{html.escape(word.query)}”"
    return label


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
