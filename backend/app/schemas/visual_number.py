"""Bounded chart-label syntax to Decimal; never infer numbers from prose."""

import re
from decimal import Decimal

from pydantic_core import PydanticCustomError

_NUMBER = re.compile(
    r"[+-]?(?:(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE][+-]?[0-9]{1,3})?"
)


def parse_visual_number(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise PydanticCustomError("decimal_type", "Expected a numeric visual value")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        # Convert Python numeric inputs through decimal text, not float arithmetic.
        return Decimal(str(value))
    if len(value) > 64:
        raise PydanticCustomError("decimal_parsing", "Invalid visual number format")
    numeric = value.strip().removesuffix("%").strip()
    if not _NUMBER.fullmatch(numeric):
        raise PydanticCustomError("decimal_parsing", "Invalid visual number format")
    # Percentages stay in chart units: 48% -> 48, never 0.48.
    # Magnitude/precision/finiteness are still enforced by the domain Number.
    return Decimal(numeric.replace(",", ""))
