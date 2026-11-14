"""Convert a word and its kana reading into Anki's `{{furigana:}}` field syntax."""

from __future__ import annotations

import re
from itertools import groupby

_KATAKANA = range(0x30A1, 0x30F7)
_KATAKANA_TO_HIRAGANA_OFFSET = 0x60


def _is_kana(char: str) -> bool:
    return "\u3040" <= char <= "\u30ff"


def _to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(char) - _KATAKANA_TO_HIRAGANA_OFFSET) if ord(char) in _KATAKANA else char
        for char in text
    )


def to_anki_furigana(word: str, reading: str) -> str:
    """Return `word` with the reading attached only to its kanji runs.

    "食べる", "たべる" -> "食[た]べる"; "取り扱い", "とりあつかい" -> "取[と]り 扱[あつか]い".
    """
    if word == reading or all(_is_kana(char) for char in word):
        return word

    runs = ["".join(chars) for _, chars in groupby(word, key=_is_kana)]
    # Kana runs must appear verbatim in the reading, so they anchor where each kanji
    # run's reading starts and ends. Both sides are compared in hiragana because the
    # dictionary may spell okurigana and reading in different scripts.
    pattern = "".join(re.escape(_to_hiragana(run)) if _is_kana(run[0]) else "(.+?)" for run in runs)
    match = re.fullmatch(pattern, _to_hiragana(reading))
    if match is None:
        return f"{word}[{reading}]"

    parts = []
    group = 1
    for run in runs:
        if _is_kana(run[0]):
            parts.append(run)
            continue
        start, end = match.span(group)
        group += 1
        # Anki's ruby base extends back to the previous space, so every kanji run
        # after the first character needs one to avoid swallowing preceding kana.
        separator = " " if parts else ""
        parts.append(f"{separator}{run}[{reading[start:end]}]")
    return "".join(parts)
