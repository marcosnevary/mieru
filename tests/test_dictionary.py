from __future__ import annotations

import pytest
import requests
from conftest import load_fixture

from mieru.core import dictionary, http
from mieru.core.dictionary import is_japanese, parse_jisho, reading_of, search, split_queries


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


@pytest.mark.parametrize("text", ["犬", "いぬ", "トマト", "取り扱い", "時々", "食べる"])
def test_accepts_japanese_words(text: str) -> None:
    assert is_japanese(text)


@pytest.mark.parametrize("text", ["", "dog", "犬 猫", "犬です。", " 犬"])
def test_rejects_anything_that_is_not_a_japanese_word(text: str) -> None:
    assert not is_japanese(text)


def test_reads_a_kana_word_as_itself_without_a_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_english: str) -> list[dictionary.Candidate]:
        raise AssertionError("kana needs no dictionary lookup")

    monkeypatch.setattr(dictionary, "search", fail)

    assert reading_of("トマト") == "トマト"


def test_reads_a_kanji_word_from_its_exact_dictionary_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = parse_jisho(load_fixture("jisho_dog.json"))
    monkeypatch.setattr(dictionary, "search", lambda _word: candidates)

    assert reading_of("犬") == "いぬ"


def test_has_no_reading_for_a_word_the_dictionary_does_not_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = parse_jisho(load_fixture("jisho_dog.json"))
    monkeypatch.setattr(dictionary, "search", lambda _word: candidates)

    assert reading_of("食べた") is None


def test_splits_a_word_list_on_commas_and_line_breaks() -> None:
    assert split_queries("dog, cat\nnice to meet you") == ["dog", "cat", "nice to meet you"]


def test_keeps_a_single_word_as_is() -> None:
    assert split_queries("  dog ") == ["dog"]


def test_drops_empty_and_repeated_words() -> None:
    assert split_queries("dog,, cat,\n\ndog, ") == ["dog", "cat"]


def test_spaces_lookups_to_stay_under_the_jisho_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intervals: list[float] = []

    def fake_get(
        _url: str, _params: object = None, *, min_interval: float = 0.0
    ) -> requests.Response:
        intervals.append(min_interval)
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"meta": {"status": 200}, "data": []}'
        return response

    monkeypatch.setattr(http, "get", fake_get)

    search("dog")
    search("cat")

    assert intervals and all(interval > 0 for interval in intervals)
