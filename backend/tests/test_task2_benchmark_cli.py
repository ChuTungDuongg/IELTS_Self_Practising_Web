import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_task2_benchmark_contracts import sample

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts/benchmark_task2.py"


def cli():
    spec = importlib.util.spec_from_file_location("task2_cli", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("cwd", [ROOT, ROOT / "backend"])
def test_offline_cli_dry_run_no_database_or_provider(tmp_path, cwd):
    path = tmp_path / "manifest.jsonl"
    path.write_text(json.dumps(sample()), encoding="utf-8")
    command = [
        sys.executable,
        str(SCRIPT),
        "--manifest",
        str(path),
        "--split",
        "dev",
        "--dry-run",
        "--output",
        str(tmp_path / "report"),
        "--max-concurrent-llm-requests",
        "1",
    ]
    result = subprocess.run(
        command,
        cwd=cwd,
        env={
            **os.environ,
            "DATABASE_URL": "postgresql+asyncpg://fictional:fictional@127.0.0.1:1/NEVER_CONNECT",
            "JWT_SECRET": "",
            "AI_WRITING_VLLM_BASE_URL": "https://private.example/SECRET_URL",
            "AI_WRITING_OPENAI_API_KEY": "SECRET_KEY",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and "DRY_RUN: samples=1 runs=0 failed=0" in result.stdout
    assert not any(
        secret in result.stdout + result.stderr
        for secret in ("SECRET", "Fictional", "NEVER_CONNECT")
    )
    report = json.loads((tmp_path / "report/report.json").read_text(encoding="utf-8"))
    assert report["configuration"]["max_concurrent_llm_requests"] == 1
    assert report["configuration"]["prompt_version"].endswith("mts-task2-v12")
    assert "SECRET" not in json.dumps(report)


@pytest.mark.parametrize("contents", ["id,essay\nsecret", '{"essay":"SECRET"}', ""])
def test_cli_safe_invalid_manifest(contents, tmp_path, capsys):
    path = tmp_path / "manifest.jsonl"
    path.write_text(contents, encoding="utf-8")
    assert (
        cli().main(
            [
                "--manifest",
                str(path),
                "--split",
                "dev",
                "--dry-run",
                "--output",
                str(tmp_path / "output"),
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert "BENCHMARK_" in output.err and "SECRET" not in output.err


@pytest.mark.parametrize("value", ["0", "5"])
def test_cli_concurrency_bounds(value, tmp_path):
    with pytest.raises(SystemExit) as error:
        cli().main(
            ["--manifest", str(tmp_path), "--split", "dev", "--max-concurrent-llm-requests", value]
        )
    assert error.value.code == 2


def test_cli_safe_failure_exit_codes_and_interruption(tmp_path, capsys, monkeypatch):
    path = tmp_path / "manifest.jsonl"
    path.write_text(json.dumps(sample()), encoding="utf-8")
    script = cli()
    args = ["--manifest", str(path), "--split", "dev", "--output", str(tmp_path / "report")]

    async def failure(*args, **kwargs):
        raise RuntimeError("SECRET_PROVIDER_BODY")

    monkeypatch.setattr(script, "run_benchmark", failure)
    assert script.main(args) == 2
    assert "SECRET_PROVIDER_BODY" not in capsys.readouterr().err

    async def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(script, "run_benchmark", interrupt)
    assert script.main(args) == 130
    assert "BENCHMARK_INTERRUPTED" in capsys.readouterr().err

    async def partial(*args, **kwargs):
        return {"status": "COMPLETED", "sample_count": 1, "records": [{"status": "FAILED"}]}

    monkeypatch.setattr(script, "run_benchmark", partial)
    assert script.main(args) == 1
