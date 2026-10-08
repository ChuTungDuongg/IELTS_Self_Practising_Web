"""Chart label formatting is transport syntax; authoritative values stay Decimal."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.task1_visual import Point, TableCell


@pytest.mark.parametrize("model", [Point, TableCell])
@pytest.mark.parametrize(
    "raw,expected",
    [
        (48, "48"),
        (48.0, "48.0"),
        ("48", "48"),
        ("48.0", "48.0"),
        ("48%", "48"),
        ("48 %", "48"),
        ("39 %", "39"),
        ("1,200", "1200"),
        ("1,200.5", "1200.5"),
        ("1,200.50%", "1200.50"),
        (" -1,200.50 % ", "-1200.50"),
        (".125", ".125"),
        ("1e-8", "1e-8"),
        (Decimal("48.00"), "48.00"),
        (None, None),
    ],
)
def test_point_and_table_share_safe_visual_number_normalization(model, raw, expected):
    labels = (
        {"category": "Fictional"} if model is Point else {"row": "Fictional", "column": "Count"}
    )
    item = model.model_validate({**labels, "value": raw, "confidence": 0.95})
    if expected is None:
        assert item.value is None
    else:
        assert isinstance(item.value, Decimal)
        assert item.value.as_tuple() == Decimal(expected).as_tuple()


@pytest.mark.parametrize("model", [Point, TableCell])
@pytest.mark.parametrize(
    "raw",
    [
        "about 48%",
        "roughly fifty",
        "48 percent approximately",
        "10-20",
        "forty eight",
        "unknown",
        "high",
        "",
        {},
        [],
        True,
        False,
        "1,20",
        "12,00.5",
        "1.200,50",
        "1 200",
        "48%%",
        "48 % more",
        "٤٨%",
        "9" * 200,
        "NaN",
        "Infinity",
        float("nan"),
        float("inf"),
        "1000000000001%",
        "0.123456789%",
    ],
)
def test_visual_number_rejects_prose_ambiguous_format_and_domain_bound_violations(model, raw):
    labels = (
        {"category": "Fictional"} if model is Point else {"row": "Fictional", "column": "Count"}
    )
    with pytest.raises(ValidationError):
        model.model_validate({**labels, "value": raw, "confidence": 0.95})


def test_visual_number_serialization_and_decimal_arithmetic_remain_exact():
    item = Point(category="Fictional", value="0.1%", confidence=0.95)
    assert item.value + Decimal("0.2") == Decimal("0.3")
    assert item.model_dump(mode="json")["value"] == "0.1"
