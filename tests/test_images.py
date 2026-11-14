import pytest
import requests
from conftest import load_fixture

from mieru.core import http, images
from mieru.core.images import ImageResult, InvalidApiKeyError, parse_pexels, parse_pixabay


def test_uses_preview_for_thumbnails_and_web_format_for_the_card() -> None:
    results = parse_pixabay(load_fixture("pixabay_dog.json"))

    assert results[0] == ImageResult(
        preview_url="https://cdn.pixabay.com/photo/2016/01/05/17/51/dog-1123016_150.jpg",
        image_url="https://pixabay.com/get/g1a2b3c_640.jpg",
        credit="Lum3n on Pixabay",
    )
    assert len(results) == 2


def test_uses_small_pexels_photo_for_thumbnails_and_large_for_the_card() -> None:
    results = parse_pexels(load_fixture("pexels_handshake.json"))

    photo = "https://images.pexels.com/photos/3184291/pexels-photo-3184291.jpeg"
    assert results[0] == ImageResult(
        preview_url=f"{photo}?auto=compress&cs=tinysrgb&h=130",
        image_url=f"{photo}?auto=compress&cs=tinysrgb&h=650&w=940",
        credit="Photo by fauxels on Pexels",
    )
    assert len(results) == 2


def test_reports_a_rejected_pexels_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args: object, **_kwargs: object) -> requests.Response:
        response = requests.Response()
        response.status_code = 401
        raise requests.HTTPError(response=response)

    monkeypatch.setattr(http, "get", reject)

    with pytest.raises(InvalidApiKeyError) as raised:
        images.search_pexels("handshake", "bad-key")
    assert raised.value.source == "Pexels"
