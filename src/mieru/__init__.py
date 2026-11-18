"""mieru: turn an English word into a Japanese Anki card with furigana, audio and a picture."""

from __future__ import annotations

from aqt import gui_hooks, mw
from aqt.qt import QAction, QKeySequence

from .ui.editor_audio import add_editor_button

_dialog = None


def _open_dialog() -> None:
    # Imported lazily so loading the add-on stays cheap at Anki startup.
    from .ui.dialog import MieruDialog

    global _dialog
    assert mw is not None
    if _dialog is None:
        _dialog = MieruDialog(mw)
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()


def _refresh_note_type() -> None:
    # Imported lazily so loading the add-on stays cheap at Anki startup.
    from .ui.note_type import refresh_note_type

    assert mw is not None
    refresh_note_type(mw.col)


def _add_menu_action() -> None:
    assert mw is not None
    action = QAction("mieru…", mw)
    action.setShortcut(QKeySequence("W"))
    action.triggered.connect(_open_dialog)
    mw.form.menuTools.addAction(action)


gui_hooks.profile_did_open.append(_refresh_note_type)
gui_hooks.main_window_did_init.append(_add_menu_action)
gui_hooks.editor_did_init_buttons.append(add_editor_button)
