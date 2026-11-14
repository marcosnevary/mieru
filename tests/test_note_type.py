from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from anki.cards import Card
from anki.collection import Collection

from mieru.ui.note_type import NOTE_TYPE_NAME, ensure_note_type

_RUBY_WORD = "<ruby><rb>食</rb><rt>た</rt></ruby>べる"
_PICTURE = "mieru_食べる.jpg"
_CONNECTION = "Lunch with grandma"


@pytest.fixture
def col(tmp_path: Path) -> Iterator[Collection]:
    collection = Collection(str(tmp_path / "collection.anki2"))
    yield collection
    collection.close()


@pytest.fixture
def cards(col: Collection) -> list[Card]:
    note = col.new_note(ensure_note_type(col))
    note["Word"] = "食[た]べる"
    note["Audio"] = "[sound:mieru_食べる.mp3]"
    note["Image"] = f'<img src="{_PICTURE}">'
    note["English"] = "to eat"
    note["Personal Connection"] = _CONNECTION
    col.add_note(note, col.decks.get_current_id())
    return sorted(note.cards(), key=lambda card: card.ord)


def test_creates_the_note_type_once(col: Collection) -> None:
    first = ensure_note_type(col)
    second = ensure_note_type(col)

    assert first["id"] == second["id"]
    assert len([m for m in col.models.all_names_and_ids() if m.name == NOTE_TYPE_NAME]) == 1


def test_comprehension_card_shows_the_word_and_answers_with_picture_audio_and_connection(
    cards: list[Card],
) -> None:
    question = cards[0].question()
    answer = cards[0].answer()

    assert _RUBY_WORD in question
    assert "[anki:play" not in question
    assert _PICTURE not in question
    assert _PICTURE in answer
    assert "[anki:play:a:0]" in answer
    assert _CONNECTION in answer
    assert "<hr" not in answer
    assert "to eat" not in answer


def test_production_card_shows_the_picture_and_answers_with_word_audio_and_connection(
    cards: list[Card],
) -> None:
    question = cards[1].question()
    answer = cards[1].answer()

    assert _PICTURE in question
    assert _RUBY_WORD not in question
    assert "[anki:play" not in question
    assert _RUBY_WORD in answer
    assert "[anki:play:a:0]" in answer
    assert _CONNECTION in answer
    assert "<hr" not in answer
    assert "to eat" not in answer


def test_restores_the_templates_and_css_of_an_existing_note_type(col: Collection) -> None:
    original = ensure_note_type(col)
    expected = [(t["name"], t["qfmt"], t["afmt"]) for t in original["tmpls"]], original["css"]
    for template, front in zip(original["tmpls"], ("{{Word}}", "{{Image}}")):
        template["name"] += " edited"
        template["qfmt"] = front
        template["afmt"] = "{{FrontSide}}<hr id=answer>{{Image}}"
    original["css"] = ".card {}"
    col.models.update_dict(original)

    restored = ensure_note_type(col)

    assert ([(t["name"], t["qfmt"], t["afmt"]) for t in restored["tmpls"]], restored["css"]) == (
        expected
    )


def test_adds_the_production_card_and_connection_to_an_older_note_type(
    col: Collection,
) -> None:
    models = col.models
    older = models.new(NOTE_TYPE_NAME)
    for name in ("Word", "Audio", "Image", "English"):
        models.add_field(older, models.new_field(name))
    template = models.new_template("Word → Picture")
    template["qfmt"] = "{{furigana:Word}}{{Audio}}"
    template["afmt"] = "{{FrontSide}}<div id=answer>{{Image}}</div>"
    models.add_template(older, template)
    models.add_dict(older)
    older_note = col.new_note(models.by_name(NOTE_TYPE_NAME))  # type: ignore[arg-type]
    older_note["Word"] = "犬[いぬ]"
    older_note["Image"] = '<img src="mieru_犬.jpg">'
    col.add_note(older_note, col.decks.get_current_id())

    notetype = ensure_note_type(col)

    assert models.field_names(notetype) == [
        "Word",
        "Audio",
        "Image",
        "English",
        "Personal Connection",
    ]
    assert [t["name"] for t in notetype["tmpls"]] == ["Comprehension", "Production"]
    older_note.load()
    assert len(older_note.cards()) == 2
