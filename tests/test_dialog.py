from __future__ import annotations

import requests

from mieru.ui.dialog import _network_error_message


def _error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response.url = "https://jisho.org/api/v1/search/words"
    return requests.HTTPError(response=response)


def test_explains_a_rate_limited_server() -> None:
    assert _network_error_message(_error(429)) == (
        "The server is limiting requests right now. Wait a minute and search again."
    )


def test_reports_other_failures_as_an_unreachable_server() -> None:
    assert _network_error_message(requests.ConnectionError()).startswith(
        "Could not reach the server:"
    )
