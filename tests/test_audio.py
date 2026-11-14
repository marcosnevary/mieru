from __future__ import annotations

import hashlib
from typing import Any

import pytest
import requests

from mieru.core import audio, http

JAPANESEPOD101_MISSING_CLIP = b"placeholder"


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content


def serve(monkeypatch: pytest.MonkeyPatch, by_host: dict[str, bytes | Exception]) -> None:
    def fake_get(url: str, params: dict[str, Any] | None = None) -> FakeResponse:
        for host, outcome in by_host.items():
            if host in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return FakeResponse(outcome)
        raise AssertionError(f"unexpected request to {url}")

    monkeypatch.setattr(http, "get", fake_get)
    monkeypatch.setattr(
        audio,
        "_JAPANESEPOD101_MISSING_MD5",
        hashlib.md5(JAPANESEPOD101_MISSING_CLIP).hexdigest(),
    )


def test_prefers_native_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, {"languagepod101": b"native", "google": b"tts"})

    assert audio.fetch_audio("犬", "いぬ") == b"native"


def test_falls_back_to_tts_when_recording_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve(monkeypatch, {"languagepod101": JAPANESEPOD101_MISSING_CLIP, "google": b"tts"})

    assert audio.fetch_audio("犬の顔", "いぬのかお") == b"tts"


def test_falls_back_to_tts_when_japanesepod101_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve(monkeypatch, {"languagepod101": requests.ConnectionError(), "google": b"tts"})

    assert audio.fetch_audio("犬", "いぬ") == b"tts"


def test_returns_none_when_every_source_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    serve(
        monkeypatch,
        {"languagepod101": JAPANESEPOD101_MISSING_CLIP, "google": requests.HTTPError()},
    )

    assert audio.fetch_audio("犬", "いぬ") is None
