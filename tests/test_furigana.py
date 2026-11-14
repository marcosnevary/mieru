import pytest

from mieru.core.furigana import to_anki_furigana


@pytest.mark.parametrize(
    ("word", "reading", "expected"),
    [
        ("犬", "いぬ", "犬[いぬ]"),
        ("銀行", "ぎんこう", "銀行[ぎんこう]"),
        ("食べる", "たべる", "食[た]べる"),
        ("取り扱い", "とりあつかい", "取[と]り 扱[あつか]い"),
        ("お茶", "おちゃ", "お 茶[ちゃ]"),
        ("時々", "ときどき", "時々[ときどき]"),
        ("気持ち", "きもち", "気持[きも]ち"),
        ("トックリ形", "とっくりけい", "トックリ 形[けい]"),
        ("トマト", "トマト", "トマト"),
        ("りんご", "りんご", "りんご"),
    ],
)
def test_attaches_reading_to_kanji_runs(word: str, reading: str, expected: str) -> None:
    assert to_anki_furigana(word, reading) == expected


def test_falls_back_to_whole_word_when_reading_does_not_align() -> None:
    assert to_anki_furigana("食べる", "くう") == "食べる[くう]"
