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

    heading = question[question.index('<div class="heading">') :]
    heading = heading[: heading.index("</div>")]
    assert "<ruby><rb>食</rb><rt>た</rt></ruby>べる" in heading
    assert "[anki:play:q:0]" in heading
    assert "mieru_食べる.jpg" not in question
    assert "mieru_食べる.jpg" in answer
    assert "<hr" not in answer
    assert "to eat" not in answer


def test_restores_the_template_and_css_of_an_existing_note_type(col: Collection) -> None:
    original = ensure_note_type(col)
    front, back, css = original["tmpls"][0]["qfmt"], original["tmpls"][0]["afmt"], original["css"]
    original["tmpls"][0]["qfmt"] = "{{Word}}"
    original["tmpls"][0]["afmt"] = "{{FrontSide}}<hr id=answer>{{Image}}"
    original["css"] = ".card {}"
    col.models.update_dict(original)

    ensure_note_type(col)

    restored = col.models.by_name(NOTE_TYPE_NAME)
    assert restored is not None
    assert restored["tmpls"][0]["qfmt"] == front
    assert restored["tmpls"][0]["afmt"] == back
    assert restored["css"] == css
