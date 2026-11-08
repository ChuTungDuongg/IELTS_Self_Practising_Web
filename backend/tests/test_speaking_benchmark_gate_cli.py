import json
import subprocess
import sys
from pathlib import Path


def test_speaking_benchmark_gate_cli_pass(tmp_path: Path):
    report_data = {
        "protocol": "speaking-regression-gate-v1",
        "status": "PASS",
        "matched_samples": 50,
        "selected_samples": 50,
        "matched_independent_candidates": 30,
        "reasons": [],
        "metrics": [
            {
                "metric": "overall_exact_match_ratio",
                "direction": "HIGHER_IS_BETTER",
                "status": "PASS",
                "baseline": 0.8,
                "candidate": 0.85,
                "difference": 0.05,
                "tolerable_regression": 0.02,
            }
        ],
    }
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps(report_data), encoding="utf-8")

    cli_path = Path(__file__).resolve().parents[2] / "scripts" / "speaking_benchmark_gate_cli.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), str(report_file)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "speaking-regression-gate-v1" in proc.stdout
    assert "overall_exact_match_ratio" in proc.stdout
    assert "PASS" in proc.stdout


def test_speaking_benchmark_gate_cli_fail(tmp_path: Path):
    report_data = {
        "protocol": "speaking-regression-gate-v1",
        "status": "FAIL",
        "matched_samples": 50,
        "selected_samples": 50,
        "matched_independent_candidates": 30,
        "reasons": ["CRITERIA_REGRESSED"],
        "metrics": [],
    }
    report_file = tmp_path / "fail_report.json"
    report_file.write_text(json.dumps(report_data), encoding="utf-8")

    cli_path = Path(__file__).resolve().parents[2] / "scripts" / "speaking_benchmark_gate_cli.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), str(report_file), "--format", "json"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["status"] == "FAIL"


def test_speaking_benchmark_gate_cli_inconclusive_or_missing(tmp_path: Path):
    cli_path = Path(__file__).resolve().parents[2] / "scripts" / "speaking_benchmark_gate_cli.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), str(tmp_path / "nonexistent.json")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
