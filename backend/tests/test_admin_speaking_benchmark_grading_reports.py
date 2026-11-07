import csv
import io

import pytest


def test_aggregate_metrics_preserve_missing_and_literal_errors():
    from app.services.speaking_benchmark_reports import summarize

    rows = [
        {"human": {"overall": h}, "ai": {"overall": a}, "verified": True, "split": "DEV"}
        for h, a in [(6, 6.5), (7, 6), (5, None)]
    ]
    metrics = summarize(rows)["criteria"]["overall"]
    assert metrics["total_count"] == 3
    assert metrics["count"] == 2
    assert metrics["mae"] == 0.75
    assert metrics["signed_bias"] == -0.25
    assert metrics["coverage_rate"] == pytest.approx(2 / 3)
    assert metrics["pearson"] is None


def test_export_is_formula_safe_and_uses_strict_allowlist():
    from app.services.speaking_benchmark_reports import csv_export, export_rows

    rows = [
        {
            "sample_id": "fictional",
            "code": "=HYPERLINK(1)",
            "split": "DEV",
            "human": {"overall": 6},
            "ai": {"overall": 6.5},
            "transcript": "SECRET",
            "audio_key": "PRIVATE",
            "notes": "PRIVATE",
            "verified": True,
        }
    ]
    safe = export_rows(rows)
    assert "SECRET" not in str(safe)
    assert "PRIVATE" not in str(safe)
    parsed = list(csv.DictReader(io.StringIO(csv_export(rows))))
    assert parsed[0]["code"].startswith("'")
