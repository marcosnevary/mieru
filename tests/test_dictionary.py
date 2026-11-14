from conftest import load_fixture

from mieru.core.dictionary import parse_jisho, split_queries


def test_lists_common_words_before_phrases_containing_the_query() -> None:
    candidates = parse_jisho(load_fixture("jisho_dog.json"))

    dog = candidates[0]
    assert (dog.word, dog.reading, dog.is_common) == ("犬", "いぬ", True)
    assert dog.meanings[0] == "dog (Canis (lupus) familiaris), canine"
    assert [c.is_common for c in candidates] == sorted(
        (c.is_common for c in candidates), reverse=True
    )


def test_offers_every_sense_of_an_ambiguous_word() -> None:
    words = [c.word for c in parse_jisho(load_fixture("jisho_bank.json"))]

    assert "銀行" in words
    assert "土手" in words


def test_uses_reading_as_word_for_kana_only_entries() -> None:
    tomato = parse_jisho(load_fixture("jisho_tomato.json"))[0]

    assert (tomato.word, tomato.reading) == ("トマト", "トマト")


def test_returns_nothing_for_unknown_words() -> None:
    assert parse_jisho({"meta": {"status": 200}, "data": []}) == []


def test_skips_entries_without_a_reading() -> None:
    words = [c.word for c in parse_jisho(load_fixture("jisho_tomato.json"))]

    assert "トマト缶" not in words


def test_splits_a_word_list_on_commas_and_line_breaks() -> None:
    assert split_queries("dog, cat\nnice to meet you") == ["dog", "cat", "nice to meet you"]


def test_keeps_a_single_word_as_is() -> None:
    assert split_queries("  dog ") == ["dog"]


def test_drops_empty_and_repeated_words() -> None:
    assert split_queries("dog,, cat,\n\ndog, ") == ["dog", "cat"]
