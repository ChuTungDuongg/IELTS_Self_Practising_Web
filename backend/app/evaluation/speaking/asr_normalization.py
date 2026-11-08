"""Versioned research token normalization. Legacy replay CLI behavior is unchanged."""

import unicodedata

from app.evaluation.speaking.hybrid import _tokens

NORMALIZATION = "asr-research-nfc-casefold-words-v2"


def normalized_text(text):
    return " ".join(_tokens(unicodedata.normalize("NFC", text).casefold()))
