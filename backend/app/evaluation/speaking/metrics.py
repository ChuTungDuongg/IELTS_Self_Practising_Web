"""Pure offline Speaking agreement arithmetic; labels never alter scorer output.

Rates are fractions in [0, 1]. Errors are predicted minus human half-band labels.
Missing predictions count toward failure/coverage, but never enter paired metrics.
No model, database, provider, or third-party numerical dependency is required.
"""

from collections import Counter, defaultdict
from math import fsum, isfinite, sqrt
from numbers import Real
from typing import Any

METRICS_PROTOCOL_VERSION = "speaking-metrics-v1"


def _half_band(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("Scores must be numeric finite half-band values between 0 and 9")
    try:
        score = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError("Scores must be numeric finite half-band values between 0 and 9") from exc
    if not isfinite(score) or not 0 <= score <= 9 or score * 2 != int(score * 2):
        raise ValueError("Scores must be numeric finite half-band values between 0 and 9")
    return score


def _average_ranks(values: list[float]) -> list[float]:
    """Assign tied values the mean of their one-based rank positions."""
    ordered = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        average_rank = (start + 1 + end) / 2
        for position in range(start, end):
            ranks[ordered[position]] = average_rank
        start = end
    return ranks


def _correlation(targets: list[float], predictions: list[float]) -> tuple[float | None, str]:
    count = len(targets)
    target_mean, predicted_mean = fsum(targets) / count, fsum(predictions) / count
    target_delta = [value - target_mean for value in targets]
    predicted_delta = [value - predicted_mean for value in predictions]
    target_variance = fsum(value * value for value in target_delta)
    predicted_variance = fsum(value * value for value in predicted_delta)
    if not target_variance or not predicted_variance:
        return None, "constant_vector"
    covariance = fsum(a * b for a, b in zip(target_delta, predicted_delta, strict=True))
    # Roundoff can otherwise put perfect agreement just outside [-1, 1].
    return max(-1.0, min(1.0, covariance / sqrt(target_variance * predicted_variance))), "ok"


def _quadratic_weighted_kappa(
    targets: list[float], predictions: list[float]
) -> tuple[float | None, str]:
    target_counts, predicted_counts = [0] * 19, [0] * 19
    observed_disagreement = 0
    for target, predicted in zip(targets, predictions, strict=True):
        target_index, predicted_index = int(target * 2), int(predicted * 2)
        target_counts[target_index] += 1
        predicted_counts[predicted_index] += 1
        observed_disagreement += (target_index - predicted_index) ** 2
    # All 19 project half-band categories participate; the weight divisor cancels.
    expected_disagreement = sum(
        target_counts[i] * predicted_counts[j] * (i - j) ** 2 for i in range(19) for j in range(19)
    )
    if not expected_disagreement:
        return None, "undefined_expected_variance"
    return 1 - len(targets) * observed_disagreement / expected_disagreement, "ok"


def score_metrics(
    targets: list[float],
    predictions: list[float | None],
    *,
    minimum_correlation_samples: int = 3,
    minimum_qwk_samples: int = 5,
) -> dict[str, Any]:
    """Return agreement, correlations, failures, and descriptive calibration buckets.

    Validate every human label, including rows whose prediction is missing. Each
    nonmissing prediction must be a finite numeric half-band value in [0, 9].
    Null statistics carry explicit statuses: no_samples, insufficient_samples,
    constant_vector (correlations), or undefined_expected_variance (kappa).

    Error distribution and calibration buckets use only paired rows, sorted by
    signed error and exact human half-band respectively. They describe scorer
    behavior and do not apply a correction or produce a calibrated score.
    """
    for threshold in (minimum_correlation_samples, minimum_qwk_samples):
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
            raise ValueError("Metric sample thresholds must be a positive integer")
    if len(targets) != len(predictions):
        raise ValueError("Targets and predictions must have the same length")
    paired_targets, paired_predictions = [], []
    for target, predicted in zip(targets, predictions, strict=True):
        validated_target = _half_band(target)
        if predicted is not None:
            paired_targets.append(validated_target)
            paired_predictions.append(_half_band(predicted))
    total_count, count = len(targets), len(paired_targets)
    result: dict[str, Any] = dict.fromkeys(
        (
            "mae",
            "rmse",
            "pearson",
            "spearman",
            "quadratic_weighted_kappa",
            "within_0_5",
            "within_1_0",
            "exact_agreement",
            "signed_bias",
        )
    )
    result.update(
        metric_protocol_version=METRICS_PROTOCOL_VERSION,
        total_count=total_count,
        count=count,
        nonscorable_count=total_count - count,
        failure_rate=(total_count - count) / total_count if total_count else None,
        coverage_rate=count / total_count if total_count else None,
        error_distribution=[],
        calibration_buckets=[],
    )
    if not count:
        result.update(
            pearson_status="no_samples", spearman_status="no_samples", qwk_status="no_samples"
        )
        return result
    errors = [
        predicted - target
        for target, predicted in zip(paired_targets, paired_predictions, strict=True)
    ]
    absolute_errors = [abs(error) for error in errors]
    buckets: dict[float, list[float]] = defaultdict(list)
    for target, error in zip(paired_targets, errors, strict=True):
        buckets[target].append(error)
    result.update(
        mae=fsum(absolute_errors) / count,
        rmse=sqrt(fsum(error * error for error in errors) / count),
        signed_bias=fsum(errors) / count,
        exact_agreement=sum(error == 0 for error in errors) / count,
        within_0_5=sum(error <= 0.5 for error in absolute_errors) / count,
        within_1_0=sum(error <= 1.0 for error in absolute_errors) / count,
        error_distribution=[
            {"error": error, "count": occurrences}
            for error, occurrences in sorted(Counter(errors).items())
        ],
        calibration_buckets=[
            {
                "human_band": target,
                "count": len(bucket),
                "mean_error": fsum(bucket) / len(bucket),
                "mae": fsum(abs(error) for error in bucket) / len(bucket),
            }
            for target, bucket in sorted(buckets.items())
        ],
    )
    if count < minimum_correlation_samples:
        result.update(pearson_status="insufficient_samples", spearman_status="insufficient_samples")
    else:
        result["pearson"], result["pearson_status"] = _correlation(
            paired_targets, paired_predictions
        )
        result["spearman"], result["spearman_status"] = _correlation(
            _average_ranks(paired_targets), _average_ranks(paired_predictions)
        )
    if count < minimum_qwk_samples:
        result["qwk_status"] = "insufficient_samples"
    else:
        result["quadratic_weighted_kappa"], result["qwk_status"] = _quadratic_weighted_kappa(
            paired_targets, paired_predictions
        )
    return result
