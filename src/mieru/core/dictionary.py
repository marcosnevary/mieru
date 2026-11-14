"""English -> Japanese candidates from Jisho.org, which serves JMdict."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import http

_JISHO_SEARCH_URL = "https://jisho.org/api/v1/search/words"


@dataclass(frozen=True)
class Candidate:
    word: str
    reading: str
    meanings: tuple[str, ...]
    is_common: bool


def search(english: str) -> list[Candidate]:
    return parse_jisho(http.get(_JISHO_SEARCH_URL, {"keyword": english}).json())


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
