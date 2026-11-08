"""HTTP API integration tests for Quality, Evaluation Suites, Regression Gates, and Exports."""

import asyncio
import json
import subprocess
import sys

import httpx
import pytest

from app.api.dependencies import require_admin
from app.core.database import get_session
from app.main import app
from app.models import User
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run


@pytest.mark.asyncio
async def test_quality_suites_gates_reports_and_cli_pipeline(grading_lab, monkeypatch, tmp_path):
    factory, settings, storage, owner_id, sample_id, run_id = grading_lab

    # Set up user for authentication
    owner_user = User(
        id=owner_id,
        email=f"owner-{owner_id}@example.com",
        display_name="Owner Admin",
        is_active=True,
    )
    from app.core.config import get_settings

    global_settings = get_settings()
    monkeypatch.setattr(global_settings, "storage_root", settings.storage_root)
    monkeypatch.setattr(global_settings, "storage_backend", "local")

    async def mock_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = mock_session
    app.dependency_overrides[require_admin] = lambda: owner_user

    # In grading_lab, complete the run so it has a valid prediction for evaluation
    async with factory() as session, session.begin():
        run = await session.get(Run, run_id)
        run.status = "COMPLETED"
        run.prediction = {
            "bands": {"fc": 6.5, "lr": 6.5, "gra": 6.5, "pr": 6.5, "overall": 6.5},
            "limitations": [],
        }
        config_fp = run.config_fingerprint

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        try:
            # 1. POST /quality (read-only evaluation)
            quality_payload = {
                "cohort": [{"sample_id": str(sample_id), "review_revision": 1}],
                "label_selection": {"kind": "LEGACY"},
                "policy": {
                    "protocol": "speaking-dataset-quality-v1",
                    "require_human_label": False,
                    "require_all_parts": False,
                    "minimum_independent_candidates": 1,
                },
            }
            res = await client.post(
                "/api/v1/admin/speaking-benchmark/quality", json=quality_payload
            )
            assert res.status_code == 200
            diag = res.json()
            assert diag["protocol"] == "speaking-dataset-quality-v1"
            assert "status" in diag
            assert diag["eligible_samples"] == 1

            # 2. POST /quality/snapshots and GET /quality/snapshots
            res = await client.post(
                "/api/v1/admin/speaking-benchmark/quality/snapshots", json=quality_payload
            )
            assert res.status_code == 201
            snap = res.json()
            snapshot_id = snap["id"]

            res = await client.get("/api/v1/admin/speaking-benchmark/quality/snapshots")
            assert res.status_code == 200
            snaps = res.json()
            assert any(s["id"] == snapshot_id for s in snaps)

            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/quality/snapshots/{snapshot_id}"
            )
            assert res.status_code == 200
            assert res.json()["id"] == snapshot_id

            # 3. POST /evaluation-suites and GET /evaluation-suites
            suite_payload = {
                **quality_payload,
                "name": "Integration Test Suite",
                "description": "Suite for regression gate testing",
                "expected_revision": 0,
                "holdout_evaluation": False,
            }
            res = await client.post(
                "/api/v1/admin/speaking-benchmark/evaluation-suites", json=suite_payload
            )
            assert res.status_code == 201
            suite = res.json()
            suite_id = suite["id"]
            assert suite["name"] == "Integration Test Suite"

            res = await client.get("/api/v1/admin/speaking-benchmark/evaluation-suites")
            assert res.status_code == 200
            suites = res.json()
            assert any(s["id"] == suite_id for s in suites)

            res = await client.get(f"/api/v1/admin/speaking-benchmark/evaluation-suites/{suite_id}")
            assert res.status_code == 200
            assert res.json()["id"] == suite_id

            # 4. POST /regression-gates
            gate_payload = {
                "name": "Self-Comparison Regression Gate",
                "suite_id": suite_id,
                "baseline": {
                    "kind": "GRADING",
                    "configuration_fingerprint": config_fp,
                },
                "candidate": {
                    "kind": "GRADING",
                    "configuration_fingerprint": config_fp,
                },
                "policy": {
                    "protocol": "speaking-regression-gate-v1",
                    "comparison": "CONFIGURATION",
                    "minimum_independent_candidates": 1,
                    "minimum_prediction_coverage": 1.0,
                    "minimum_reference_coverage": 1.0,
                    "thresholds": [
                        {"metric": "overall_mae", "max_regression": 0.5},
                    ],
                    "max_unknown_billing_attempts": 0,
                },
            }
            res = await client.post(
                "/api/v1/admin/speaking-benchmark/regression-gates", json=gate_payload
            )
            assert res.status_code == 201
            gate = res.json()
            gate_id = gate["id"]
            assert gate["name"] == "Self-Comparison Regression Gate"

            res = await client.get("/api/v1/admin/speaking-benchmark/regression-gates")
            assert res.status_code == 200
            assert any(g["id"] == gate_id for g in res.json())

            res = await client.get(f"/api/v1/admin/speaking-benchmark/regression-gates/{gate_id}")
            assert res.status_code == 200
            assert res.json()["id"] == gate_id

            # 5. POST /regression-gates/{gate_id}/evaluate
            res = await client.post(
                f"/api/v1/admin/speaking-benchmark/regression-gates/{gate_id}/evaluate",
                json={"holdout_evaluation": False},
            )
            assert res.status_code == 201
            report = res.json()
            report_id = report["id"]
            assert report["gate_id"] == gate_id
            assert report["status"] in {"PASS", "FAIL", "INCONCLUSIVE", "INVALID"}

            # 6. GET /regression-gates/{gate_id}/reports and GET /regression-reports/{report_id}
            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/regression-gates/{gate_id}/reports"
            )
            assert res.status_code == 200
            reports = res.json()
            assert any(r["id"] == report_id for r in reports)

            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/regression-reports/{report_id}"
            )
            assert res.status_code == 200
            assert res.json()["id"] == report_id

            # 7. Exports: CSV and JSON
            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/regression-reports/{report_id}/export.csv"
            )
            assert res.status_code == 200
            assert "text/csv" in res.headers["content-type"]
            csv_lines = res.text.strip().split("\n")
            assert len(csv_lines) >= 2
            assert "metric,direction,status" in csv_lines[0]

            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/regression-reports/{report_id}/export.json"
            )
            assert res.status_code == 200
            report_json = res.json()
            assert report_json["id"] == report_id

            # 8. Test offline saved-JSON CLI
            saved_json_path = tmp_path / "test_report.json"
            saved_json_path.write_text(json.dumps(report_json), encoding="utf-8")

            # Run CLI via python subprocess
            from pathlib import Path

            def run_cli():
                cli_path = (
                    Path(__file__).resolve().parents[2]
                    / "scripts"
                    / "speaking_benchmark_gate_cli.py"
                )
                return subprocess.run(
                    [
                        sys.executable,
                        str(cli_path),
                        str(saved_json_path),
                    ],
                    capture_output=True,
                    text=True,
                )

            result = await asyncio.to_thread(run_cli)
            # Exit code depends on report status: 0 for PASS, 1 for FAIL, 2 for INCONCLUSIVE/INVALID
            expected_exit = (
                0 if report["status"] == "PASS" else 1 if report["status"] == "FAIL" else 2
            )
            assert result.returncode == expected_exit
            assert "Protocol:" in result.stdout
            assert "Status:" in result.stdout
        finally:
            app.dependency_overrides.clear()
