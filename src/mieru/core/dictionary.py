"""English -> Japanese candidates from Jisho.org, which serves JMdict."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import http
from .furigana import is_kana

_JISHO_SEARCH_URL = "https://jisho.org/api/v1/search/words"
# Jisho answers 429 above 10 requests per 10 seconds; a word list asks for every
# word at once, so the requests are spaced out instead of fired together.
_JISHO_REQUEST_INTERVAL_SECONDS = 1.1
# Kana, kanji, the iteration marks 々 and 〆.
_JAPANESE_TEXT = re.compile(r"[\u3005\u3006\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]+")


@dataclass(frozen=True)
class Candidate:
    word: str
    reading: str
    meanings: tuple[str, ...]
    is_common: bool


def split_queries(text: str) -> list[str]:
    queries = (query.strip() for query in re.split(r"[,\n]", text))
    return list(dict.fromkeys(query for query in queries if query))


def is_japanese(text: str) -> bool:
    return _JAPANESE_TEXT.fullmatch(text) is not None


def search(english: str) -> list[Candidate]:
    response = http.get(
        _JISHO_SEARCH_URL,
        {"keyword": english},
        min_interval=_JISHO_REQUEST_INTERVAL_SECONDS,
    )
    return parse_jisho(response.json())


def reading_of(word: str) -> str | None:
    """The kana reading of a Japanese word, or None when Jisho doesn't list the word as written."""
    if all(is_kana(char) for char in word):
        return word
    # Jisho also returns phrases containing the word, so only an exact match counts;
    # another entry's reading would give the wrong pronunciation.
    return next((c.reading for c in search(word) if c.word == word), None)


def parse_jisho(payload: dict[str, Any]) -> list[Candidate]:
    candidates = []
    for entry in payload["data"]:
        japanese = entry["japanese"][0]
        # Entries Jisho imports from Wikipedia may lack a reading, which furigana
        # and audio both need.
        reading = japanese.get("reading")
        if reading is None:
            continue
        candidates.append(
            Candidate(
                # Words usually written in kana have no "word" key.
                word=japanese.get("word", reading),
                reading=reading,
                meanings=tuple(
                    ", ".join(sense["english_definitions"]) for sense in entry["senses"]
                ),
                is_common=entry.get("is_common", False),
            )
        )
    # Jisho ranks phrases that merely contain the query (犬の顔 for "dog") above the
    # word itself; common words first keeps Jisho's order within each group.
    return sorted(candidates, key=lambda candidate: not candidate.is_common)
