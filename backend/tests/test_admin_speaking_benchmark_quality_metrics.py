"""P4 pure gate decisions: persisted evidence only, no providers or databases."""

from copy import deepcopy

import pytest

from app.schemas.speaking_benchmark_quality import GatePolicy
from app.services.speaking_benchmark_quality_metrics import evaluate_regression


def study(count=10):
    samples, a, b = [], [], []
    for index in range(count):
        identity = dict(
            sample_id=str(index),
            candidate_id=f"candidate-{index}",
            review_revision=1,
            source_sha256="a" * 64,
            manifest_fingerprint="b" * 64,
            label_fingerprint="c" * 64,
            reference_fingerprint="d" * 64,
        )
        samples.append(identity | {"human": {"overall": 6}})
        a.append(
            identity
            | {"ai": {"overall": 6.5}, "metrics": {"wer": 0.2, "cer": 0.1}, "available": True}
        )
        b.append(
            identity
            | {"ai": {"overall": 6}, "metrics": {"wer": 0.1, "cer": 0.05}, "available": True}
        )
    config = {"rubric_version": "rubric-v1", "metric_protocol": "admin-speaking-research-v1"}
    return (
        {"samples": samples},
        {"rows": a, "configuration": config},
        {"rows": b, "configuration": config},
    )


def policy(metric="wer", **overrides):
    return GatePolicy(thresholds=[{"metric": metric, "max_regression": 0}], **overrides)


def test_complete_matched_cohort_passes_without_invented_causal_claim():
    suite, baseline, candidate = study()
    result = evaluate_regression(policy(), suite, baseline, candidate, {"issues": []})
    assert result["status"] == "PASS"
    assert result["matched_independent_candidates"] == 10
    metric = result["metrics"][0]
    assert metric["baseline"] == 0.2 and metric["candidate"] == 0.1
    assert metric["difference"] == pytest.approx(-0.1)
    assert metric["paired"]["ci95"] == pytest.approx([0.1, 0.1])
    assert "NO_CAUSAL_OR_SIGNIFICANCE_CLAIM" in result["limitations"]


def test_insufficient_candidate_count_is_inconclusive_and_repeated_responses_do_not_help():
    suite, baseline, candidate = study()
    for row in suite["samples"] + baseline["rows"] + candidate["rows"]:
        row["candidate_id"] = "same-candidate"
    result = evaluate_regression(policy(), suite, baseline, candidate, {"issues": []})
    assert result["status"] == "INCONCLUSIVE"
    assert result["matched_independent_candidates"] == 1


def test_blocking_quality_precedes_small_cohort_and_cannot_pass():
    suite, baseline, candidate = study(1)
    result = evaluate_regression(
        policy(),
        suite,
        baseline,
        candidate,
        {"issues": [{"severity": "BLOCKED", "code": "DEV_HOLDOUT_CANDIDATE_LEAKAGE"}]},
    )
    assert result["status"] == "FAIL"


@pytest.mark.parametrize(
    "field",
    [
        "source_sha256",
        "manifest_fingerprint",
        "review_revision",
        "label_fingerprint",
        "reference_fingerprint",
    ],
)
def test_source_review_or_reference_identity_mismatch_is_invalid(field):
    suite, baseline, candidate = study()
    candidate["rows"][0][field] = "changed"
    assert (
        evaluate_regression(policy(), suite, baseline, candidate, {"issues": []})["status"]
        == "INVALID"
    )


def test_missing_prediction_keeps_full_denominator_instead_of_zero_or_favorable_subset():
    suite, baseline, candidate = study()
    candidate["rows"].pop()
    result = evaluate_regression(policy("overall_mae"), suite, baseline, candidate, {"issues": []})
    assert result["status"] == "FAIL"
    assert result["candidate_coverage"] == 0.9
    assert result["metrics"][0]["candidate"] == 0
    assert result["selected_samples"] == 10


def test_scoring_metrics_reuse_human_bands_and_preserve_missing_overall():
    suite, baseline, candidate = study()
    candidate["rows"][0]["ai"]["overall"] = None
    result = evaluate_regression(policy("overall_mae"), suite, baseline, candidate, {"issues": []})
    assert result["status"] == "FAIL"
    assert result["band_metrics"]["candidate"]["overall"]["count"] == 9
    assert result["band_metrics"]["candidate"]["overall"]["nonscorable_count"] == 1


def test_rubric_incompatibility_is_invalid_and_inputs_are_not_mutated():
    suite, baseline, candidate = study()
    candidate["configuration"] = candidate["configuration"] | {"rubric_version": "other"}
    before = deepcopy((suite, baseline, candidate))
    assert (
        evaluate_regression(policy(), suite, baseline, candidate, {"issues": []})["status"]
        == "INVALID"
    )
    assert (suite, baseline, candidate) == before


def test_thresholds_require_explicit_finite_limits_and_meaningful_minima():
    with pytest.raises(ValueError):
        policy(minimum_independent_candidates=0)
    with pytest.raises(ValueError):
        GatePolicy(thresholds=[{"metric": "wer", "max_regression": float("nan")}])
    with pytest.raises(ValueError):
        GatePolicy(thresholds=[])


def test_partial_coverage_compares_matched_recordings_only():
    suite, baseline, candidate = study()
    baseline["rows"][0]["metrics"]["wer"] = 9
    candidate["rows"][0]["metrics"]["wer"] = None
    candidate["rows"][1]["metrics"]["wer"] = 2
    result = evaluate_regression(
        policy(
            minimum_prediction_coverage=0.9,
            minimum_reference_coverage=0.9,
            minimum_independent_candidates=9,
        ),
        suite,
        baseline,
        candidate,
        {"issues": []},
    )
    assert result["status"] == "FAIL"
    assert result["metrics"][0]["baseline"] == pytest.approx(0.2)


def test_metrics_require_common_candidate_cohort_and_propagate_invalid_artifacts():
    suite, baseline, candidate = study()
    candidate["rows"][0]["metrics"]["wer"] = None
    candidate["rows"][1]["metrics"]["cer"] = None
    p = GatePolicy(
        thresholds=[{"metric": m, "max_regression": 0} for m in ["wer", "cer"]],
        minimum_independent_candidates=9,
        minimum_reference_coverage=0.9,
    )
    result = evaluate_regression(p, suite, baseline, candidate, {"issues": []})
    assert result["status"] == "INCONCLUSIVE"
    assert result["matched_independent_candidates"] == 8
    candidate["invalid_reasons"] = ["GRADING_SUITE_BINDING_MISMATCH"]
    assert evaluate_regression(p, suite, baseline, candidate, {"issues": []})["status"] == "INVALID"
