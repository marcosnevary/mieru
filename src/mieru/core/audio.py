"""Pronunciation audio: native JapanesePod101 recordings, Google TTS as fallback."""

from __future__ import annotations

import hashlib

import requests

from . import http

_JAPANESEPOD101_URL = "https://assets.languagepod101.com/dictionary/japanese/audiomp3.php"
# JapanesePod101 answers missing words with HTTP 200 and a fixed "audio not available" clip.
_JAPANESEPOD101_MISSING_MD5 = "7e2c2f954ef6051373ba916f000168dc"
_GOOGLE_TTS_URL = "https://translate.google.com/translate_tts"


def fetch_audio(word: str, reading: str) -> bytes | None:
    """Return an MP3 of the pronunciation, or None when no source has one."""
    return _from_japanesepod101(word, reading) or _from_google_tts(reading)


def _from_japanesepod101(word: str, reading: str) -> bytes | None:
    try:
        audio = http.get(_JAPANESEPOD101_URL, {"kanji": word, "kana": reading}).content
    except requests.RequestException:
        return None
    if hashlib.md5(audio).hexdigest() == _JAPANESEPOD101_MISSING_MD5:
        return None
    return audio or None


def _from_google_tts(reading: str) -> bytes | None:
    try:
        audio = http.get(
            _GOOGLE_TTS_URL,
            {"ie": "UTF-8", "tl": "ja", "client": "tw-ob", "q": reading},
        ).content
    except requests.RequestException:
        return None
    return audio or None
