"""An Audio button in Anki's note editor: generates the pronunciation of the selected
Japanese word and copies its sound tag, to paste after the word, in any editor (add,
edit, Browser)."""

from __future__ import annotations

from aqt.editor import Editor, NewEditor
from aqt.operations import QueryOp
from aqt.qt import QApplication
from aqt.utils import showWarning, tooltip

from ..core import audio, dictionary


def add_editor_button(buttons: list[str], editor: Editor | NewEditor) -> None:
    buttons.append(
        editor.addButton(
            icon=None,
            cmd="mieruAudio",
            func=_generate,
            tip="Generate the audio of the selected Japanese word (mieru)",
            label="Audio",
        )
    )


def _generate(editor: Editor | NewEditor) -> None:
    editor.web.evalWithCallback(
        "getSelection().toString()", lambda text: _on_selection(editor, str(text))
    )


def _on_selection(editor: Editor | NewEditor, text: str) -> None:
    word = text.strip()
    if not dictionary.is_japanese(word):
        tooltip("Select a Japanese word first.", parent=editor.parentWindow)
        return
    QueryOp(
        parent=editor.parentWindow,
        op=lambda _col: _fetch(word),
        success=lambda data: _on_audio(editor, word, data),
    ).without_collection().failure(
        lambda error: showWarning(
            f"Could not generate the audio: {error}", parent=editor.parentWindow
        )
    ).run_in_background()


def _fetch(word: str) -> bytes | None:
    reading = dictionary.reading_of(word)
    if reading is None:
        return None
    return audio.fetch_audio(word, reading)


def _on_audio(editor: Editor | NewEditor, word: str, data: bytes | None) -> None:
    if data is None:
        tooltip(f"No audio found for {word}.", parent=editor.parentWindow)
        return
    name = editor.mw.col.media.write_data(f"mieru_{word}.mp3", data)
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    clipboard.setText(f"[sound:{name}]")
    tooltip(f"Audio ready for {word}. Paste it after the word.", parent=editor.parentWindow)
