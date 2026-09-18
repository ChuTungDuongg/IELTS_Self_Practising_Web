import re

WORD_PATTERN = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)


def count_words(text: str) -> int:
    """Count Unicode letter/number words, retaining inner apostrophes and hyphens."""
    return len(WORD_PATTERN.findall(text))
