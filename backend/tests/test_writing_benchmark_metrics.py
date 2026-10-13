"""Provider-free shared score arithmetic and Task 1 compatibility."""

from decimal import Decimal
from pathlib import Path

import pytest

from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.evaluation.task1 import metrics as task1
from app.evaluation.task1.runner import implementation_hash
from app.evaluation.writing.metrics import overall_score, score_metrics


def test_task1_reexports_identical_functions():
    assert task1.score_metrics is score_metrics
    assert task1.overall_score is overall_score


def test_shared_hand_calculated_metrics():
    values = [(Decimal(a), Decimal(b)) for a, b in [(5, 5), (5.5, 6), (6, 7), (6.5, 8)]]
    result = score_metrics(values, minimum_qwk_samples=4)
    assert result == pytest.approx(
        {
            "count": 4,
            "exact_agreement": 0.25,
            "within_0_5": 0.5,
            "within_1_0": 0.75,
            "signed_bias": 0.75,
            "mae": 0.75,
            "rmse": 0.9354143466934853,
            "quadratic_weighted_kappa": 10 / 17,
            "qwk_status": "ok",
        }
    )


def test_all_official_bins_and_unavailable_qwk():
    bins = [Decimal(i) / 2 for i in range(19)]
    assert score_metrics([(v, v) for v in bins])["quadratic_weighted_kappa"] == 1
    assert score_metrics([])["qwk_status"] == "no_samples"
    assert score_metrics([(Decimal(6), Decimal(6))])["qwk_status"] == "insufficient_samples"
    assert (
        score_metrics([(Decimal(6), Decimal(6))] * 10)["qwk_status"]
        == "undefined_expected_variance"
    )
    averaged = score_metrics([(Decimal("6.25"), Decimal("6.5"))] * 10)
    assert averaged["mae"] == 0.25
    assert averaged["qwk_status"] == "non_half_band_scores"


@pytest.mark.parametrize("first", ["ta", "tr"])
@pytest.mark.parametrize("scores", [(6, 6, 6, 6.5), (6, 6, 6.5, 6.5), (0, 9, 9, 9)])
def test_task_specific_overall_matches_production(first, scores):
    traits = (first, "cc", "lr", "gra")
    values = [Decimal(v) for v in scores]
    assert (
        overall_score(dict(zip(traits, values, strict=True)), traits=traits)
        == aggregate_ai_task_two(*values)[1]
    )
    assert overall_score({first: Decimal(6)}, traits=traits) is None


def test_task1_hash_tracks_shared_metric_dependency(monkeypatch):
    before = implementation_hash()
    original = Path.read_text

    def changed(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        return (
            value + "\n# dependency edit\n"
            if path.as_posix().endswith("evaluation/writing/metrics.py")
            else value
        )

    monkeypatch.setattr(Path, "read_text", changed)
    assert implementation_hash() != before
