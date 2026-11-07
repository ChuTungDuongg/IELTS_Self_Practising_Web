"""Private comparison contracts: fictional waveforms, references and recognizers only."""

import asyncio
import json

import pytest
from test_speaking_replay_runner import Analyzer, replay  # noqa: F401

from app.evaluation.speaking import asr_comparison as comparison
from app.evaluation.speaking import replay_runner
from app.evaluation.speaking.asr_comparison import HumanReference, authorize_comparison
from app.evaluation.speaking.asr_metrics import lexical_metrics
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.providers.speaking_asr.lexical import lexical_identity


def reference(text="Yesterday I go um I I mean school", **values):
    return HumanReference(
        segment_id="p1",
        source_sha256="a" * 64,
        start_ms=0,
        end_ms=10000,
        text=text,
        human_verified=True,
        provenance="independent_human_transcriber",
        **values,
    )


def test_strict_lexical_metrics_retain_errors_fillers_and_repetitions():
    truth = reference(
        annotations=[
            {"kind": "incorrect_grammar", "start_token": 0, "end_token": 3},
            {"kind": "self_correction", "start_token": 5, "end_token": 8},
        ]
    )
    exact = lexical_metrics(truth.text, truth)
    assert exact["wer"] == exact["cer"] == 0
    assert all(item["recall"] == 1 for item in exact["preservation"].values())
    polished = lexical_metrics("Yesterday I went I mean school fictional", truth)
    assert polished["wer"] > 0 and polished["missing_words"] > 0
    assert polished["hallucinated_words"] == 1
    assert polished["preservation"]["filler"]["recall"] == 0
    assert polished["preservation"]["repetition"]["recall"] == 0
    assert polished["preservation"]["incorrect_grammar"]["recall"] == 0
    assert lexical_metrics("A fluent hypothesis")["wer"] is None
    silence = lexical_metrics("fictional hallucination", reference(text=""))
    assert silence["wer"] is None and silence["hallucinated_words"] == 2
    inserted = lexical_metrics("Yesterday I really go um I I mean school", truth)
    assert inserted["preservation"]["incorrect_grammar"]["recall"] == 0


def test_provider_estimates_and_gpu_consent_include_every_variant(replay):  # noqa: F811
    kwargs = dict(
        allow_live=True, allow_gpu=False, max_audio_seconds=120, seconds=60, estimate=1, budget=2
    )
    with pytest.raises(BenchmarkInputError, match="EVERY_PROVIDER"):
        authorize_comparison(
            replay.settings,
            [("azure_pa", None), ("azure_stt", None)],
            provider_estimates={"azure_pa": 0.5},
            **kwargs,
        )
    with pytest.raises(BenchmarkInputError, match="BUDGET"):
        authorize_comparison(
            replay.settings,
            [("azure_pa", None), ("azure_stt", None)],
            provider_estimates={"azure_pa": 0.6, "azure_stt": 0.6},
            **kwargs,
        )
    with pytest.raises(BenchmarkInputError, match="GPU_NOT_AUTHORIZED"):
        authorize_comparison(
            replay.settings,
            [("faster_whisper_modal", None)],
            provider_estimates={"faster_whisper_modal": 0.5},
            **kwargs,
        )
    with pytest.raises(BenchmarkInputError, match="EXPLICIT_FLAG"):
        authorize_comparison(
            replay.settings,
            [("azure_pa", None)],
            provider_estimates={"azure_pa": 0.5},
            **(kwargs | {"allow_live": False}),
        )
    with pytest.raises(BenchmarkInputError, match="AUDIO_BUDGET"):
        authorize_comparison(
            replay.settings,
            [("azure_pa", 500), ("azure_pa", 1000)],
            provider_estimates={"azure_pa": 0.5},
            **(kwargs | {"seconds": 121}),
        )


@pytest.fixture
def harness(replay, monkeypatch):  # noqa: F811
    monkeypatch.setattr(comparison, "validate", replay_runner.validate)
    monkeypatch.setattr(comparison, "normalize_window", replay_runner.normalize_window)
    return replay


async def test_offline_comparison_same_pcm_human_strata_no_provider_construction(
    harness, monkeypatch, tmp_path
):
    from app.evaluation.speaking.replay_audio import pcm_digest

    segment = harness.manifest.segments[0]
    audio = comparison.normalize_window(
        harness.root,
        segment.source,
        {"sha256": "a" * 64},
        segment,
        tmp_path / "fixture.wav",
        harness.settings,
    )
    result = await Analyzer(harness.settings).analyze(audio)
    fixture_rows = []
    for provider, text in (
        ("azure_pa", "Yesterday I went to school"),
        ("azure_stt", "Yesterday I go um I I mean school"),
    ):
        copy = result.model_copy(deep=True)
        copy.provider = lexical_identity(harness.settings, provider)
        copy.lexical_transcript = text
        fixture_rows.append(
            {
                "segment_id": "p1",
                "source_sha256": "a" * 64,
                "start_ms": 0,
                "end_ms": 10000,
                "provider": provider,
                "result": copy.model_dump(mode="json"),
            }
        )
    fixture_path = harness.root / "asr-fixtures.json"
    fixture_path.write_text(
        json.dumps({"schema_version": 1, "observations": fixture_rows}), encoding="utf-8"
    )
    reference_path = harness.root / "asr-human-references.json"
    reference_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "references": [
                    reference(
                        accent="vi", speaking_speed="slow", response_length="short"
                    ).model_dump()
                ],
            }
        ),
        encoding="utf-8",
    )

    def forbidden(*_, **__):
        pytest.fail("Offline comparison cannot construct or call providers")

    monkeypatch.setattr(comparison, "create_lexical_analyzer", forbidden)
    monkeypatch.setattr(comparison, "AzureSpeechAnalyzer", forbidden)
    kwargs = dict(
        providers=["azure_pa", "azure_stt"], segment_ids=["p1"], fixtures_path=fixture_path
    )
    output, report = await comparison.compare_asr(
        harness.root, harness.output, harness.settings, references_path=reference_path, **kwargs
    )
    assert report["execution"] == "OFFLINE_FIXTURES"
    assert report["provider_audio_seconds"] == 20
    assert {row["pcm_sha256"] for row in report["samples"]} == {pcm_digest(audio)}
    assert report["providers"]["azure_stt:default"]["wer"] == 0
    assert report["providers"]["azure_pa:default"]["wer"] > 0
    assert len(report["strata"]) == 6
    assert all(row["new_requests"] == 0 for row in report["samples"])
    assert (output / "summary.md").is_file()
    assert "Yesterday" not in (output / "summary.md").read_text(encoding="utf-8")
    _, unlabelled = await comparison.compare_asr(
        harness.root, harness.output, harness.settings, **kwargs
    )
    assert all(r["wer"] is None and r["cer"] is None for r in unlabelled["providers"].values())
    assert unlabelled["disagreement"] and not unlabelled["disagreement"][0]["is_accuracy"]
    fixture_rows[0]["start_ms"] = 1
    fixture_path.write_text(
        json.dumps({"schema_version": 1, "observations": fixture_rows}), encoding="utf-8"
    )
    with pytest.raises(BenchmarkInputError, match="WINDOW_MISMATCH"):
        await comparison.compare_asr(harness.root, harness.output, harness.settings, **kwargs)


async def test_completed_provider_checkpoints_reused_and_interrupted_calls_never_retried(
    harness, monkeypatch
):
    calls = []
    interrupted = [False]

    class FakeAnalyzer:
        def __init__(self, settings, strategy):
            self.settings, self.strategy = settings, strategy
            self.identity = lexical_identity(settings, strategy)

        async def analyze(self, audio, **ids):
            calls.append(self.strategy)
            if interrupted[0]:
                raise asyncio.CancelledError()
            result = await Analyzer(self.settings).analyze(audio, **ids)
            return result.model_copy(update={"provider": self.identity})

    monkeypatch.setattr(comparison, "AzureSpeechAnalyzer", lambda s: FakeAnalyzer(s, "azure_pa"))
    monkeypatch.setattr(comparison, "create_lexical_analyzer", lambda s, p: FakeAnalyzer(s, p))
    kwargs = dict(
        providers=["azure_pa", "azure_stt"],
        segment_ids=["p1"],
        allow_live=True,
        estimated_cost_usd=1,
        max_estimated_cost_usd=2,
        provider_estimates={"azure_pa": 0.5, "azure_stt": 0.5},
    )
    for _ in range(2):
        _, report = await comparison.compare_asr(
            harness.root, harness.output, harness.settings, **kwargs
        )
        assert report["status"] == "COMPARED"
    assert calls == ["azure_pa", "azure_stt"]
    assert all(r["cache_reused"] and r["new_requests"] == 0 for r in report["samples"])
    # An existing checkpoint with another identity is neither a cache hit nor metric evidence.
    from app.evaluation.speaking.replay_cache import read_checkpoint, save_checkpoint

    for path in (harness.output / ".speech-cache").glob("*.json"):
        checkpoint = read_checkpoint(path)
        if checkpoint["results"][0]["provider"]["provider"] == "azure-speech":
            checkpoint["identity"] = "wrong-source-or-model"
            save_checkpoint(path, checkpoint)
    _, rejected = await comparison.compare_asr(
        harness.root, harness.output, harness.settings, **kwargs
    )
    row = rejected["samples"][0]
    assert row["status"] == "FAILED" and "text" not in row
    assert not row["cache_reused"] and row["new_requests"] == 0
    assert calls == ["azure_pa", "azure_stt"]
    interrupted[0] = True
    kwargs["segment_ids"] = ["p2"]
    with pytest.raises(asyncio.CancelledError):
        await comparison.compare_asr(harness.root, harness.output, harness.settings, **kwargs)
    assert calls == ["azure_pa", "azure_stt", "azure_pa"]
    kwargs["providers"] = ["azure_pa"]
    kwargs["provider_estimates"] = {"azure_pa": 0.5}
    _, report = await comparison.compare_asr(
        harness.root, harness.output, harness.settings, **kwargs
    )
    assert len(calls) == 3
    assert report["samples"][0]["billing_uncertain"]
    assert "BILLING_UNKNOWN" in report["samples"][0]["error_code"]


def test_comparison_never_sends_examiner_or_unverified_audio(harness):
    from app.evaluation.speaking.asr_comparison import plan_comparison

    with pytest.raises(BenchmarkInputError, match="EXPLICIT_PROVIDERS"):
        plan_comparison(harness.manifest, {}, harness.settings, [], [], [])
    manifest = harness.manifest.model_copy(update={"candidate_only_verified": False})
    with pytest.raises(BenchmarkInputError, match="SPEAKER_NOT_VERIFIED"):
        plan_comparison(manifest, {}, harness.settings, ["azure_pa"], [], [])
    manifest = harness.manifest.model_copy(deep=True)
    manifest.segments[0].speaker_role = "examiner"
    with pytest.raises(BenchmarkInputError, match="CANDIDATE_SEGMENT"):
        plan_comparison(manifest, {}, harness.settings, ["azure_pa"], ["p1"], [])


async def test_fixture_cannot_claim_another_provider_or_source(harness, tmp_path):
    from pydantic import ValidationError

    segment = harness.manifest.segments[0]
    audio = comparison.normalize_window(
        harness.root,
        segment.source,
        {"sha256": "a" * 64},
        segment,
        tmp_path / "fixture.wav",
        harness.settings,
    )
    result = await Analyzer(harness.settings).analyze(audio)
    fixture = dict(
        segment_id="p1",
        source_sha256="a" * 64,
        start_ms=0,
        end_ms=10000,
        provider="azure_pa",
        result=result,
    )
    comparison.FixtureObservation.model_validate(fixture)
    with pytest.raises(ValidationError, match="provenance mismatch"):
        comparison.FixtureObservation.model_validate(fixture | {"provider": "azure_stt"})
    with pytest.raises(ValidationError, match="provenance mismatch"):
        comparison.FixtureObservation.model_validate(fixture | {"source_sha256": "b" * 64})
