from conftest import load_fixture

from mieru.core.images import ImageResult, parse_pixabay


def test_uses_preview_for_thumbnails_and_web_format_for_the_card() -> None:
    results = parse_pixabay(load_fixture("pixabay_dog.json"))

    assert results[0] == ImageResult(
        preview_url="https://cdn.pixabay.com/photo/2016/01/05/17/51/dog-1123016_150.jpg",
        image_url="https://pixabay.com/get/g1a2b3c_640.jpg",
    )
    assert len(results) == 2
