"""Replay orchestration contracts: synthetic media and fake providers only."""

import asyncio
import json
import math
import wave
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import pytest

from app.core.config import Settings
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_models import ReplayManifest, ReplaySegment
from app.evaluation.speaking.replay_runner import (
    check_live_configuration,
    check_live_limits,
    select_segments,
)


def settings(**values):
    return Settings(_env_file=None, speaking_profile="speaking_hybrid_v1", **values)


def test_live_flag_and_operator_estimate_are_required():
    with pytest.raises(BenchmarkInputError, match="EXPLICIT_FLAG"):
        check_live_limits(False, 60, 1, 0.5, "azure")
    for estimate in (None, float("nan"), -1, 2):
        with pytest.raises(BenchmarkInputError):
            check_live_limits(True, 60, 1, estimate, "azure")
    check_live_limits(True, 60, 1, 0, "azure")
    with pytest.raises(BenchmarkInputError):
        check_live_limits(True, 60, 1, 0, "full")


def test_azure_configuration_never_requires_openai_but_full_does(monkeypatch):
    monkeypatch.setattr(
        "app.evaluation.speaking.replay_runner.hybrid_profile_status",
        lambda _: {
            "configured": True,
            "vad_available": True,
            "limitations": [],
        },
    )
    configured = settings(
        speaking_asr_enabled=True,
        speaking_azure_key="fictional-key",
        speaking_azure_region="japaneast",
        speaking_azure_billing_mode="free_only",
    )
    check_live_configuration(configured, "azure")
    with pytest.raises(BenchmarkInputError, match="OPENAI"):
        check_live_configuration(configured, "full")
    with pytest.raises(BenchmarkInputError, match="AZURE_CONFIGURATION"):
        check_live_configuration(settings(), "azure")


def test_unsegmented_smoke_is_bounded_and_full_requires_verified_candidate():
    manifest = ReplayManifest(source="full_speaking.mp3")
    metadata = {"full_speaking.mp3": {"duration_ms": 840000}}
    selected = select_segments(manifest, metadata, "azure", 60, settings())
    assert len(selected) == 1 and selected[0].end_ms == 60000
    assert selected[0].speaker_role == "unknown"
    with pytest.raises(BenchmarkInputError, match="SPEAKER_NOT_VERIFIED"):
        select_segments(manifest, metadata, "full", 900, settings())


def test_full_never_changes_response_cap_or_mixes_examiner():
    segments = [
        ReplaySegment(
            id=f"p{p}",
            source="full_speaking.wav",
            part_number=p,
            prompt_type="LONG_TURN" if p == 2 else "SHORT_ANSWER",
            prompt_text="Fictional prompt",
            start_ms=(p - 1) * 100000,
            end_ms=p * 100000,
            speaker_role="candidate",
        )
        for p in (1, 2, 3)
    ]
    manifest = ReplayManifest(candidate_only_verified=True, segments=segments)
    selected = select_segments(
        manifest, {"full_speaking.wav": {"duration_ms": 840000}}, "full", 900, settings()
    )
    assert len(selected) == 3 and all(s.end_ms - s.start_ms == 100000 for s in selected)
    assert settings().speaking_max_decoded_seconds == 600


def test_checkpoint_interrupt_requires_manual_billing_reconciliation(tmp_path):
    from app.evaluation.speaking.replay_cache import live_lock, read_checkpoint, save_checkpoint

    path = tmp_path / "SENSITIVE-speech.json"
    save_checkpoint(path, {"schema_version": 1, "state": "ATTEMPTED"})
    assert read_checkpoint(path)["state"] == "ATTEMPTED"
    with live_lock(tmp_path):
        with pytest.raises(BenchmarkInputError, match="LOCKED"):
            with live_lock(tmp_path):
                pass
    assert not (tmp_path / "SENSITIVE-live.lock").exists()


@pytest.fixture
def replay(tmp_path, monkeypatch):
    from app.evaluation.speaking import replay_runner as runner
    from app.schemas.speaking_timeline import AudioSegmentMapping
    from app.services.speaking_audio import NormalizedAudio, fingerprint
    from app.services.speaking_vad import VadResult

    root = tmp_path / "private"
    root.mkdir()
    segments = [
        ReplaySegment(
            id=f"p{p}",
            source="PRIVATE_SOURCE_MARKER.wav",
            part_number=p,
            prompt_type="LONG_TURN" if p == 2 else "SHORT_ANSWER",
            prompt_text="PRIVATE_QUESTION_MARKER",
            start_ms=(p - 1) * 10000,
            end_ms=p * 10000,
            speaker_role="candidate",
        )
        for p in (1, 2, 3)
    ]
    manifest = ReplayManifest(candidate_only_verified=True, segments=segments)
    metadata = {"PRIVATE_SOURCE_MARKER.wav": {"duration_ms": 30000, "sha256": "a" * 64}}
    labels = [None]
    monkeypatch.setattr(runner, "validate", lambda *_: (manifest, metadata, labels[0]))
    monkeypatch.setattr(
        runner,
        "hybrid_profile_status",
        lambda _: {
            "configured": True,
            "vad_available": True,
            "limitations": [],
        },
    )

    def normalize(_root, name, meta, segment, destination, configured):
        with wave.open(str(destination), "wb") as output:
            output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            output.writeframes(
                b"".join(
                    int(8000 * math.sin(i / 23)).to_bytes(2, "little", signed=True)
                    for i in range(160000)
                )
            )
        key = fingerprint([meta["sha256"], segment.start_ms, segment.end_ms])
        rid = uuid5(NAMESPACE_URL, key)
        mapping = AudioSegmentMapping(
            response_id=rid,
            take_number=1,
            segment_id=uuid5(rid, "source-window"),
            normalized_start_ms=0,
            normalized_end_ms=10000,
            source_start_ms=segment.start_ms,
        )
        return NormalizedAudio(
            destination,
            meta["sha256"],
            configured.speaking_normalizer_version,
            key,
            10000,
            timeline=(mapping,),
        )

    async def vad(audio, _):
        return VadResult(available=True, spans=[(0, audio.duration_ms)])

    monkeypatch.setattr(runner, "normalize_window", normalize)
    monkeypatch.setattr("app.services.speaking_vad.measure_vad_async", vad)
    configured = settings(
        speaking_asr_enabled=True,
        speaking_asr_provider="azure",
        speaking_azure_key="PRIVATE_AZURE_KEY_MARKER",
        speaking_azure_region="japaneast",
        speaking_azure_billing_mode="free_only",
        speaking_ai_enabled=True,
        speaking_ai_provider="openai",
        ai_writing_openai_api_key="PRIVATE_OPENAI_KEY_MARKER",
        speaking_ai_model="gpt-6-luna",
    )
    return SimpleNamespace(
        root=root,
        output=tmp_path / "reports",
        settings=configured,
        labels=labels,
        manifest=manifest,
    )


class Analyzer:
    def __init__(self, settings, failure=None, pronunciation=True):
        self.settings, self.failure, self.pronunciation = settings, failure, pronunciation
        self.calls = 0

    async def analyze(self, audio, **identity):
        from app.evaluation.speaking.replay_audio import pcm_digest
        from app.providers.speech_analysis.azure import azure_analysis_identity
        from app.schemas.speech_analysis import SpeechAnalysisResult

        self.calls += 1
        if isinstance(self.failure, BaseException):
            raise self.failure
        words = [
            {
                "evidence_id": f"w{i}",
                "utterance_id": "u1",
                "text": text,
                "start_ms": i * 1000,
                "end_ms": (i + 1) * 1000,
            }
            for i, text in enumerate("Yesterday I go to my fictional village again".split())
        ]
        return SpeechAnalysisResult.model_validate(
            {
                "provider": azure_analysis_identity(self.settings).model_dump(),
                "source": {
                    "audio_fingerprint": audio.source_audio_fingerprint,
                    "normalized_audio_fingerprint": pcm_digest(audio),
                    "duration_ms": audio.duration_ms,
                    **identity,
                },
                "status": "FAILED" if self.failure else "COMPLETE",
                "error_code": self.failure,
                "provider_reason_code": "HTTP_429" if self.failure else None,
                "lexical_transcript": ""
                if self.failure
                else "Yesterday I go to my fictional village again",
                "words": [] if self.failure else words,
                "observations": [
                    {
                        "evidence_id": f"o{i}",
                        "target_id": w["evidence_id"],
                        "kind": "pronunciation",
                        "metric": "AccuracyScore",
                        "score": 74,
                        "start_ms": w["start_ms"],
                        "end_ms": w["end_ms"],
                    }
                    for i, w in enumerate(words)
                ]
                if self.pronunciation and not self.failure
                else [],
                "coverage": {
                    "audio_duration_ms": audio.duration_ms,
                    "stream_completed": not self.failure,
                    "word_count": len(words) if not self.failure else 0,
                    "timed_word_count": len(words),
                    "recognized_span_ms": 10000 if not self.failure else 0,
                },
                "capabilities": {
                    "word_timing_observed": True,
                    "pronunciation_observed": self.pronunciation,
                    "prosody_observed": None,
                },
                "usage": {
                    "attempted_calls": 1,
                    "submitted_audio_ms": audio.duration_ms,
                    "billing_uncertain": True,
                },
                "latency_ms": 12,
            }
        )


class LLM:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def ensure_ready(self):
        pass

    async def complete(self, messages, schema, *, options=None):
        from app.providers.speaking_llm.base import Completion

        self.calls.append(messages)
        if self.fail:
            raise RuntimeError("PRIVATE_PROVIDER_BODY_MARKER")
        data = (
            {"score": 6.5}
            if "score" in schema["properties"]
            else {"feedback": "Fictional test feedback.", "strengths": [], "improvements": []}
        )
        return Completion(json.dumps(data), usage={"prompt_tokens": 10, "completion_tokens": 5})


async def run(replay, **options):
    from app.evaluation.speaking.replay_runner import run_replay

    return await run_replay(
        replay.root,
        replay.output,
        replay.settings,
        allow_live=True,
        max_audio_seconds=60,
        estimated_cost_usd=0.5,
        max_estimated_cost_usd=1,
        offline_test=True,
        **options,
    )


async def test_validate_zero_apis_and_smoke_never_calls_luna(replay):
    from app.evaluation.speaking.replay_runner import run_replay

    analyzer = Analyzer(replay.settings)
    llm = LLM()
    output, report = await run_replay(
        replay.root, replay.output, replay.settings, analyzer=analyzer
    )
    assert analyzer.calls == 0 and report["status"] == "VALIDATED"
    output, report = await run(
        replay, mode="azure", analyzer=analyzer, scorer=SimpleNamespace(provider=llm)
    )
    assert analyzer.calls == 1 and llm.calls == []
    assert report["luna"]["scores"] == {} and report["luna"]["overall"] is None
    assert report["azure"]["word_timing_coverage"] == 1
    assert report["input"]["part_counts"] == {"1": 1}
    assert report["azure"]["prosody_observed"] is None
    assert report["evaluation"]["metrics"] == {}
    assert "LIVE_UNVERIFIED" in report["limitations"]
    assert all(
        (output / name).is_file()
        for name in (
            "summary.md",
            "summary.json",
            "predictions.json",
            "samples.jsonl",
            "speech-coverage.json",
        )
    )


async def test_full_uses_production_scorer_and_features_without_human_truth(replay):
    from app.evaluation.speaking.replay_models import ReplayHumanLabels
    from app.services.speaking_scorer import SpeakingScorer

    replay.labels[0] = ReplayHumanLabels(
        bands={"overall": 7},
        provenance={
            "kind": "human_examiner",
            "reference": "PRIVATE_HUMAN_PROVENANCE",
            "verified": True,
        },
    )
    analyzer, llm = Analyzer(replay.settings), LLM()
    output, report = await run(replay, mode="full", analyzer=analyzer, scorer=SpeakingScorer(llm))
    assert report["status"] == "GRADED", report
    assert report["luna"]["overall"] == 6.5 and analyzer.calls == 3 and len(llm.calls) == 8
    assert report["evaluation"]["differences"] == {"overall": -0.5}
    assert set(report["evaluation"]["metrics"]) == {"overall"}
    assert report["azure"]["vad_available"] is True
    assert all("Yesterday I go" in json.dumps(messages) for messages in llm.calls)
    assert "PRIVATE_HUMAN_PROVENANCE" not in json.dumps(llm.calls) and '"human"' not in json.dumps(
        llm.calls
    )
    public = "".join(p.read_text() for p in output.iterdir() if not p.name.startswith("SENSITIVE-"))
    for marker in (
        "PRIVATE_SOURCE_MARKER",
        "PRIVATE_QUESTION_MARKER",
        "Yesterday",
        "PRIVATE_AZURE_KEY_MARKER",
        "PRIVATE_OPENAI_KEY_MARKER",
        str(replay.root),
    ):
        assert marker not in public
    assert report["luna"]["usage"]["prompt_tokens"] == 80
    # A complete replay reuses both caches even without --resume.
    _, second = await run(replay, mode="full", analyzer=analyzer, scorer=SpeakingScorer(llm))
    assert analyzer.calls == 3 and len(llm.calls) == 8 and second["azure"]["new_attempts"] == 0


async def test_luna_failure_resume_keeps_complete_speech_and_prompt_changes_do_not_rebill(replay):
    from app.services.speaking_scorer import SpeakingScorer

    analyzer = Analyzer(replay.settings)
    _, failed = await run(
        replay, mode="full", analyzer=analyzer, scorer=SpeakingScorer(LLM(fail=True))
    )
    assert failed["luna"]["overall"] is None and analyzer.calls == 3
    _, completed = await run(
        replay, mode="full", analyzer=analyzer, scorer=SpeakingScorer(LLM()), resume=True
    )
    assert completed["luna"]["overall"] == 6.5 and analyzer.calls == 3
    replay.settings.speaking_ai_prompt_version = "fictional-prompt-v2"
    _, refreshed = await run(replay, mode="full", analyzer=analyzer, scorer=SpeakingScorer(LLM()))
    assert refreshed["luna"]["overall"] == 6.5 and analyzer.calls == 3


@pytest.mark.parametrize(
    "failure", [TimeoutError(), asyncio.CancelledError(), "SPEAKING_AZURE_QUOTA_EXCEEDED"]
)
async def test_uncertain_or_quota_speech_never_retries_or_falls_back(replay, failure):
    analyzer = Analyzer(replay.settings, failure=failure)
    _, first = await run(replay, mode="azure", analyzer=analyzer)
    _, resumed = await run(replay, mode="azure", analyzer=analyzer, resume=True)
    assert analyzer.calls == 1 and resumed["status"] == "FAILED"
    assert first["status"] == (
        "CANCELLED" if isinstance(failure, asyncio.CancelledError) else "FAILED"
    )
    assert first["azure"]["new_attempts"] == 1 and resumed["azure"]["new_attempts"] == 0
    assert first["azure"]["billing_uncertain"]
    if isinstance(failure, str):
        assert failure in resumed["limitations"]
        assert first["azure"]["samples"][0]["provider_reason_codes"] == ["HTTP_429"]


async def test_missing_pr_keeps_three_scores_and_no_overall(replay):
    from app.services.speaking_scorer import SpeakingScorer

    analyzer, llm = Analyzer(replay.settings, pronunciation=False), LLM()
    _, report = await run(replay, mode="full", analyzer=analyzer, scorer=SpeakingScorer(llm))
    assert report["luna"]["scores"]["pr"] is None and report["luna"]["overall"] is None
    assert report["luna"]["reasons"]["pr"] == "SPEAKING_PR_UNASSESSABLE"
    assert len(llm.calls) == 6


async def test_no_temporal_fc_keeps_other_scores_without_overall(replay, monkeypatch):
    from app.services.speaking_scorer import SpeakingScorer
    from app.services.speaking_vad import VadResult

    async def unavailable(*_):
        return VadResult(available=False, limitations=["VAD_UNAVAILABLE"])

    monkeypatch.setattr("app.services.speaking_vad.measure_vad_async", unavailable)
    _, report = await run(
        replay, mode="full", analyzer=Analyzer(replay.settings), scorer=SpeakingScorer(LLM())
    )
    assert report["luna"]["scores"]["fc"] is None and report["luna"]["scores"]["pr"] == 6.5
    assert (
        report["luna"]["overall"] is None
        and report["luna"]["reasons"]["fc"] == "SPEAKING_FC_UNASSESSABLE"
    )


@pytest.mark.parametrize("missing", ["key", "region"])
def test_explicit_missing_azure_settings_fail_before_provider(missing):
    configured = settings(
        speaking_asr_enabled=True,
        speaking_asr_provider="azure",
        speaking_azure_key=None if missing == "key" else "fictional",
        speaking_azure_region="" if missing == "region" else "japaneast",
    )
    with pytest.raises(BenchmarkInputError, match="AZURE_CONFIGURATION_MISSING"):
        check_live_configuration(configured, "azure")


async def test_guard_rejects_implicit_live_even_with_injected_provider(replay):
    from app.evaluation.speaking.replay_runner import run_replay

    analyzer = Analyzer(replay.settings)
    with pytest.raises(BenchmarkInputError, match="EXPLICIT_FLAG"):
        await run_replay(
            replay.root, replay.output, replay.settings, mode="azure", analyzer=analyzer
        )
    assert analyzer.calls == 0


async def test_incomplete_stream_is_not_reused_as_complete(replay):
    class PartialAnalyzer(Analyzer):
        async def analyze(self, audio, **identity):
            result = await super().analyze(audio, **identity)
            result.status = "PARTIAL"
            result.coverage.stream_completed = False
            return result

    analyzer = PartialAnalyzer(replay.settings)
    _, first = await run(replay, mode="azure", analyzer=analyzer)
    _, resumed = await run(replay, mode="azure", analyzer=analyzer, resume=True)
    assert first["azure"]["partial"] == 1 and resumed["status"] == "FAILED" and analyzer.calls == 1


async def test_score_first_is_preserved_across_feedback_cancellation(replay):
    from app.services.speaking_scorer import SpeakingScorer

    class InterruptedFeedback(LLM):
        async def complete(self, messages, schema, *, options=None):
            if "score" not in schema["properties"]:
                raise asyncio.CancelledError()
            return await super().complete(messages, schema, options=options)

    analyzer, llm = Analyzer(replay.settings), InterruptedFeedback()
    _, interrupted = await run(replay, mode="full", analyzer=analyzer, scorer=SpeakingScorer(llm))
    assert interrupted["status"] == "CANCELLED" and interrupted["luna"]["scores"]["fc"] == 6.5
    remaining = LLM()
    _, completed = await run(
        replay, mode="full", analyzer=analyzer, scorer=SpeakingScorer(remaining), resume=True
    )
    assert completed["luna"]["overall"] == 6.5 and len(remaining.calls) == 6 and analyzer.calls == 3


async def test_full_quota_blocks_luna_and_legacy_fallbacks(replay, monkeypatch):
    from app.services.speaking_scorer import SpeakingScorer

    def forbidden(*_):
        pytest.fail("Replay must never construct a legacy/fallback provider")

    monkeypatch.setattr("app.providers.speaking_asr.create_provider", forbidden)
    monkeypatch.setattr("app.providers.speaking_llm.create_provider", forbidden)
    analyzer, llm = Analyzer(replay.settings, failure="SPEAKING_AZURE_QUOTA_EXCEEDED"), LLM()
    _, report = await run(replay, mode="full", analyzer=analyzer, scorer=SpeakingScorer(llm))
    assert report["status"] == "FAILED" and analyzer.calls == 1 and llm.calls == []
    assert "SPEAKING_AZURE_QUOTA_EXCEEDED" in report["limitations"]
    assert set(report["luna"]["reasons"].values()) == {"SPEAKING_AZURE_QUOTA_EXCEEDED"}
    assert set(report["luna"]["scores"]) == {"fc", "lr", "gra", "pr"}
