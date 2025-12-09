from diary_files import extract_date_info_from_source, is_diary_filename


def test_is_diary_filename_true_for_japanese_format():
    assert is_diary_filename("2025年05月15日(木).md")


def test_is_diary_filename_false_for_non_diary_name():
    assert not is_diary_filename("note.md")


def test_extract_date_info_from_source_for_japanese_diary():
    info = extract_date_info_from_source("2025年05月15日(木).md")
    assert info is not None
    assert info["date"] == "2025-05-15"
    assert info["year"] == 2025
    assert info["month"] == 5
    assert info["day"] == 15
    assert 0 <= info["dayOfWeek"] <= 6


def test_extract_date_info_from_source_returns_none_for_invalid():
    assert extract_date_info_from_source("note.md") is None
