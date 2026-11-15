"""The mieru window: English word -> Japanese candidate -> picture -> new note."""

from __future__ import annotations

import html
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import requests
from anki.collection import SearchNode
from anki.errors import AbortSchemaModification
from anki.notes import Note
from anki.utils import tmpfile
from aqt.deckchooser import DeckChooser
from aqt.main import AnkiQt
from aqt.operations import QueryOp
from aqt.operations.note import add_note, update_note
from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPixmap,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from aqt.sound import av_player
from aqt.utils import (
    disable_help_button,
    restoreGeom,
    saveGeom,
    showWarning,
    tooltip,
)

from ..core import audio, dictionary, images, stroke_order
from ..core.dictionary import Candidate, split_queries
from ..core.furigana import to_anki_furigana
from ..core.images import SOURCES, ImageResult, InvalidApiKeyError, Source
from .note_type import (
    AUDIO_FIELD,
    ENGLISH_FIELD,
    FIELDS,
    IMAGE_FIELD,
    NOTE_TYPE_NAME,
    PERSONAL_CONNECTION_FIELD,
    STROKE_ORDER_FIELD,
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
_IMPORT_FILTER = "Pictures (*.jpg *.jpeg *.png *.gif *.webp)"
_MISSING_KEY_MESSAGE = (
    "To choose pictures, add a free Pixabay API key in "
    'Tools › Add-ons › mieru › Config (get one at <a href="https://pixabay.com/api/docs/">'
    "pixabay.com/api/docs</a>)."
)


@dataclass(eq=False)
class _Picture:
    """A picture of a word: a search result downloaded when the note is added, or a
    file the user imported."""

    thumbnail: QPixmap
    credit: str
    # Including the dot, as in ".jpg".
    suffix: str
    image_url: str | None = None
    data: bytes | None = None

    @property
    def imported(self) -> bool:
        return self.data is not None


class _Duplicate(Enum):
    REPLACE = "replace"
    ADD = "add"
    CANCEL = "cancel"


@dataclass(eq=False)
class _Word:
    """One English word of the list with everything loaded and chosen for it, so
    moving between words keeps their state."""

    query: str
    image_query: str
    # None while the dictionary lookup runs.
    candidates: list[Candidate] | None = None
    lookup_failed: bool = False
    candidate_row: int = 0
    audio: dict[Candidate, bytes | None] = field(default_factory=dict)
    audio_requested: set[Candidate] = field(default_factory=set)
    pictures: list[_Picture] = field(default_factory=list)
    selected_pictures: set[_Picture] = field(default_factory=set)
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
            and bool(self.selected_pictures)
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
        self._import_button = QPushButton("Import…")
        self._import_button.clicked.connect(self._import_pictures)
        image_search_row.addWidget(self._image_query_input)
        image_search_row.addWidget(image_search_button)
        image_search_row.addWidget(self._import_button)
        layout.addLayout(image_search_row)
        self._image_list = PictureGrid()
        self._image_list.itemSelectionChanged.connect(self._on_picture_selection_changed)
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
            word.lookup_failed = True
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
        # Imported pictures are the user's own choice, so a new search keeps them.
        word.pictures = [picture for picture in word.pictures if picture.imported]
        word.selected_pictures.intersection_update(word.pictures)
        self._search_images(word)
        self._show_pictures()

    def _import_pictures(self) -> None:
        word = self._word
        if word is None:
            return
        paths, _filter = QFileDialog.getOpenFileNames(self, "Import pictures", "", _IMPORT_FILTER)
        unreadable = []
        for path in paths:
            file = Path(path)
            data = file.read_bytes()
            thumbnail = QPixmap()
            if not thumbnail.loadFromData(data):
                unreadable.append(file.name)
                continue
            picture = _Picture(
                thumbnail=thumbnail,
                credit=f"{file.name} (imported)",
                suffix=file.suffix.lower(),
                data=data,
            )
            word.pictures.append(picture)
            word.selected_pictures.add(picture)
        self._show_pictures()
        if unreadable:
            showWarning(f"Could not read as pictures: {', '.join(unreadable)}", parent=self)

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
            word.pictures.append(
                _Picture(
                    thumbnail=pixmap,
                    credit=result.credit,
                    suffix=_extension(result.image_url),
                    image_url=result.image_url,
                )
            )
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
        self._import_button.setEnabled(word is not None)
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
            for picture in word.pictures:
                self._image_list.add_picture(picture.thumbnail, picture.credit)
            self._image_list.select_rows(
                [
                    row
                    for row, picture in enumerate(word.pictures)
                    if picture in word.selected_pictures
                ]
            )
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

    def _on_picture_selection_changed(self) -> None:
        word = self._word
        if word is not None:
            word.selected_pictures = {
                word.pictures[row] for row in self._image_list.selected_rows()
            }
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
        target = note
        replacing = False
        existing = self._find_duplicate(note)
        if existing is not None:
            choice = _ask_duplicate(self, candidate.word)
            if choice is _Duplicate.CANCEL:
                return
            if choice is _Duplicate.REPLACE:
                for name in FIELDS:
                    existing[name] = note[name]
                target = existing
                replacing = True

        pictures = [picture for picture in word.pictures if picture in word.selected_pictures]
        audio_data = word.audio.get(candidate)
        deck_id = self._deck_chooser.selected_deck_id

        def download() -> tuple[list[bytes], list[tuple[str, bytes]]]:
            return (
                [_picture_bytes(picture) for picture in pictures],
                stroke_order.fetch_stroke_order(candidate.word),
            )

        def save_note(downloaded: tuple[list[bytes], list[tuple[str, bytes]]]) -> None:
            picture_data, diagrams = downloaded
            media = self.mw.col.media
            image_names = [
                media.write_data(f"mieru_{candidate.word}_{number}{picture.suffix}", data)
                for number, (picture, data) in enumerate(zip(pictures, picture_data), start=1)
            ]
            target[IMAGE_FIELD] = "".join(
                f'<img src="{html.escape(name)}">' for name in image_names
            )
            target[AUDIO_FIELD] = ""
            if audio_data is not None:
                audio_name = media.write_data(f"mieru_{candidate.word}.mp3", audio_data)
                target[AUDIO_FIELD] = f"[sound:{audio_name}]"
            # Named by character, so words sharing a character share its file.
            diagram_names = [
                media.write_data(f"mieru_stroke_order_{character}.svg", svg)
                for character, svg in diagrams
            ]
            target[STROKE_ORDER_FIELD] = "".join(
                f'<img src="{html.escape(name)}">' for name in diagram_names
            )
            if replacing:
                operation = update_note(parent=self, note=target)
            else:
                operation = add_note(parent=self, note=target, target_deck_id=deck_id)
            operation.success(
                lambda _: self._on_added(word, candidate, replacing)
            ).run_in_background()

        QueryOp(
            parent=self,
            op=lambda _col: download(),
            success=save_note,
        ).without_collection().with_progress("Downloading pictures and stroke order…").failure(
            self._show_network_error
        ).run_in_background()

    def _find_duplicate(self, note: Note) -> Note | None:
        col = self.mw.col
        search = col.build_search_string(
            SearchNode(note=NOTE_TYPE_NAME),
            SearchNode(field=SearchNode.Field(field_name=WORD_FIELD, text=note[WORD_FIELD])),
        )
        note_ids = col.find_notes(search)
        # The oldest one: its card history is the longest.
        return col.get_note(min(note_ids)) if note_ids else None

    def _on_added(self, word: _Word, candidate: Candidate, replaced: bool) -> None:
        tooltip(f"{'Replaced' if replaced else 'Added'} {candidate.word}", parent=self.mw)
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
            showWarning(_network_error_message(error), parent=self)
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
    query = html.escape(word.query)
    if word.lookup_failed:
        return f"{label} · could not look up “{query}”"
    if not word.candidates:
        return f"{label} · none found for “{query}”"
    return label


def _network_error_message(error: requests.RequestException) -> str:
    response = error.response if isinstance(error, requests.HTTPError) else None
    if response is not None and response.status_code == 429:
        return "The server is limiting requests right now. Wait a minute and search again."
    return f"Could not reach the server: {error}"


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


def _picture_bytes(picture: _Picture) -> bytes:
    if picture.data is not None:
        return picture.data
    assert picture.image_url is not None
    return images.download(picture.image_url)


def _ask_duplicate(parent: QWidget, word: str) -> _Duplicate:
    box = QMessageBox(parent)
    box.setWindowTitle("mieru")
    box.setText(f"You already have a mieru card for {word}.")
    replace = box.addButton("Replace", QMessageBox.ButtonRole.AcceptRole)
    add = box.addButton("Add anyway", QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked is replace:
        return _Duplicate.REPLACE
    if clicked is add:
        return _Duplicate.ADD
    return _Duplicate.CANCEL
