"""Offline arithmetic checks against hand-computed Speaking benchmark examples."""

import json
import math

import pytest

from app.evaluation.speaking.metrics import METRICS_PROTOCOL_VERSION, score_metrics


def test_agreement_errors_and_failure_coverage_use_the_correct_denominators():
    result = score_metrics([1, 2, 3, 4, 5, 6], [1, 2.5, 4, 2.5, None, 7.5])
    assert result["total_count"] == 6
    assert result["count"] == 5
    assert result["nonscorable_count"] == 1
    assert result["failure_rate"] == pytest.approx(1 / 6)
    assert result["coverage_rate"] == pytest.approx(5 / 6)
    assert result["mae"] == pytest.approx(0.9)
    assert result["rmse"] == pytest.approx(math.sqrt(1.15))
    assert result["signed_bias"] == pytest.approx(0.3)
    assert result["exact_agreement"] == pytest.approx(1 / 5)
    assert result["within_0_5"] == pytest.approx(2 / 5)
    assert result["within_1_0"] == pytest.approx(3 / 5)


@pytest.mark.parametrize("predictions,expected", [([1, 2, 3, 4, 5], 1), ([5, 4, 3, 2, 1], -1)])
def test_perfect_and_reversed_correlations(predictions, expected):
    result = score_metrics([1, 2, 3, 4, 5], predictions)
    assert result["pearson"] == pytest.approx(expected)
    assert result["spearman"] == pytest.approx(expected)
    assert result["pearson_status"] == result["spearman_status"] == "ok"


def test_pearson_and_spearman_have_distinct_hand_computed_values():
    # Centered vectors [-1, 0, 1] and [-4/3, -1/3, 5/3] give sqrt(27/28).
    result = score_metrics([1, 2, 3], [1, 2, 4])
    assert result["pearson"] == pytest.approx(math.sqrt(27 / 28))
    assert result["spearman"] == pytest.approx(1)
    assert result["qwk_status"] == "insufficient_samples"


def test_spearman_uses_average_ranks_for_ties():
    # Ranks [1.5, 1.5, 3, 4], [1, 2.5, 2.5, 4]: covariance 3.75 / 4.5.
    result = score_metrics([1, 1, 2, 3], [1, 2, 2, 3])
    assert result["spearman"] == pytest.approx(5 / 6)


def test_qwk_uses_half_band_categories_and_expected_marginals():
    # Index squared disagreement = 2; marginal expected sum = 390; 1 - 5*2/390.
    result = score_metrics([1, 2, 3, 4, 5], [1, 2.5, 2.5, 4, 5])
    assert result["quadratic_weighted_kappa"] == pytest.approx(38 / 39)
    assert result["qwk_status"] == "ok"
    assert result["mae"] == pytest.approx(0.2)
    assert result["rmse"] == pytest.approx(math.sqrt(0.1))
    assert score_metrics([0, 9] * 3, [9, 0] * 3)["quadratic_weighted_kappa"] == -1


@pytest.mark.parametrize(
    "targets,predictions", [([2] * 5, [2] * 5), ([2] * 5, [3] * 5), ([1, 2, 3, 4, 5], [3] * 5)]
)
def test_constant_vectors_have_explicit_correlation_status(targets, predictions):
    result = score_metrics(targets, predictions)
    assert result["pearson"] is None
    assert result["spearman"] is None
    assert result["pearson_status"] == result["spearman_status"] == "constant_vector"
    if targets == predictions:
        assert result["quadratic_weighted_kappa"] is None
        assert result["qwk_status"] == "undefined_expected_variance"
    else:
        assert result["quadratic_weighted_kappa"] == pytest.approx(0)
        assert result["qwk_status"] == "ok"


def test_minimum_samples_count_only_scorable_predictions():
    result = score_metrics([1, 2, 3, 4, 5], [1, 2, None, None, None])
    assert result["count"] == 2
    assert result["pearson"] is result["spearman"] is None
    assert result["pearson_status"] == result["spearman_status"] == "insufficient_samples"
    assert result["quadratic_weighted_kappa"] is None
    assert result["qwk_status"] == "insufficient_samples"
    configured = score_metrics([1, 2], [1, 2], minimum_correlation_samples=2, minimum_qwk_samples=2)
    assert configured["pearson"] == configured["spearman"] == 1
    assert configured["quadratic_weighted_kappa"] == 1


@pytest.mark.parametrize(
    "targets,predictions,expected_failure", [([], [], None), ([1, 2], [None, None], 1)]
)
def test_no_scorable_samples_keep_errors_null_and_coverage_explicit(
    targets, predictions, expected_failure
):
    result = score_metrics(targets, predictions)
    assert result["count"] == 0
    assert result["failure_rate"] == expected_failure
    assert result["coverage_rate"] == (0 if targets else None)
    assert result["nonscorable_count"] == len(targets)
    for key in (
        "mae",
        "rmse",
        "signed_bias",
        "exact_agreement",
        "within_0_5",
        "within_1_0",
        "pearson",
        "spearman",
        "quadratic_weighted_kappa",
    ):
        assert result[key] is None
    assert (
        result["pearson_status"]
        == result["spearman_status"]
        == result["qwk_status"]
        == "no_samples"
    )
    assert result["error_distribution"] == result["calibration_buckets"] == []


def test_error_distribution_and_half_band_calibration_buckets_are_sorted():
    result = score_metrics([2, 1.5, 2, 1, 3], [3, 1, 1, None, 3])
    assert result["error_distribution"] == [
        {"error": -1.0, "count": 1},
        {"error": -0.5, "count": 1},
        {"error": 0.0, "count": 1},
        {"error": 1.0, "count": 1},
    ]
    assert result["calibration_buckets"] == [
        {"human_band": 1.5, "count": 1, "mean_error": -0.5, "mae": 0.5},
        {"human_band": 2.0, "count": 2, "mean_error": 0.0, "mae": 1.0},
        {"human_band": 3.0, "count": 1, "mean_error": 0.0, "mae": 0.0},
    ]


@pytest.mark.parametrize(
    "invalid", [True, False, "3", float("nan"), float("inf"), -float("inf"), -0.5, 9.5, 1.25, None]
)
def test_invalid_targets_are_rejected_even_if_prediction_is_missing(invalid):
    with pytest.raises(ValueError, match="half-band"):
        score_metrics([invalid], [None])


@pytest.mark.parametrize(
    "invalid", [True, False, "3", float("nan"), float("inf"), -float("inf"), -0.5, 9.5, 1.25]
)
def test_invalid_predictions_are_rejected(invalid):
    with pytest.raises(ValueError, match="half-band"):
        score_metrics([3], [invalid])


def test_mismatched_lengths_are_rejected():
    with pytest.raises(ValueError, match="same length"):
        score_metrics([1, 2], [1])


@pytest.mark.parametrize("threshold", [0, -1, True, 1.5, "3", None])
@pytest.mark.parametrize("parameter", ["minimum_correlation_samples", "minimum_qwk_samples"])
def test_thresholds_must_be_positive_integers(parameter, threshold):
    with pytest.raises(ValueError, match="positive integer"):
        score_metrics([], [], **{parameter: threshold})


def test_metric_output_is_deterministic_finite_json_and_does_not_mutate_inputs():
    targets, predictions = [0, 3.5, 9, 4], [0, None, 8.5, 5]
    before = (targets.copy(), predictions.copy())
    result = score_metrics(targets, predictions)
    assert result == score_metrics(targets, predictions)
    assert (targets, predictions) == before
    assert METRICS_PROTOCOL_VERSION == result["metric_protocol_version"] == "speaking-metrics-v1"
    assert json.loads(json.dumps(result, allow_nan=False)) == result
