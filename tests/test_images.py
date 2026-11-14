import pytest
import requests
from conftest import load_fixture

from mieru.core import http, images
from mieru.core.images import ImageResult, InvalidApiKeyError, parse_pixabay


def test_uses_preview_for_thumbnails_and_web_format_for_the_card() -> None:
    results = parse_pixabay(load_fixture("pixabay_dog.json"))

    assert results[0] == ImageResult(
        preview_url="https://cdn.pixabay.com/photo/2016/01/05/17/51/dog-1123016_150.jpg",
        image_url="https://pixabay.com/get/g1a2b3c_640.jpg",
        credit="Lum3n on Pixabay",
    )
    assert len(results) == 2


def test_reports_a_rejected_pixabay_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args: object, **_kwargs: object) -> requests.Response:
        response = requests.Response()
        response.status_code = 400
        response._content = (
            b"[ERROR 400] Invalid or missing API key (https://pixabay.com/api/docs/)."
        )
        raise requests.HTTPError(response=response)

    monkeypatch.setattr(http, "get", reject)

    with pytest.raises(InvalidApiKeyError) as raised:
        images.search_pixabay("dog", "bad-key")
    assert raised.value.source == "Pixabay"
