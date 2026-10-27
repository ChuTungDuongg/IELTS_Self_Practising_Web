"""Accent-insensitive feed search without an optional PostgreSQL extension."""

import unicodedata

from sqlalchemy import func

from app.core.exceptions import AppError

_GROUPS = {
    "a": "àáạảãâầấậẩẫăằắặẳẵ",
    "e": "èéẹẻẽêềếệểễ",
    "i": "ìíịỉĩ",
    "o": "òóọỏõôồốộổỗơờớợởỡ",
    "u": "ùúụủũưừứựửữ",
    "y": "ỳýỵỷỹ",
    "d": "đ",
}
_ACCENTS = "".join(_GROUPS.values())
_PLAIN = "".join(letter * len(values) for letter, values in _GROUPS.items())


def normalize_feed_search(value: str | None) -> str:
    if value is not None and len(value) > 200:
        raise AppError("INVALID_FEED_SEARCH", "Search must be at most 200 characters.", 422)
    decomposed = unicodedata.normalize("NFD", (value or "").casefold().replace("đ", "d"))
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def search_feed(query, search: str, *columns):
    if not search:
        return query
    text = func.regexp_replace(
        func.translate(func.lower(func.concat_ws(" ", *columns)), _ACCENTS, _PLAIN),
        "[\u0300-\u036f]",
        "",
        "g",
    )
    for word in search.split():
        query = query.where(text.contains(word, autoescape=True))
    return query
