"""Stroke order diagrams from KanjiVG: one SVG per character, strokes numbered in order."""

from __future__ import annotations

import requests

from . import http

# KanjiVG is CC BY-SA 3.0; each SVG keeps its copyright header, which is the
# attribution the licence asks for.
_KANJIVG_URL = "https://raw.githubusercontent.com/KanjiVG/kanjivg/master/kanji/{code:05x}.svg"


def fetch_stroke_order(word: str) -> list[tuple[str, bytes]]:
    """Return (character, SVG) for each distinct character of `word`, in order.

    Characters KanjiVG lacks or that fail to download are left out, so a word is
    never held back by its stroke order.
    """
    diagrams = []
    for character in dict.fromkeys(word):
        try:
            svg = http.get(_KANJIVG_URL.format(code=ord(character))).content
        except requests.RequestException:
            continue
        if svg:
            diagrams.append((character, svg))
    return diagrams
