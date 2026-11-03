"""CLI guards are offline, including when local dotenv credentials exist."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def cli(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "replay_cli", Path(__file__).resolve().parents[2] / "scripts/replay_speaking.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/.env").write_text("SPEAKING_AZURE_KEY=PRIVATE_TEST_SECRET\n")
    return module


def test_prepare_empty_folder_gives_safe_instructions_without_calling_providers(cli, capsys):
    assert cli.main(["--prepare"]) == 2
    console = capsys.readouterr()
    assert "REPLAY_NO_AUDIO" in console.err
    assert "PRIVATE_TEST_SECRET" not in console.err + console.out
    assert (cli.ROOT / "benchmarks/speaking/private/replay").is_dir()


def test_cli_does_not_accept_source_outside_private(cli, capsys):
    assert cli.main(["--input", str(cli.ROOT / "outside")]) == 2
    assert "REPLAY_PRIVATE_ROOT_REQUIRED" in capsys.readouterr().err


def test_cli_defaults_to_offline_validate_and_passes_full_limits(cli, monkeypatch, capsys):
    calls = []

    async def run(root, reports, settings, **options):
        calls.append(options)
        return reports / "replay-offline", {
            "status": "VALIDATED",
            "limitations": ["LIVE_UNVERIFIED"],
        }

    monkeypatch.setattr(cli, "run_replay", run)
    assert cli.main([]) == 0
    assert calls[-1]["mode"] == "validate" and calls[-1]["allow_live"] is False
    assert (
        cli.main(
            [
                "--mode",
                "full",
                "--allow-live",
                "--estimated-cost-usd",
                "0.5",
                "--max-estimated-cost-usd",
                "1",
                "--resume",
            ]
        )
        == 0
    )
    assert calls[-1]["max_audio_seconds"] == 900 and calls[-1]["resume"] is True
    assert "PRIVATE_TEST_SECRET" not in capsys.readouterr().out
