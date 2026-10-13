"""Pure Writing score agreement and production overall arithmetic."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from app.domains.scoring.ai_writing import aggregate_ai_task_two

TRAITS = ("ta", "cc", "lr", "gra")


def overall_score(
    scores: Mapping[str, Decimal | None], *, traits: tuple[str, ...] = TRAITS
) -> Decimal | None:
    """Use the same four-criterion mean and half-up rounding as production."""
    values = [scores.get(trait) for trait in traits]
    if any(value is None for value in values):
        return None
    _, overall = aggregate_ai_task_two(*(value for value in values if value is not None))
    return overall


def score_metrics(
    pairs: Sequence[tuple[Decimal, Decimal]], *, minimum_qwk_samples: int = 10
) -> dict[str, Any]:
    """Agreement and signed predicted-minus-human error, without calibrating scores.

    QWK uses all 19 official half-band categories from 0 to 9, including empty
    categories. Non-half-band human averages retain their exact error metrics;
    their QWK is unavailable rather than silently quantizing their labels.
    """
    if minimum_qwk_samples < 1:
        raise ValueError("minimum_qwk_samples must be positive")
    for target, predicted in pairs:
        if any(
            not score.is_finite() or not Decimal(0) <= score <= Decimal(9)
            for score in (target, predicted)
        ):
            raise ValueError("Benchmark scores must be finite and between 0 and 9")
    count = len(pairs)
    result: dict[str, Any] = dict.fromkeys(
        (
            "exact_agreement",
            "within_0_5",
            "within_1_0",
            "signed_bias",
            "mae",
            "rmse",
            "quadratic_weighted_kappa",
        )
    )
    result["count"] = count
    if not count:
        result["qwk_status"] = "no_samples"
        return result
    errors = [predicted - target for target, predicted in pairs]
    absolute = [abs(error) for error in errors]
    result.update(
        exact_agreement=sum(error == 0 for error in errors) / count,
        within_0_5=sum(error <= Decimal("0.5") for error in absolute) / count,
        within_1_0=sum(error <= 1 for error in absolute) / count,
        signed_bias=float(sum(errors, Decimal(0)) / count),
        mae=float(sum(absolute, Decimal(0)) / count),
        rmse=float((sum((error * error for error in errors), Decimal(0)) / count).sqrt()),
    )
    if count < minimum_qwk_samples:
        result["qwk_status"] = "insufficient_samples"
        return result
    if any(score % Decimal("0.5") != 0 for pair in pairs for score in pair):
        result["qwk_status"] = "non_half_band_scores"
        return result
    targets, predictions = [0] * 19, [0] * 19
    observed_disagreement = 0
    for target, predicted in pairs:
        target_index, predicted_index = int(target * 2), int(predicted * 2)
        targets[target_index] += 1
        predictions[predicted_index] += 1
        observed_disagreement += (target_index - predicted_index) ** 2
    # The common quadratic weight divisor (18**2) cancels from the ratio.
    expected_disagreement = sum(
        targets[i] * predictions[j] * (i - j) ** 2 for i in range(19) for j in range(19)
    )
    if expected_disagreement == 0:
        result["qwk_status"] = "undefined_expected_variance"
    else:
        result["quadratic_weighted_kappa"] = float(
            1 - Decimal(count * observed_disagreement) / expected_disagreement
        )
        result["qwk_status"] = "ok"
    return result
