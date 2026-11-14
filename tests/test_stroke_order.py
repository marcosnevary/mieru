from __future__ import annotations

from typing import Any

import pytest
import requests

from mieru.core import http, stroke_order


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content


def serve(monkeypatch: pytest.MonkeyPatch, by_file: dict[str, bytes | Exception]) -> list[str]:
    requested: list[str] = []

    def fake_get(url: str, params: dict[str, Any] | None = None) -> FakeResponse:
        requested.append(url)
        outcome = by_file.get(url.rsplit("/", 1)[-1], requests.HTTPError("404"))
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    monkeypatch.setattr(http, "get", fake_get)
    return requested


def test_returns_a_diagram_per_character_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    requested = serve(
        monkeypatch,
        {
            "098df.svg": b"<svg>shoku</svg>",
            "03079.svg": b"<svg>be</svg>",
            "0308b.svg": b"<svg>ru</svg>",
        },
    )

    assert stroke_order.fetch_stroke_order("食べる") == [
        ("食", b"<svg>shoku</svg>"),
        ("べ", b"<svg>be</svg>"),
        ("る", b"<svg>ru</svg>"),
    ]
    assert (
        requested[0] == "https://raw.githubusercontent.com/KanjiVG/kanjivg/master/kanji/098df.svg"
    )


def test_downloads_a_repeated_character_once(monkeypatch: pytest.MonkeyPatch) -> None:
    requested = serve(monkeypatch, {"07530.svg": b"<svg>ta</svg>"})

    assert stroke_order.fetch_stroke_order("田田") == [("田", b"<svg>ta</svg>")]
    assert len(requested) == 1


def test_leaves_out_missing_and_failed_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, {"072ac.svg": b"<svg>inu</svg>", "03092.svg": requests.ConnectionError()})

    assert stroke_order.fetch_stroke_order("犬をA") == [("犬", b"<svg>inu</svg>")]
