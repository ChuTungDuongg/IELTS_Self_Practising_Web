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


def test_diarization_review_and_approval_never_dispatch_cloud_modes(cli, monkeypatch):
    from app.evaluation.speaking import replay_diarization_cli

    calls = []

    def action(root, settings, config, args):
        calls.append(args)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Offline diarization must not dispatch Azure/Luna replay")

    monkeypatch.setattr(replay_diarization_cli, "run_diarization_action", action)
    monkeypatch.setattr(cli, "run_replay", forbidden)
    for flags in (
        ["--auto-segment"],
        ["--review-segments"],
        ["--approve-segments"],
        ["--confirm-candidate-speaker", "f0-speaker_01", "--set-part-boundaries", "10000", "50000"],
    ):
        assert cli.main(flags) == 0
    assert len(calls) == 4 and calls[-1].set_part_boundaries == [10000, 50000]
    assert cli.main(["--auto-segment", "--allow-live"]) == 2
    assert len(calls) == 4


def test_setup_missing_token_is_safe_and_does_not_echo_dotenv(cli, monkeypatch, capsys):
    from app.evaluation.speaking import replay_diarization_cli

    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(replay_diarization_cli.sys.stdin, "isatty", lambda: False)
    assert cli.main(["--setup-diarization-model"]) == 2
    output = capsys.readouterr()
    assert (
        "HF_TOKEN_REQUIRED" in output.err and "PRIVATE_TEST_SECRET" not in output.err + output.out
    )


def test_cli_auto_confirm_questions_approve_validate_cycle_is_offline(cli, monkeypatch, capsys):
    import hashlib
    import json

    from test_speaking_diarization import result

    from app.evaluation.speaking import replay_diarization as coordinator
    from app.evaluation.speaking import replay_diarization_cli as actions
    from app.evaluation.speaking import replay_manifest
    from app.evaluation.speaking import replay_segment_review as review
    from app.evaluation.speaking.replay_cache import read_checkpoint, save_checkpoint

    root = cli.ROOT / "benchmarks/speaking/private/replay"
    root.mkdir(parents=True)
    source = root / "full_speaking.wav"
    source.write_bytes(b"fictional CLI audio fixture")
    item = result(
        [
            ("e", 0, 1000),
            ("c", 2000, 10000),
            ("e", 20000, 21000),
            ("c", 22000, 90000),
            ("e", 100000, 101000),
            ("c", 102000, 115000),
        ]
    )
    metadata = {
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "duration_ms": 180000,
        "size_bytes": source.stat().st_size,
        "format": "wav",
    }
    for module in (coordinator, replay_manifest, review):
        monkeypatch.setattr(module, "probe_audio", lambda *_: metadata)
    monkeypatch.setattr(
        coordinator, "normalize_recording", lambda *args: args[3].write_bytes(b"normalized fixture")
    )

    class Engine:
        identity = {"model": "fictional-model", "revision": "test"}
        config = {"threads": 2}
        calls = 0

        def analyze(self, _, *, source, metadata, cache_key):
            self.calls += 1
            return item.model_copy(
                update={
                    "source": source,
                    "source_sha256": metadata["sha256"],
                    "cache_key": cache_key,
                }
            )

    engine = Engine()
    monkeypatch.setattr(actions, "LocalDiarizer", lambda **_: engine)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Offline review must never construct a billable or legacy provider")

    monkeypatch.setattr("app.providers.speaking_asr.create_provider", forbidden)
    monkeypatch.setattr("app.providers.speaking_llm.create_provider", forbidden)
    assert cli.main(["--auto-segment"]) == 0
    assert not (root / "segments.json").exists()
    assert (
        cli.main(["--confirm-candidate-speaker", "c", "--set-part-boundaries", "20000", "100000"])
        == 0
    )
    template = read_checkpoint(root / "question-context.template.json")
    for question in template["questions"].values():
        question.update(prompt_text="Fictional <script>unsafe()</script> question", verified=True)
    questions = root / "questions.json"
    save_checkpoint(questions, template)
    assert cli.main(["--question-context", str(questions)]) == 0
    assert cli.main(["--approve-segments"]) == 0
    before = (root / "segments.json").read_bytes()
    assert json.loads(before)["candidate_only_verified"] is True
    assert cli.main(["--mode", "validate"]) == 0
    assert cli.main(["--auto-segment"]) == 0 and engine.calls == 1
    assert (root / "segments.json").read_bytes() == before
    html = (root / "review.local.html").read_text()
    assert "&lt;script&gt;unsafe()&lt;/script&gt;" in html and "<script>unsafe()" not in html
    assert "PRIVATE_TEST_SECRET" not in capsys.readouterr().out
