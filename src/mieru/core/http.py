"""Shared HTTP access so every external source gets the same timeout and headers."""

from __future__ import annotations

from typing import Any

import requests

TIMEOUT_SECONDS = 15
# Google's TTS endpoint rejects requests without a browser-like User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (mieru Anki add-on)"}


def get(
    url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
) -> requests.Response:
    response = requests.get(
        url, params=params, headers={**_HEADERS, **(headers or {})}, timeout=TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response
