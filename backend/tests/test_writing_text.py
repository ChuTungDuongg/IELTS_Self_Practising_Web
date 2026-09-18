from app.domains.writing import count_words


def test_word_count_handles_whitespace_and_punctuation() -> None:
    assert count_words("  The chart, illustrates\nsolar-power growth. ") == 5


def test_word_count_handles_unicode_and_apostrophes() -> None:
    assert count_words("It’s a city's plan for Đà Nẵng.") == 7


def test_word_count_ignores_punctuation_only() -> None:
    assert count_words("... — !!!") == 0
