"""Hybrid checkpoints reuse one billable analysis across features, scoring and asset repair."""

from sqlalchemy import select
from test_speaking_transcript import completed, fake_decode, worker_for

from app.core.config import Settings
from app.models.speaking_transcript import SpeakingNormalizedAudio, SpeakingTranscript
from app.providers.speech_analysis.azure import AzureSpeechAnalyzer
from app.schemas.speech_analysis import SpeechCapabilities, SpeechCoverage, SpeechUsage, SpeechWord
from app.services.speaking_audio import normalize_committed_take
from app.services.speaking_transcript import SpeakingTranscriptService


class Analyzer:
    def __init__(self, settings):
        self.identity = AzureSpeechAnalyzer(settings).identity
        self.calls = []

    async def analyze(self, audio, **identity):
        self.calls.append((audio.source_audio_fingerprint, identity))
        result = AzureSpeechAnalyzer(Settings())._empty(
            audio,
            identity.get("response_id"),
            identity.get("take_number"),
            identity.get("segment_id"),
        )
        return result.model_copy(
            update={
                "provider": self.identity,
                "status": "COMPLETE",
                "lexical_transcript": "Yesterday I go",
                "display_transcript": "Yesterday I go.",
                "words": [
                    SpeechWord(
                        evidence_id=f"{identity.get('segment_id')}_{i}",
                        utterance_id="u",
                        text=word,
                        start_ms=i * 200,
                        end_ms=(i + 1) * 200,
                    )
                    for i, word in enumerate(["Yesterday", "I", "go"])
                ],
                "coverage": SpeechCoverage(
                    audio_duration_ms=audio.duration_ms,
                    stream_completed=True,
                    final_utterance_count=1,
                    word_count=3,
                    timed_word_count=3,
                    recognized_span_ms=600,
                ),
                "capabilities": SpeechCapabilities(pronunciation_observed=None),
                "usage": SpeechUsage(attempted_calls=1, submitted_audio_ms=audio.duration_ms),
            }
        )


async def test_shared_result_persists_and_new_feature_does_not_rebill_after_asset_repair(
    db_session, tmp_path, monkeypatch
):
    aid, rid, media = await completed(db_session, tmp_path)
    settings = Settings(speaking_profile="speaking_hybrid_v1", speaking_asr_enabled=True)
    analyzer = Analyzer(settings)
    from types import SimpleNamespace

    from app.providers.speaking_asr import provider_identity

    provider = SimpleNamespace(identity=provider_identity(settings), analyzer=analyzer)
    service = SpeakingTranscriptService(
        db_session, media.actor, settings, identity=provider.identity
    )
    run = await service.create(aid)
    worker = worker_for(db_session, settings, media.storage, provider)
    await worker.execute(run.run_id)
    snapshot = await service.get(aid, run.run_id)
    assert snapshot.status == "COMPLETED" and snapshot.responses[0].verbatim == "Yesterday I go"
    assert len(analyzer.calls) == 1
    from app.services.speaking_features import feature_identity

    def changed_features(settings):
        return {**feature_identity(settings), "fluency": "fluency-offline-next"}

    monkeypatch.setattr("app.services.speaking_transcript.feature_identity", changed_features)
    monkeypatch.setattr(
        "app.services.speaking_transcript_worker.feature_identity", changed_features
    )
    newer = SpeakingTranscriptService(db_session, media.actor, settings, identity=provider.identity)
    next_run = await newer.create(aid)
    assert next_run.run_id != run.run_id
    await worker.execute(next_run.run_id)
    assert (await newer.get(aid, next_run.run_id)).status == "COMPLETED"
    assert len(analyzer.calls) == 1, "Feature changes must reuse durable speech analysis"
    async with db_session.begin():
        normalized = await db_session.scalar(
            select(SpeakingNormalizedAudio).where(SpeakingNormalizedAudio.response_id == rid)
        )
        assert normalized.metadata_json["speech_analysis"]
        key = normalized.storage_key
        transcript = await db_session.scalar(
            select(SpeakingTranscript)
            .where(SpeakingTranscript.response_id == rid, SpeakingTranscript.kind == "VERBATIM")
            .limit(1)
        )
        assert transcript.provider_json["evidence"]["profile"] == "speaking_hybrid_v1"
    media.storage.delete(key)
    await normalize_committed_take(
        db_session, rid, settings, storage=media.storage, executor=fake_decode
    )
    async with db_session.begin():
        row = await db_session.scalar(
            select(SpeakingNormalizedAudio).where(SpeakingNormalizedAudio.response_id == rid)
        )
        assert row.metadata_json.get("speech_analysis"), (
            "Asset repair must retain billable checkpoint"
        )


async def test_partial_stream_is_readable_but_never_reused_as_complete(db_session, tmp_path):
    from types import SimpleNamespace

    from app.providers.speaking_asr import provider_identity

    aid, rid, media = await completed(db_session, tmp_path)
    settings = Settings(speaking_profile="speaking_hybrid_v1", speaking_asr_enabled=True)

    class Partial(Analyzer):
        async def analyze(self, audio, **identity):
            result = await super().analyze(audio, **identity)
            return result.model_copy(update={"status": "PARTIAL", "error_code": "AZURE_TIMEOUT"})

    analyzer = Partial(settings)
    provider = SimpleNamespace(identity=provider_identity(settings), analyzer=analyzer)
    service = SpeakingTranscriptService(
        db_session, media.actor, settings, identity=provider.identity
    )
    run = await service.create(aid)
    worker = worker_for(db_session, settings, media.storage, provider)
    await worker.execute(run.run_id)
    snapshot = await service.get(aid, run.run_id)
    assert snapshot.status == "PARTIAL" and snapshot.responses[0].status == "PARTIAL"
    assert snapshot.responses[0].verbatim == "Yesterday I go"
    again = await service.create(aid)
    assert not again.cache_hit
    await worker.execute(again.run_id)
    assert len(analyzer.calls) == 1


async def test_unknown_billable_attempt_is_not_blindly_retried(db_session, tmp_path):
    import asyncio

    import pytest

    from app.core.exceptions import AppError
    from app.services.speaking_analysis_cache import cached_speech_analysis
    from app.services.speaking_audio import stage_normalized_audio

    _, rid, media = await completed(db_session, tmp_path)
    settings = Settings(speaking_profile="speaking_hybrid_v1", speaking_asr_enabled=True)
    analyzer = Analyzer(settings)
    calls = []

    async def cancelled(*args, **kwargs):
        calls.append(1)
        raise asyncio.CancelledError

    analyzer.analyze = cancelled
    worker = worker_for(db_session, settings, media.storage, None)
    ref = await normalize_committed_take(
        db_session, rid, settings, storage=media.storage, executor=fake_decode
    )
    async with stage_normalized_audio(media.storage, ref, 600) as audio:
        with pytest.raises(asyncio.CancelledError):
            await cached_speech_analysis(worker.sessions, audio, settings, analyzer)
        with pytest.raises(AppError) as error:
            await cached_speech_analysis(worker.sessions, audio, settings, analyzer)
        assert error.value.code == "SPEAKING_ANALYSIS_BILLING_UNKNOWN" and len(calls) == 1
