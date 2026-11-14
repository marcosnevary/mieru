"""Picture search on Pixabay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import requests

from . import http

_PIXABAY_URL = "https://pixabay.com/api/"
_RESULTS_PER_PAGE = 24


class InvalidApiKeyError(Exception):
    def __init__(self, source: str) -> None:
        super().__init__(f"{source} rejected the API key")
        self.source = source


@dataclass(frozen=True)
class ImageResult:
    preview_url: str
    # Pixabay's 640px rendition: large enough for a card, small enough for the
    # collection. Its URL expires after 24 hours, so it is downloaded on add.
    image_url: str
    credit: str


def search_pixabay(query: str, api_key: str) -> list[ImageResult]:
    params = {
        "key": api_key,
        "q": query,
        "image_type": "all",
        "safesearch": "true",
        "per_page": _RESULTS_PER_PAGE,
    }
    try:
        response = http.get(_PIXABAY_URL, params)
    except requests.HTTPError as error:
        # Pixabay reports a bad key as a plain-text 400 rather than a JSON error.
        if error.response is not None and "API key" in error.response.text:
            raise InvalidApiKeyError("Pixabay") from error
        raise
    return parse_pixabay(response.json())


def parse_pixabay(payload: dict[str, Any]) -> list[ImageResult]:
    return [
        ImageResult(
            preview_url=hit["previewURL"],
            image_url=hit["webformatURL"],
            credit=f"{hit['user']} on Pixabay",
        )
        for hit in payload["hits"]
    ]


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    config_key: str
    search: Callable[[str, str], list[ImageResult]]


SOURCES = (Source("Pixabay", "https://pixabay.com/", "pixabay_api_key", search_pixabay),)


def download(url: str) -> bytes:
    return http.get(url).content
