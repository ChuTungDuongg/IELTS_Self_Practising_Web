from decimal import Decimal

import pytest

from app.domains.scoring.writing import (
    calculate_final_writing_band,
    calculate_task_overall,
    calculate_weighted_writing_overall,
    validate_writing_criterion_score,
)


def test_writing_task_and_weighted_overalls_keep_decimal_precision() -> None:
    task_one = calculate_task_overall(
        Decimal("7.0"), Decimal("6.5"), Decimal("7.0"), Decimal("6.5")
    )
    task_two = calculate_task_overall(
        Decimal("7.0"), Decimal("7.0"), Decimal("7.0"), Decimal("7.0")
    )

    assert task_one == Decimal("6.75")
    assert task_two == Decimal("7.00")
    weighted = calculate_weighted_writing_overall(task_one, task_two)
    assert weighted == (Decimal("6.75") + Decimal("14.00")) / Decimal(3)
    assert calculate_final_writing_band(weighted) == Decimal("7.0")


def test_task_two_has_exactly_double_weight() -> None:
    task_one = calculate_task_overall(*([Decimal("6.0")] * 4))
    task_two = calculate_task_overall(*([Decimal("7.5")] * 4))

    assert calculate_weighted_writing_overall(task_one, task_two) == Decimal("7.0")
    assert calculate_final_writing_band(Decimal("7.0")) == Decimal("7.0")


@pytest.mark.parametrize("value", ["0.0", "0.5", "7.0", "7.5", "9.0"])
def test_valid_half_band_criterion_scores(value: str) -> None:
    assert validate_writing_criterion_score(Decimal(value)) == Decimal(value)


@pytest.mark.parametrize("value", ["-0.5", "7.25", "9.5"])
def test_invalid_criterion_scores(value: str) -> None:
    with pytest.raises(ValueError):
        validate_writing_criterion_score(Decimal(value))


def test_weighted_result_is_incomplete_until_both_tasks_exist() -> None:
    assert calculate_weighted_writing_overall(Decimal("7.0"), None) is None
    assert calculate_weighted_writing_overall(None, Decimal("7.0")) is None
    assert calculate_final_writing_band(None) is None
