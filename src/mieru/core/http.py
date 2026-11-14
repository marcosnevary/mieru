"""Shared HTTP access so every external source gets the same timeout and headers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

TIMEOUT_SECONDS = 15
# Google's TTS endpoint rejects requests without a browser-like User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (mieru Anki add-on)"}

# Jisho answers 429 above 10 requests per 10 seconds, and a word list asks for
# every word at once. Sources whose host needs pacing pass their interval;
# retrying a rate-limited request with a backoff turns a failed lookup into a
# slower one, and the backoff holds back every other request to that host.
_ATTEMPTS = 3
_BACKOFF_SECONDS = 2.0
_MAX_RETRY_AFTER_SECONDS = 10.0


@dataclass
class _Pacer:
    lock: threading.Lock = field(default_factory=threading.Lock)
    next_start: float = 0.0


_pacers: dict[str, _Pacer] = {}
_pacers_lock = threading.Lock()


def get(
    url: str, params: dict[str, Any] | None = None, *, min_interval: float = 0.0
) -> requests.Response:
    host = urlparse(url).hostname or ""
    retries = 0
    while True:
        _wait_turn(host, min_interval)
        response = requests.get(url, params=params, headers=_HEADERS, timeout=TIMEOUT_SECONDS)
        if response.status_code != 429 or retries == _ATTEMPTS - 1:
            response.raise_for_status()
            return response
        _back_off(host, _retry_delay(response, retries))
        retries += 1


def _pacer(host: str) -> _Pacer:
    with _pacers_lock:
        return _pacers.setdefault(host, _Pacer())


def _wait_turn(host: str, min_interval: float) -> None:
    pacer = _pacer(host)
    with pacer.lock:
        now = time.monotonic()
        start = max(now, pacer.next_start)
        pacer.next_start = start + min_interval
        if start > now:
            time.sleep(start - now)


def _back_off(host: str, delay: float) -> None:
    pacer = _pacer(host)
    with pacer.lock:
        pacer.next_start = max(pacer.next_start, time.monotonic() + delay)


def _retry_delay(response: requests.Response, retries: int) -> float:
    retry_after: str = response.headers.get("Retry-After", "")
    if retry_after.isdigit():
        return min(float(retry_after), _MAX_RETRY_AFTER_SECONDS)
    return _BACKOFF_SECONDS * 2.0**retries
