from __future__ import annotations

import time

import pytest
import requests

from mieru.core import http

_URL = "https://jisho.org/api/v1/search/words"
_INTERVAL_SECONDS = 1.1


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(time, "monotonic", fake.monotonic)
    monkeypatch.setattr(time, "sleep", fake.sleep)
    # Spacing state outlives a real process's requests; each test starts fresh.
    monkeypatch.setattr(http, "_pacers", {})
    return fake


def _response(status: int, headers: dict[str, str] | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.url = _URL
    if headers is not None:
        response.headers.update(headers)
    return response


def _serve(monkeypatch: pytest.MonkeyPatch, *responses: requests.Response) -> list[float]:
    starts: list[float] = []
    queue = list(responses)

    def get(*_args: object, **_kwargs: object) -> requests.Response:
        starts.append(time.monotonic())
        return queue.pop(0)

    monkeypatch.setattr(requests, "get", get)
    return starts


def test_spaces_requests_to_a_host_that_asks_for_an_interval(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    starts = _serve(monkeypatch, _response(200), _response(200))

    http.get(_URL, {"keyword": "dog"}, min_interval=_INTERVAL_SECONDS)
    http.get(_URL, {"keyword": "cat"}, min_interval=_INTERVAL_SECONDS)

    assert starts[1] - starts[0] == pytest.approx(_INTERVAL_SECONDS)


def test_keeps_requests_to_a_host_without_an_interval_together(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    starts = _serve(monkeypatch, _response(200), _response(200))

    http.get("https://cdn.pixabay.com/photo.jpg")
    http.get("https://cdn.pixabay.com/photo.jpg")

    assert starts[1] == starts[0]
    assert clock.sleeps == []


def test_retries_a_rate_limited_request_after_a_backoff(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    starts = _serve(monkeypatch, _response(429), _response(200))

    response = http.get(_URL)

    assert response.status_code == 200
    assert len(starts) == 2
    assert clock.sleeps == pytest.approx([2.0])


def test_waits_the_delay_the_server_asks_for(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    _serve(monkeypatch, _response(429, {"Retry-After": "5"}), _response(200))

    http.get(_URL)

    assert clock.sleeps == pytest.approx([5.0])


def test_gives_up_after_three_rate_limited_attempts(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    starts = _serve(monkeypatch, _response(429), _response(429), _response(429))

    with pytest.raises(requests.HTTPError) as raised:
        http.get(_URL)

    assert len(starts) == 3
    assert raised.value.response is not None
    assert raised.value.response.status_code == 429
    assert clock.sleeps == pytest.approx([2.0, 4.0])
