from decimal import Decimal

import pytest

from app.domains.scoring.ielts_band import (
    listening_raw_to_band,
    project_overall_band,
    reading_raw_to_band,
    round_to_half,
)

PRODUCT_BANDS = {
    40: 9.0,
    39: 9.0,
    38: 8.5,
    37: 8.5,
    36: 8.0,
    35: 8.0,
    34: 7.5,
    33: 7.5,
    32: 7.0,
    30: 7.0,
    29: 6.5,
    27: 6.5,
    26: 6.0,
    23: 6.0,
    22: 5.5,
    20: 5.5,
    19: 5.0,
    16: 5.0,
    15: 4.5,
    13: 4.5,
    12: 4.0,
    10: 4.0,
    9: 3.5,
    7: 3.5,
    6: 3.0,
    5: 3.0,
    4: 2.5,
    3: 2.5,
    2: None,
    0: None,
}


@pytest.mark.parametrize(("raw_score", "expected"), PRODUCT_BANDS.items())
def test_reading_and_listening_use_the_product_band_table(
    raw_score: int, expected: float | None
) -> None:
    assert reading_raw_to_band(raw_score, 40) == expected
    assert listening_raw_to_band(raw_score, 40) == expected


@pytest.mark.parametrize("converter", [reading_raw_to_band, listening_raw_to_band])
def test_non_standard_objective_module_has_no_official_band(converter) -> None:
    assert converter(20, 30) is None


@pytest.mark.parametrize(
    ("raw_score", "max_score"),
    [(-1, 40), (41, 40), (1, 0), (0, -1)],
)
@pytest.mark.parametrize("converter", [reading_raw_to_band, listening_raw_to_band])
def test_invalid_score_shape_is_rejected(converter, raw_score: int, max_score: int) -> None:
    with pytest.raises(ValueError):
        converter(raw_score, max_score)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("7.24"), Decimal("7.0")),
        (Decimal("7.25"), Decimal("7.5")),
        (Decimal("7.74"), Decimal("7.5")),
        (Decimal("7.75"), Decimal("8.0")),
    ],
)
def test_round_to_half_uses_decimal_half_up(value: Decimal, expected: Decimal) -> None:
    assert round_to_half(value) == expected


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ((7.0, 7.5, 6.5), 7.0),
        ((7.0, 7.0, 7.5), 7.0),
        ((7.5, 7.5, 7.0), 7.5),
        ((None, 7.5, 7.0), None),
    ],
)
def test_project_overall_requires_three_bands_and_rounds_once(
    scores: tuple[float | None, float | None, float | None], expected: float | None
) -> None:
    assert project_overall_band(*scores) == expected
