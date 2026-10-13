import json
from decimal import Decimal

from test_task2_benchmark import config
from test_task2_benchmark_contracts import record

from app.evaluation.task2.models import EvaluationRecord
from app.evaluation.task2.report import build_report, write_report
from app.evaluation.writing.metrics import score_metrics


def test_report_uses_shared_metrics_partial_cohorts_and_visible_failures(tmp_path):
    cfg = config()
    one = EvaluationRecord.model_validate({**record(), "config_key": cfg.key})
    two = EvaluationRecord.model_validate(
        {
            **record(),
            "sample_id": "T2-002",
            "split": "holdout",
            "config_key": cfg.key,
            "status": "FAILED",
            "predicted": {"tr": 7, "cc": 6.5},
            "predicted_overall": None,
            "failures": {"gra": "CRITERION_FAILED"},
        }
    )
    report = build_report([one, two], cfg)
    aggregate = report["aggregate"]
    assert aggregate["failure_rate"] == 0.5 and aggregate["count"] == 2
    assert aggregate["metrics"]["tr"] == score_metrics(
        [(Decimal(6), Decimal(6)), (Decimal(6), Decimal(7))]
    )
    assert aggregate["metrics"]["overall"] == score_metrics([(Decimal(6), Decimal(6))])
    assert aggregate["metrics"]["gra"]["count"] == 1
    assert report["stratified"]["split"]["holdout"]["failure_count"] == 1
    assert "6.0-6.5" in report["stratified"]["target_band"]["tr"]
    assert report["failures"] == [{"sample_id": "T2-002", "failures": {"gra": "CRITERION_FAILED"}}]
    write_report(tmp_path, report)
    assert "Failure" in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "tr" in (tmp_path / "disagreements.csv").read_text(encoding="utf-8")
    assert (
        json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["aggregate"][
            "failure_count"
        ]
        == 1
    )


def test_retry_success_preserves_initial_failures_calls_usage_and_cache_stats():
    cfg = config()
    failed = EvaluationRecord.model_validate(
        {
            **record(),
            "config_key": cfg.key,
            "status": "FAILED",
            "predicted": {},
            "predicted_overall": None,
            "failures": {"run": "BENCHMARK_SAMPLE_FAILED"},
            "provider_calls": 1,
            "token_usage": {"total_tokens": 5},
        }
    )
    success = EvaluationRecord.model_validate(
        {
            **record(),
            "config_key": cfg.key,
            "provider_calls": 13,
            "token_usage": {"total_tokens": 130},
            "cache_hit": True,
        }
    )
    report = build_report([success], cfg, attempts=[failed, success])
    assert report["aggregate"]["failure_count"] == 0
    assert report["aggregate"]["new_provider_calls"] == 0
    assert report["operational"]["attempt_count"] == 2
    assert report["operational"]["failed_attempt_count"] == 1
    assert report["operational"]["initial_failure_rate"] == 1
    assert report["operational"]["provider_calls"] == 14
    assert report["operational"]["token_usage"] == {"total_tokens": 135}
