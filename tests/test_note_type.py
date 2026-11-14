from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from anki.collection import Collection

from mieru.ui.note_type import NOTE_TYPE_NAME, ensure_note_type


@pytest.fixture
def col(tmp_path: Path) -> Iterator[Collection]:
    collection = Collection(str(tmp_path / "collection.anki2"))
    yield collection
    collection.close()


def test_creates_the_note_type_once(col: Collection) -> None:
    first = ensure_note_type(col)
    second = ensure_note_type(col)

    assert first["id"] == second["id"]
    assert len([m for m in col.models.all_names_and_ids() if m.name == NOTE_TYPE_NAME]) == 1


def test_shows_word_with_furigana_and_audio_on_front_and_only_the_picture_behind(
    col: Collection,
) -> None:
    note = col.new_note(ensure_note_type(col))
    note["Word"] = "食[た]べる"
    note["Audio"] = "[sound:mieru_食べる.mp3]"
    note["Image"] = '<img src="mieru_食べる.jpg">'
    note["English"] = "to eat"
    col.add_note(note, col.decks.get_current_id())

    card = note.cards()[0]
    question = card.question()
    answer = card.answer()

    assert "<ruby><rb>食</rb><rt>た</rt></ruby>べる" in question
    assert "[anki:play:q:0]" in question
    assert "mieru_食べる.jpg" not in question
    assert "mieru_食べる.jpg" in answer
    assert "to eat" not in answer
