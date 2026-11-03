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


def test_final_writing_band_uses_raw_task_means_without_double_rounding() -> None:
    task_one = calculate_task_overall(*(Decimal(v) for v in ("6", "6", "6", "6.5")))
    task_two = calculate_task_overall(*(Decimal(v) for v in ("6", "6", "6.5", "6.5")))
    assert task_one == Decimal("6.125")
    assert task_two == Decimal("6.25")
    weighted = calculate_weighted_writing_overall(task_one, task_two)
    assert weighted == (Decimal("6.125") + 2 * Decimal("6.25")) / 3
    assert calculate_final_writing_band(weighted) == Decimal("6.0")


@pytest.mark.parametrize(
    ("criteria", "raw", "band"),
    [
        (("5", "5", "4", "4.5"), "4.625", 4.5),
        (("4.5", "4.5", "5", "5"), "4.75", 5.0),
        (("6", "6", "6.5", "6.5"), "6.25", 6.5),
        (("6.5", "6.5", "7", "7"), "6.75", 7.0),
        (("7", "7", "7", "7.5"), "7.125", 7.0),
        (("7.5", "8", "8", "8"), "7.875", 8.0),
        (("0", "0", "0", "0"), "0", 0.0),
        (("9", "9", "9", "9"), "9", 9.0),
    ],
)
def test_writing_score_dto_preserves_raw_mean_and_derives_task_band(criteria, raw, band):
    from app.models import AttemptWritingScore
    from app.services.attempts import AttemptService

    score = AttemptWritingScore(
        **dict(zip(("ta", "cc", "lr", "gra"), map(Decimal, criteria), strict=True))
    )
    payload = AttemptService._present_writing_score(score).model_dump(mode="json")
    assert payload["overall"] == float(raw)
    assert payload["task_band"] == band
    assert [payload[key] for key in ("ta", "cc", "lr", "gra")] == list(map(float, criteria))
