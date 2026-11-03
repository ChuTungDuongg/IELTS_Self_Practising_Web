"""Synthetic private truth; these tests never invoke a speech provider."""

import json

import pytest
from test_speaking_benchmark import predictions, sample

from app.evaluation.speaking.manifest import BenchmarkInputError, load_manifest
from app.evaluation.speaking.models import BenchmarkSample
from app.evaluation.speaking.report import build_report


def test_speaker_cannot_cross_dev_and_holdout_even_outside_selected_rows(tmp_path):
    rows = [sample("dev"), sample("holdout")]
    for row, split in zip(rows, ["DEV", "HOLDOUT"], strict=True):
        row.update(speaker_id="private-speaker", split=split)
    path = tmp_path / "manifest.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(BenchmarkInputError, match="SPEAKER_SPLIT_LEAKAGE"):
        load_manifest(path, max_samples=1)


def test_required_splits_validate_unselected_manifest_rows_and_change_cohort_hash(tmp_path):
    rows = [sample("dev"), sample("unlabelled")]
    rows[0].update(speaker_id="fictional-a", split="DEV")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(BenchmarkInputError, match="SPEAKER_SPLITS_REQUIRED"):
        load_manifest(manifest, max_samples=1, require_speaker_splits=True)
    first = BenchmarkSample.model_validate(rows[0])
    second = first.model_copy(update={"split": "HOLDOUT"})
    assert (
        build_report([first], predictions())["cohort_hash"]
        != build_report([second], predictions())["cohort_hash"]
    )


def test_split_report_has_independent_fc_pr_errors_and_half_band_gate():
    raw = sample()
    raw.update(speaker_id="fictional-a", split="HOLDOUT")
    result = build_report(
        [BenchmarkSample.model_validate(raw)],
        predictions({"id": raw["id"], "scores": {"fc": 7, "pr": 6.5}}),
    )
    assert result["splits"]["HOLDOUT"]["criteria"]["fc"]["signed_bias"] == 1
    assert result["splits"]["HOLDOUT"]["fc_pr_half_band_gate"] == "fail"
    assert result["splits"]["DEV"]["fc_pr_half_band_gate"] == "unavailable"
    assert "private-speaker" not in json.dumps(result)


def test_report_separates_unknown_telemetry_from_recorded_errors_and_usage():
    result = build_report(
        [BenchmarkSample.model_validate(sample())],
        predictions(
            {
                "id": "synthetic-1",
                "telemetry": {
                    "latency_ms": 50,
                    "provider_calls": 2,
                    "provider_attempts": 3,
                    "provider_errors": 1,
                    "usage": {"total_tokens": 15},
                },
            }
        ),
    )
    assert result["llm_telemetry"] == {
        "sample_count": 1,
        "latency_p50_ms": 50,
        "latency_p95_ms": 50,
        "logical_calls": 2,
        "transport_attempts": 3,
        "failed_logical_calls": 1,
        "error_rate": 0.5,
        "usage": {"total_tokens": 15},
    }
    unknown = build_report([BenchmarkSample.model_validate(sample())], predictions())
    assert unknown["llm_telemetry"]["logical_calls"] is None


def test_hybrid_provenance_identifies_actual_evidence_versions_without_credentials():
    from app.core.config import Settings
    from app.evaluation.speaking.models import provenance

    identity = provenance(
        Settings(speaking_asr_provider="azure", speaking_azure_key="PRIVATE_AZURE_KEY")
    )
    assert identity.fluency_version == "fluency-v2"
    assert identity.pronunciation_provider == "azure-speech"
    from app.providers.speech_analysis.azure import ADAPTER_VERSION

    assert identity.pronunciation_version == ADAPTER_VERSION
    assert "PRIVATE_AZURE_KEY" not in identity.model_dump_json()


def test_analysis_sidecar_reports_fidelity_timing_pause_false_positives_and_stability():
    from app.evaluation.speaking.hybrid import AnalysisEvaluation, analysis_report

    data = AnalysisEvaluation.model_validate(
        {
            "schema_version": 1,
            "samples": [
                {
                    "id": "fictional-1",
                    "truth_source": "human",
                    "truth": {
                        "lexical_transcript": "I um like the blue garden",
                        "word_boundaries_ms": {"w1": [100, 200]},
                        "pauses_ms": [[200, 700]],
                        "feedback_labels": {"p1": True, "p2": False, "p3": False},
                    },
                    "observed": {
                        "lexical_transcript": "I like a blue garden",
                        "word_boundaries_ms": {"w1": [120, 220]},
                        "pauses_ms": [[220, 720], [1000, 1500]],
                        "feedback_flags": ["p1", "p2", "unjudged"],
                        "latency_ms": 40,
                        "provider_calls": 2,
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                        "repeat_scores": [{"fc": 6, "pr": 6.5}, {"fc": 6.5, "pr": 6.5}],
                    },
                }
            ],
        }
    )
    report = analysis_report(data, {"fictional-1"})
    assert report["lexical_fidelity"]["wer"] == pytest.approx(2 / 6)
    assert report["timing"]["boundary_mae_ms"] == 20
    assert report["pauses"]["precision"] == 0.5
    assert report["pauses"]["recall"] == 1
    assert report["feedback"]["false_positive_rate"] == 0.5
    assert report["feedback"]["unjudged_flags"] == 1
    assert report["telemetry"]["provider_calls"] == 2
    assert report["repeat_stability"]["fc"]["mean_range"] == 0.5
    assert report["repeat_stability"]["pr"]["mean_range"] == 0
    assert "garden" not in json.dumps(report)


def test_missing_truth_is_unknown_and_tts_cannot_claim_human_truth():
    from app.evaluation.speaking.hybrid import AnalysisEvaluation, analysis_report

    evaluation = AnalysisEvaluation.model_validate(
        {
            "schema_version": 1,
            "samples": [{"id": "fictional-1", "truth_source": "unlabelled", "observed": {}}],
        }
    )
    report = analysis_report(evaluation, {"fictional-1"})
    assert report["lexical_fidelity"]["wer"] is None
    assert report["feedback"]["false_positive_rate"] is None
    with pytest.raises(ValueError):
        AnalysisEvaluation.model_validate(
            {
                "schema_version": 1,
                "samples": [
                    {
                        "id": "fictional-1",
                        "truth_source": "tts",
                        "truth": {"lexical_transcript": "synthetic"},
                        "observed": {},
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    "truth", [{"feedback_labels": {"p1": "false"}}, {"word_boundaries_ms": {"w1": [True, 200]}}]
)
def test_human_evidence_requires_typed_booleans_and_numeric_timing(truth):
    from app.evaluation.speaking.hybrid import AnalysisEvaluation

    with pytest.raises(ValueError):
        AnalysisEvaluation.model_validate(
            {
                "schema_version": 1,
                "samples": [
                    {"id": "fictional-1", "truth_source": "human", "truth": truth, "observed": {}}
                ],
            }
        )


async def test_labels_are_removed_before_evidence_loader(tmp_path):
    from app.core.config import Settings
    from app.evaluation.speaking.runner import evaluate_samples

    raw = sample()
    raw.update(speaker_id="fictional-a", split="DEV")
    seen = []

    async def loader(item, *_):
        seen.append(set(item.model_dump()))
        raise RuntimeError("fictional failure")

    await evaluate_samples(
        [BenchmarkSample.model_validate(raw)],
        tmp_path,
        tmp_path,
        Settings(),
        evidence_loader=loader,
    )
    assert seen == [{"id", "responses"}]


async def test_hybrid_resume_does_not_blindly_repeat_an_interrupted_speech_request(tmp_path):
    from app.core.config import Settings
    from app.evaluation.speaking.runner import evaluate_samples

    calls = []

    async def interrupted(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("provider outcome unknown")

    settings = Settings(speaking_profile="speaking_hybrid_v1")
    samples = [BenchmarkSample.model_validate(sample())]
    first = await evaluate_samples(
        samples, tmp_path, tmp_path, settings, evidence_loader=interrupted
    )
    assert first.predictions[0].overall is None
    await evaluate_samples(
        samples, tmp_path, tmp_path, settings, evidence_loader=interrupted, resume=True
    )
    assert calls == [1], (
        "Resume must require reconciliation instead of repeating potentially billed audio"
    )


def test_cli_requires_bounded_live_budget_before_constructing_settings(
    tmp_path, monkeypatch, capsys
):
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts/evaluate_speaking.py"
    spec = importlib.util.spec_from_file_location("hybrid_cli", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    raw = sample()
    raw.update(speaker_id="fictional-a", split="DEV")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps(raw))

    def forbidden(*args, **kwargs):
        pytest.fail("unbounded live evaluation must not read config or construct providers")

    monkeypatch.setattr(cli, "Settings", forbidden)
    assert (
        cli.main(["--manifest", str(manifest), "--output", str(tmp_path / "out"), "--allow-live"])
        == 2
    )
    assert "LIVE_LIMITS_REQUIRED" in capsys.readouterr().err


def test_cli_offline_sidecar_never_exports_lexical_truth(tmp_path):
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts/evaluate_speaking.py"
    spec = importlib.util.spec_from_file_location("hybrid_report_cli", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    manifest, scored, analysis = [
        tmp_path / name for name in ("manifest.jsonl", "scored.json", "analysis.json")
    ]
    manifest.write_text(json.dumps(sample()))
    scored.write_text(predictions({"id": "synthetic-1", "scores": {"fc": 6}}).model_dump_json())
    analysis.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "samples": [
                    {
                        "id": "synthetic-1",
                        "truth_source": "human",
                        "truth": {"lexical_transcript": "private fictional wording"},
                        "observed": {"lexical_transcript": "private wording"},
                    }
                ],
            }
        )
    )
    output = tmp_path / "out"
    assert (
        cli.main(
            [
                "--manifest",
                str(manifest),
                "--predictions",
                str(scored),
                "--analysis-evaluation",
                str(analysis),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    summary = json.loads((output / "summary.json").read_text())
    assert summary["speech_analysis"]["lexical_fidelity"]["wer"] == pytest.approx(1 / 3)
    assert "private fictional" not in "".join(path.read_text() for path in output.iterdir())


async def test_live_runner_records_latency_and_actual_scorer_calls_without_bodies(tmp_path):
    from test_speaking_ai import evidence, feature_bundle
    from test_speaking_ai_runs import FakeLLM

    from app.core.config import Settings
    from app.evaluation.speaking.runner import evaluate_samples
    from app.services.speaking_scorer import SpeakingScorer

    async def loader(*_):
        return evidence(features=feature_bundle())

    result = await evaluate_samples(
        [BenchmarkSample.model_validate(sample())],
        tmp_path,
        tmp_path,
        Settings(),
        scorer=SpeakingScorer(FakeLLM()),
        evidence_loader=loader,
    )
    assert result.predictions[0].telemetry.provider_calls == 8
    assert result.predictions[0].telemetry.latency_ms >= 0
    assert "He go" not in result.model_dump_json()


async def test_hybrid_loader_shares_single_analysis_with_transcript_and_features(
    tmp_path, monkeypatch
):
    import wave
    from types import SimpleNamespace

    from test_speaking_ai import feature_bundle

    from app.core.config import Settings
    from app.evaluation.speaking import runner
    from app.evaluation.speaking.models import InferenceSample
    from app.schemas.speaking_ai import ASRResult

    audio = tmp_path / "synthetic.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\0" * 32000)
    raw = sample()
    raw["responses"][0].pop("fixture_id")
    raw["responses"][0]["audio_path"] = audio.name
    analysis = [
        SimpleNamespace(
            usage=SimpleNamespace(attempted_calls=1, failed_calls=0, submitted_audio_ms=1000),
            latency_ms=100,
        )
    ]
    calls = []

    async def analyze(*_):
        calls.append("analyze")
        return analysis

    def asr(results, _):
        from app.providers.speech_analysis.azure import ADAPTER_VERSION

        assert results is analysis
        return ASRResult(
            text="fictional speech",
            words=[],
            provider="azure",
            model="service-managed-unknown",
            version=ADAPTER_VERSION,
            language="en-US",
        )

    async def features(*_, **kwargs):
        assert kwargs["speech_analysis"] is analysis
        return feature_bundle()

    monkeypatch.setattr("app.services.speaking_hybrid.analyze_response", analyze)
    monkeypatch.setattr("app.services.speaking_hybrid.analysis_to_asr", asr)
    monkeypatch.setattr(
        runner,
        "assess_audio_quality",
        lambda *_: SimpleNamespace(assessable=True, state="AUDIO_OK"),
    )
    monkeypatch.setattr(runner, "build_feature_bundle", features)
    monkeypatch.setattr(runner, "build_attempt_evidence", lambda rows: rows)
    telemetry = []

    async def record_usage(value):
        telemetry.append(value)

    result = await runner.load_evidence(
        InferenceSample(id=raw["id"], responses=raw["responses"]),
        tmp_path,
        Settings(speaking_asr_provider="azure", speaking_asr_enabled=True),
        on_speech_usage=record_usage,
    )
    assert calls == ["analyze"]
    assert result[0]["verbatim"] == "fictional speech"
    assert telemetry == [
        {"attempted_calls": 1, "failed_calls": 0, "submitted_audio_ms": 1000, "latency_ms": 100}
    ]
