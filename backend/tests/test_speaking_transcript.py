import hashlib
import math
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from test_speaking_attempts import concurrent_speaking  # noqa: F401
from test_speaking_media import recording

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models.speaking_transcript import SpeakingTranscript
from app.providers.speaking_asr.base import ASRResult, WordTiming
from app.services.speaking_audio import NormalizedAudio, normalize_committed_take
from app.services.speaking_transcript import SpeakingTranscriptService
from app.services.speaking_transcript_worker import SpeakingTranscriptWorker


def fake_decode(args, timeout):
    with wave.open(str(args[-1]), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        samples = [int(5000 * math.sin(n / 10)) for n in range(16000)]
        output.writeframes(b"".join(n.to_bytes(2, "little", signed=True) for n in samples))


class FakeASR:
    identity = {"provider": "fake", "model": "fixture", "version": "v1", "language": "en"}

    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    async def transcribe(self, audio):
        assert isinstance(audio, NormalizedAudio) and audio.sample_rate == 16000
        self.calls.append(audio)
        if self.fail:
            raise RuntimeError("SECRET_PROVIDER_BODY /private/path")
        return ASRResult(
            text="  um, He go to school every day. She don't like it.  ",
            words=[WordTiming(word="um", start=0, end=0.2, confidence=0.8)],
            provider="fake",
            model="fixture",
            version="v1",
        )


@pytest.fixture(autouse=True)
def clean_files(tmp_path):
    yield
    for file in tmp_path.rglob("*"):
        if file.is_file():
            file.unlink()


async def completed(session, tmp_path):
    runtime, media, aid, prompts, state, segment = await recording(session, tmp_path, focused=0)
    await media.upload_chunk(aid, segment.id, 0, b"fictional container")
    await media.close_segment(aid, segment.id, 1)
    await runtime.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    return aid, state.response_id, media


def worker_for(session, settings, storage, provider):
    import asyncio

    fixture_connection = asyncio.Lock()

    @asynccontextmanager
    async def sessions():
        # This rollback fixture owns one connection. Independent request races
        # use concurrent_speaking's separate real PostgreSQL connections.
        async with fixture_connection:
            yield session

    return SpeakingTranscriptWorker(
        sessions, settings, provider=provider, storage=storage, executor=fake_decode
    )


async def test_normalization_orders_containers_and_caches_without_mutating_raw(
    db_session, tmp_path
):
    runtime, media, aid, prompts, state, first = await recording(db_session, tmp_path, focused=0)
    for seq, data in [(2, b"2"), (0, b"0"), (1, b"1")]:
        await media.upload_chunk(aid, first.id, seq, data)
    await media.close_segment(aid, first.id, 3)
    second = await media.create_segment(aid, prompts[0], 1, 1, "audio/webm")
    await media.upload_chunk(aid, second.id, 0, b"new-container")
    await media.close_segment(aid, second.id, 1)
    await runtime.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    calls = []

    def decode(args, timeout):
        calls.append(
            [Path(args[n + 1]).read_bytes() for n, value in enumerate(args) if value == "-i"]
        )
        assert "concat=n=2:v=0:a=1" in " ".join(args)
        assert args.count("-protocol_whitelist") == 2
        fake_decode(args, timeout)

    settings = Settings(storage_root=tmp_path)
    original = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*.webm")}
    audio = await normalize_committed_take(
        db_session, state.response_id, settings, storage=media.storage, executor=decode
    )
    again = await normalize_committed_take(
        db_session, state.response_id, settings, storage=media.storage, executor=decode
    )
    assert calls == [[b"012", b"new-container"]] and again.path == audio.path
    assert audio.channels == 1 and audio.duration_ms == 1000
    assert all(
        hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in original.items()
    )


async def test_normalizer_version_and_audio_identity_invalidate_cache(db_session, tmp_path):
    from app.models import SpeakingResponse

    aid, rid, media = await completed(db_session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    first = await normalize_committed_take(
        db_session, rid, settings, storage=media.storage, executor=fake_decode
    )
    settings.speaking_normalizer_version = "pcm-v2"
    second = await normalize_committed_take(
        db_session, rid, settings, storage=media.storage, executor=fake_decode
    )
    assert first.cache_key != second.cache_key and first.path != second.path
    async with db_session.begin():
        response = await db_session.get(SpeakingResponse, rid)
        response.committed_audio_fingerprint = "a" * 64  # Simulate a later committed revision.
    with pytest.raises(AppError):
        await normalize_committed_take(
            db_session, rid, settings, storage=media.storage, executor=fake_decode
        )


async def test_transcripts_persist_both_kinds_and_matching_run_reuses(db_session, tmp_path):
    aid, rid, media = await completed(db_session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    actor = db_session.info["current_user_identity"]
    provider = FakeASR()
    service = SpeakingTranscriptService(db_session, actor, settings, identity=provider.identity)
    first = await service.create(aid)
    assert (await service.create(aid)).run_id == first.run_id
    await worker_for(db_session, settings, media.storage, provider).execute(first.run_id)
    snapshot = await service.get(aid, first.run_id)
    assert snapshot.status == "COMPLETED" and snapshot.responses[0].status == "READY"
    assert snapshot.responses[0].clean == "um, He go to school every day. She don't like it."
    assert "He goes" not in snapshot.responses[0].clean
    assert (await service.create(aid)).cache_hit and len(provider.calls) == 1
    async with db_session.begin():
        rows = list(
            await db_session.scalars(
                select(SpeakingTranscript).where(SpeakingTranscript.response_id == rid)
            )
        )
        assert {r.kind for r in rows} == {"VERBATIM", "CLEAN"}
    changed = SpeakingTranscriptService(
        db_session, actor, settings, identity={**provider.identity, "version": "v2"}
    )
    assert (await changed.create(aid)).run_id != first.run_id


async def test_failed_provider_is_safe_retryable_and_never_logs_body(db_session, tmp_path, caplog):
    aid, _, media = await completed(db_session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    provider = FakeASR(fail=True)
    service = SpeakingTranscriptService(
        db_session, db_session.info["current_user_identity"], settings, identity=provider.identity
    )
    created = await service.create(aid)
    await worker_for(db_session, settings, media.storage, provider).execute(created.run_id)
    snapshot = await service.get(aid, created.run_id)
    assert (
        snapshot.status == "FAILED"
        and snapshot.responses[0].error_code == "TRANSCRIPT_GENERATION_FAILED"
    )
    assert "SECRET" not in caplog.text + snapshot.model_dump_json()
    assert (await service.create(aid)).run_id == created.run_id


@pytest.mark.parametrize(
    "word",
    [
        dict(word="bad", start=2, end=1),
        dict(word="bad", start=-1, end=2),
        dict(word="bad", start=0, end=1, confidence=2),
        dict(word="bad", start=float("nan"), end=1),
        dict(word="bad", start=0, end=float("inf")),
        dict(word="bad", start=0, end=1, confidence=float("nan")),
    ],
)
def test_invalid_word_timings_are_rejected(word):
    with pytest.raises(ValidationError):
        WordTiming(**word)


async def test_run_id_and_attempt_id_do_not_grant_access(db_session, tmp_path):
    from teacher_helpers import make_user

    aid, _, _ = await completed(db_session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    service = SpeakingTranscriptService(
        db_session, db_session.info["current_user_identity"], settings, identity=FakeASR.identity
    )
    created = await service.create(aid)
    for role in ("USER", "TEACHER"):
        outsider = await make_user(db_session, role)
        with pytest.raises(AppError):
            await SpeakingTranscriptService(db_session, outsider, settings).get(aid, created.run_id)
    with pytest.raises(AppError):
        await service.get(uuid4(), created.run_id)


def test_optional_adapter_is_lazy_and_unconfigured_is_safe():
    from app.providers.speaking_asr import create_provider

    with pytest.raises(AppError) as error:
        create_provider(Settings())
    assert error.value.code == "SPEAKING_ASR_UNAVAILABLE"


@pytest.mark.parametrize(
    "source,expected",
    [
        ("  He go to school every day.  ", "He go to school every day."),
        ("um,  uh, I- I went.\nI mean I go.", "um, uh, I- I went. I mean I go."),
        ("She have a apple.\n\nI very like it.", "She have a apple. I very like it."),
    ],
)
def test_formatting_preserves_grammar_and_disfluencies(source, expected):
    from app.services.speaking_transcript import format_transcript

    assert format_transcript(source) == expected


def test_provider_rejects_out_of_order_or_unbounded_transcript():
    for payload in [
        dict(text="   "),
        dict(text="x" * 60001),
        dict(text="words", words=[dict(word="x", start=0, end=0)] * 10001),
        dict(
            text="words", words=[dict(word="x", start=0, end=1), dict(word="y", start=0.5, end=2)]
        ),
        dict(
            text="words",
            words=[dict(word="later", start=2, end=3), dict(word="earlier", start=1, end=2)],
        ),
    ]:
        with pytest.raises(ValidationError):
            ASRResult(provider="fake", model="test", version="1", **payload)


async def test_optional_adapter_never_fetches_incomplete_local_model(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from app.providers.speaking_asr.faster_whisper import FasterWhisperProvider

    calls = []
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=lambda *args, **kwargs: calls.append(args)),
    )
    provider = FasterWhisperProvider(
        Settings(speaking_asr_enabled=True, speaking_asr_model_directory=str(tmp_path))
    )
    with pytest.raises(AppError) as error:
        await provider.transcribe(
            NormalizedAudio(tmp_path / "not-decoded.wav", "source", "pcm-v1", "cache", 1000)
        )
    assert error.value.code == "SPEAKING_ASR_UNAVAILABLE" and calls == []


def test_base_import_does_not_import_heavy_speech_packages():
    import sys

    import app.main

    assert app.main.app
    assert not any(name in sys.modules for name in ("faster_whisper", "ctranslate2", "torch"))


async def test_failure_is_isolated_and_retry_preserves_other_responses(
    db_session, tmp_path, monkeypatch
):
    from datetime import timedelta

    from test_speaking_attempts import started

    from app.domains.timers import TimerService
    from app.services.speaking_media import SpeakingMediaService
    from app.storage.local import LocalAssetStorage

    clock = [TimerService.now()]
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: clock[0]))
    runtime, aid, prompts = await started(db_session)
    media = SpeakingMediaService(
        db_session, db_session.info["current_user_identity"], storage=LocalAssetStorage(tmp_path)
    )
    for prompt in prompts:
        state = await runtime.begin_prompt(aid, prompt)
        if state.phase == "PREPARING":
            await runtime.save_notes(aid, prompt, "SPEAKING_PRIVATE_NOTE_SHOULD_NEVER_BE_GRADED")
            clock[0] += timedelta(seconds=63)
            await runtime.get_state(aid)
        segment = await media.create_segment(aid, prompt, 1, 0, "audio/webm")
        await media.upload_chunk(aid, segment.id, 0, b"fictional source")
        await media.close_segment(aid, segment.id, 1)
        await runtime.finish_current_response(aid, prompt, 1, "USER_DONE")

    class PartialASR(FakeASR):
        async def transcribe(self, audio):
            if len(self.calls) == 1:
                self.calls.append(audio)
                raise RuntimeError("PRIVATE_TRANSCRIPT_EXCEPTION")
            return await super().transcribe(audio)

    settings = Settings(storage_root=tmp_path)
    provider = PartialASR()
    service = SpeakingTranscriptService(
        db_session, db_session.info["current_user_identity"], settings, identity=provider.identity
    )
    created = await service.create(aid)
    await worker_for(db_session, settings, media.storage, provider).execute(created.run_id)
    snapshot = await service.get(aid, created.run_id)
    assert snapshot.status == "PARTIAL"
    assert [r.status for r in snapshot.responses].count("READY") == 3
    assert "SPEAKING_PRIVATE_NOTE" not in snapshot.model_dump_json()
    assert "PRIVATE_TRANSCRIPT_EXCEPTION" not in snapshot.model_dump_json()
    successful = {r.response_id: r.verbatim for r in snapshot.responses if r.status == "READY"}
    await service.create(aid)
    retry_provider = FakeASR()
    await worker_for(db_session, settings, media.storage, retry_provider).execute(created.run_id)
    retried = await service.get(aid, created.run_id)
    assert retried.status == "COMPLETED" and len(retry_provider.calls) == 1
    assert all(
        r.verbatim == successful[r.response_id]
        for r in retried.responses
        if r.response_id in successful
    )


async def test_normalized_derivatives_are_queued_on_personal_deletion(db_session, tmp_path):
    from app.services.attempts import AttemptService
    from app.services.speaking_media import drain_media_cleanup

    aid, rid, media = await completed(db_session, tmp_path)
    normalized = await normalize_committed_take(
        db_session,
        rid,
        Settings(storage_root=tmp_path),
        storage=media.storage,
        executor=fake_decode,
    )
    assert normalized.path.is_file()
    await AttemptService(db_session).delete_attempt(aid)
    await drain_media_cleanup(db_session, storage=media.storage)
    assert not normalized.path.exists() and list(tmp_path.rglob("*.webm")) == []


async def test_derived_cleanup_cannot_remove_another_attempt_reference(db_session, tmp_path):
    from app.models.speaking_transcript import SpeakingNormalizedAudio
    from app.services.attempts import AttemptService
    from app.services.speaking_media import drain_media_cleanup

    first_id, first_response, media = await completed(db_session, tmp_path)
    second_id, second_response, _ = await completed(db_session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    first = await normalize_committed_take(
        db_session, first_response, settings, storage=media.storage, executor=fake_decode
    )
    await normalize_committed_take(
        db_session, second_response, settings, storage=media.storage, executor=fake_decode
    )
    async with db_session.begin():
        owner_row = await db_session.scalar(
            select(SpeakingNormalizedAudio).where(
                SpeakingNormalizedAudio.response_id == first_response
            )
        )
        other_row = await db_session.scalar(
            select(SpeakingNormalizedAudio).where(
                SpeakingNormalizedAudio.response_id == second_response
            )
        )
        other_row.storage_key = owner_row.storage_key
    await AttemptService(db_session).delete_attempt(first_id)
    await drain_media_cleanup(db_session, storage=media.storage)
    assert first.path.is_file()
    await AttemptService(db_session).delete_attempt(second_id)
    await drain_media_cleanup(db_session, storage=media.storage)
    assert not first.path.exists()


async def test_stale_worker_token_cannot_persist_or_finish_recovered_run(db_session, tmp_path):
    from app.models.speaking_transcript import SpeakingTranscriptRun

    aid, rid, media = await completed(db_session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    service = SpeakingTranscriptService(
        db_session, db_session.info["current_user_identity"], settings, identity=FakeASR.identity
    )
    created = await service.create(aid)
    async with db_session.begin():
        run = await db_session.get(SpeakingTranscriptRun, created.run_id)
        run.status, run.lease_token = "RUNNING", "new-generation"
    worker = worker_for(db_session, settings, media.storage, FakeASR())
    assert not await worker._checkpoint(
        created.run_id,
        "old-generation",
        str(rid),
        error="TRANSCRIPT_GENERATION_FAILED",
        complete=True,
    )
    assert (await service.get(aid, created.run_id)).status == "RUNNING"


async def test_concurrent_create_reuses_one_durable_job(concurrent_speaking, monkeypatch):  # noqa: F811
    import asyncio
    from datetime import timedelta

    from app.domains.timers import TimerService
    from app.models import User
    from app.models.speaking_transcript import SpeakingTranscriptRun
    from app.services.speaking_attempts import SpeakingAttemptService

    factory, owner, aid, prompts = concurrent_speaking
    clock = [TimerService.now()]
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: clock[0]))
    async with factory() as session:
        runtime = SpeakingAttemptService(session, owner)
        for prompt in prompts:
            state = await runtime.begin_prompt(aid, prompt)
            if state.phase == "PREPARING":
                clock[0] += timedelta(seconds=63)
                await runtime.get_state(aid)
            await runtime.finish_current_response(aid, prompt, 1, "USER_DONE")

    async def create():
        async with factory() as session:
            async with session.begin():
                actor = await session.get(User, owner)
            return await SpeakingTranscriptService(
                session, actor, Settings(), identity=FakeASR.identity
            ).create(aid)

    first, second = await asyncio.gather(create(), create())
    assert first.run_id == second.run_id
    assert sum(r.existing_active for r in (first, second)) == 1
    async with factory() as session:
        rows = list(
            await session.scalars(
                select(SpeakingTranscriptRun).where(SpeakingTranscriptRun.attempt_id == aid)
            )
        )
        assert len(rows) == 1 and rows[0].status == "PENDING"


async def test_optional_adapter_local_only_boundary_with_fake_model(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from app.providers.speaking_asr.faster_whisper import FasterWhisperProvider

    model_dir = tmp_path / "fictional-model"
    model_dir.mkdir()
    for name in ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"):
        (model_dir / name).write_bytes(b"synthetic adapter fixture")
    audio_path = tmp_path / "normalized.wav"
    fake_decode([str(audio_path)], 1)
    calls = []

    class Model:
        def __init__(self, path, **kwargs):
            calls.append((path, kwargs))

        def transcribe(self, path, **kwargs):
            assert path == str(audio_path) and kwargs["word_timestamps"]
            words = [SimpleNamespace(word="He", start=0, end=0.1, probability=0.8)]
            return [SimpleNamespace(text="He go to school.", words=words)], SimpleNamespace(
                language="en"
            )

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    provider = FasterWhisperProvider(
        Settings(speaking_asr_enabled=True, speaking_asr_model_directory=str(model_dir))
    )
    result = await provider.transcribe(
        NormalizedAudio(audio_path, "source", "pcm-v1", "cache", 1000)
    )
    assert result.text == "He go to school." and result.words[0].confidence == 0.8
    assert calls == [
        (str(model_dir), {"device": "cpu", "compute_type": "int8", "local_files_only": True})
    ]


async def test_lifespan_exception_still_stops_both_worker_registries(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    import app.main as main
    import app.services.speaking_media as media

    monkeypatch.setattr(main.settings, "storage_root", tmp_path)
    monkeypatch.setattr(media, "cleanup_private_media", AsyncMock())
    monkeypatch.setattr(SpeakingTranscriptWorker, "recover", AsyncMock())
    speaking, writing = AsyncMock(), AsyncMock()
    monkeypatch.setattr(main, "stop_speaking_transcript_workers", speaking)
    monkeypatch.setattr(main, "stop_writing_ai_workers", writing)
    with pytest.raises(RuntimeError, match="fixture shutdown"):
        async with main.lifespan(main.app):
            raise RuntimeError("fixture shutdown")
    speaking.assert_awaited_once()
    writing.assert_awaited_once()


@pytest.mark.parametrize("damage", ["missing", "corrupt", "path", "cached"])
async def test_normalization_missing_corrupt_and_private_paths_fail_closed(
    db_session, tmp_path, damage
):
    from app.models.speaking import SpeakingAudioChunk
    from app.models.speaking_transcript import SpeakingNormalizedAudio

    _, rid, media = await completed(db_session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    if damage == "cached":
        audio = await normalize_committed_take(
            db_session, rid, settings, storage=media.storage, executor=fake_decode
        )
        audio.path.write_bytes(b"broken cached derivative")
        # A broken derivative must be rebuilt, never handed to ASR as valid PCM.
        repaired = await normalize_committed_take(
            db_session, rid, settings, storage=media.storage, executor=fake_decode
        )
        with wave.open(str(repaired.path)) as decoded:
            assert decoded.getnframes() == 16000
        async with db_session.begin():
            assert (
                len(
                    list(
                        await db_session.scalars(
                            select(SpeakingNormalizedAudio).where(
                                SpeakingNormalizedAudio.response_id == rid
                            )
                        )
                    )
                )
                == 1
            )
        return
    async with db_session.begin():
        chunk = await db_session.scalar(select(SpeakingAudioChunk))
        path = media.storage.resolve(chunk.storage_key)
        if damage == "path":
            chunk.storage_key = "speaking-private/../../outside.webm"
        elif damage == "missing":
            path.unlink()
        else:
            path.write_bytes(b"changed source")
    with pytest.raises(AppError) as caught:
        await normalize_committed_take(
            db_session, rid, settings, storage=media.storage, executor=fake_decode
        )
    assert caught.value.code == "SPEAKING_AUDIO_UNASSESSABLE"
    assert str(tmp_path) not in caught.value.message
    assert list(tmp_path.rglob("*.wav")) == []


@pytest.fixture
async def durable_transcript(concurrent_speaking, tmp_path, monkeypatch):  # noqa: F811
    from datetime import timedelta

    from app.domains.timers import TimerService
    from app.models import User
    from app.services.speaking_attempts import SpeakingAttemptService
    from app.services.speaking_media import SpeakingMediaService
    from app.storage.local import LocalAssetStorage

    factory, owner, aid, prompts = concurrent_speaking
    clock = [TimerService.now()]
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: clock[0]))
    storage = LocalAssetStorage(tmp_path)
    ids = []
    async with factory() as session:
        async with session.begin():
            actor = await session.get(User, owner)
        runtime = SpeakingAttemptService(session, owner)
        media = SpeakingMediaService(session, actor, storage=storage)
        for index, prompt in enumerate(prompts):
            state = await runtime.begin_prompt(aid, prompt)
            ids.append(state.response_id)
            if state.phase == "PREPARING":
                await runtime.save_notes(
                    aid, prompt, "THIS_SECRET_NOTE_MUST_NOT_ENTER_SPEECH_ANALYSIS_98765"
                )
                clock[0] += timedelta(seconds=63)
                await runtime.get_state(aid)
            segment = await media.create_segment(aid, prompt, 1, 0, "audio/webm")
            await media.upload_chunk(aid, segment.id, 0, f"fictional Q{index + 1}".encode())
            await media.close_segment(aid, segment.id, 1)
            await runtime.finish_current_response(aid, prompt, 1, "USER_DONE")
    yield factory, actor, aid, ids, storage, Settings(storage_root=tmp_path)


async def create_durable(context, *, identity=None, settings=None):
    factory, actor, aid, _, _, configured = context
    async with factory() as session:
        return await SpeakingTranscriptService(
            session, actor, settings or configured, identity=identity or FakeASR.identity
        ).create(aid)


async def test_fresh_sessions_concurrent_worker_dedup_durable_artifacts_and_events(
    durable_transcript,
):
    import asyncio

    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError

    from app.models.speaking_transcript import SpeakingTranscriptEvent, SpeakingTranscriptRun

    factory, actor, aid, ids, storage, settings = durable_transcript
    first, second = await asyncio.gather(
        create_durable(durable_transcript), create_durable(durable_transcript)
    )
    assert first.run_id == second.run_id
    provider = FakeASR()
    workers = [
        SpeakingTranscriptWorker(
            factory, settings, provider=provider, storage=storage, executor=fake_decode
        )
        for _ in range(2)
    ]
    await asyncio.gather(*(w.execute(first.run_id) for w in workers))
    assert len(provider.calls) == 4
    async with factory() as session, session.begin():
        run = await session.get(SpeakingTranscriptRun, first.run_id)
        assert (
            run.status == "COMPLETED"
            and run.requested_by_user_id == actor.id
            and run.attempt_id == aid
        )
        assert run.created_at and run.updated_at and run.heartbeat_at and run.lease_token is None
        assert run.identity_json["asr"] == provider.identity
        assert {item["response_id"] for item in run.manifest_json} == {str(r) for r in ids}
        artifacts = list(
            await session.scalars(
                select(SpeakingTranscript).where(SpeakingTranscript.run_id == run.id)
            )
        )
        assert len(artifacts) == 8 and {t.kind for t in artifacts} == {"VERBATIM", "CLEAN"}
        for transcript in artifacts:
            assert (
                "He go" in transcript.text
                and "She don't" in transcript.text
                and "He goes" not in transcript.text
            )
            assert transcript.source_audio_fingerprint in {
                a.source_audio_fingerprint for a in provider.calls
            }
            assert (
                transcript.provider_json["model"] == "fixture"
                and transcript.word_timing_json[0]["confidence"] == 0.8
            )
            bundle = transcript.provider_json["evidence"]
            assert bundle["source_audio_fingerprint"] == transcript.source_audio_fingerprint
            assert (
                bundle["quality"]["state"] == "AUDIO_OK"
                and bundle["fluency"]["timing_status"] == "PARTIAL"
            )
            assert "THIS_SECRET_NOTE_MUST_NOT_ENTER_SPEECH_ANALYSIS_98765" not in str(bundle)
        events = list(
            await session.scalars(
                select(SpeakingTranscriptEvent)
                .where(SpeakingTranscriptEvent.run_id == run.id)
                .order_by(SpeakingTranscriptEvent.sequence)
            )
        )
        assert [e.sequence for e in events] == list(range(1, 12))
        assert all(set(e.payload) <= {"response_id", "status", "error_code"} for e in events)
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(
                    SpeakingTranscriptEvent(
                        run_id=run.id, sequence=1, event_type="duplicate", payload={}
                    )
                )
                await session.flush()
        duplicate = artifacts[0]
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(
                    SpeakingTranscript(
                        response_id=duplicate.response_id,
                        run_id=run.id,
                        cache_key=duplicate.cache_key,
                        source_audio_fingerprint=duplicate.source_audio_fingerprint,
                        kind=duplicate.kind,
                        text="duplicate",
                        word_timing_json=[],
                        provider_json={},
                    )
                )
                await session.flush()
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SpeakingTranscript)
                .where(SpeakingTranscript.run_id == run.id)
            )
            == 8
        )
    assert (await create_durable(durable_transcript)).cache_hit
    assert len(provider.calls) == 4
    async with factory() as session:
        snapshot, events = await SpeakingTranscriptService(
            session, actor, settings, identity=provider.identity
        ).snapshot(aid, first.run_id, after=8)
        assert snapshot.status == "COMPLETED" and [e.sequence for e in events] == [9, 10, 11]
        assert (
            "THIS_SECRET_NOTE" not in snapshot.model_dump_json()
            and "storage_key" not in snapshot.model_dump_json()
        )


@pytest.mark.parametrize(
    "change", ["provider", "model", "version", "config", "normalizer", "audio", "take"]
)
async def test_current_cache_invalidates_each_material_identity(db_session, tmp_path, change):
    from app.models.speaking import SpeakingAudioChunk, SpeakingResponse, SpeakingResponseTake
    from app.services.speaking_media import committed_fingerprint

    aid, rid, media = await completed(db_session, tmp_path)
    settings, identity = Settings(storage_root=tmp_path), dict(FakeASR.identity)
    actor = db_session.info["current_user_identity"]
    old = SpeakingTranscriptService(db_session, actor, settings, identity=identity)
    created = await old.create(aid)
    await worker_for(db_session, settings, media.storage, FakeASR()).execute(created.run_id)
    if change in {"audio", "take"}:
        # Administrative fixture replacement represents a future committed revision.
        # Runtime retry of a locked prompt remains forbidden by P3.
        async with db_session.begin():
            response = await db_session.get(SpeakingResponse, rid)
            take = await db_session.scalar(
                select(SpeakingResponseTake).where(SpeakingResponseTake.response_id == rid)
            )
            if change == "take":
                take.take_number = response.active_take_number = 2
            else:
                chunk = await db_session.scalar(select(SpeakingAudioChunk))
                media.storage.resolve(chunk.storage_key).write_bytes(b"new committed bytes")
                chunk.sha256 = hashlib.sha256(b"new committed bytes").hexdigest()
                chunk.byte_size = len(b"new committed bytes")
            await db_session.flush()
            response.committed_audio_fingerprint = await committed_fingerprint(db_session, take)
        stale = await old.get(aid, created.run_id)
        assert (
            stale.responses[0].error_code == "TRANSCRIPT_SOURCE_CHANGED"
            and stale.responses[0].verbatim is None
        )
    elif change == "normalizer":
        settings.speaking_normalizer_version = "pcm-next"
    else:
        identity["config_hash" if change == "config" else change] = "changed"
    current = SpeakingTranscriptService(db_session, actor, settings, identity=identity)
    assert await current.latest(aid) is None
    assert (await current.create(aid)).run_id != created.run_id


async def test_q3_failure_and_checkpoint_rollback_preserve_other_durable_responses(
    durable_transcript, monkeypatch
):
    from app.models.speaking import SpeakingResponse
    from app.repositories.speaking_transcript import SpeakingTranscriptRepository

    factory, actor, aid, ids, storage, settings = durable_transcript
    async with factory() as session:
        bad_source = (await session.get(SpeakingResponse, ids[2])).committed_audio_fingerprint

    class Partial(FakeASR):
        async def transcribe(self, audio):
            if audio.source_audio_fingerprint == bad_source:
                raise TimeoutError("PRIVATE_TIMEOUT_BODY")
            return await super().transcribe(audio)

    original = SpeakingTranscriptRepository.append
    failed = []

    async def append(repository, run, event_type, payload=None):
        if (
            payload
            and payload.get("response_id") == str(ids[1])
            and payload.get("status") == "READY"
            and not failed
        ):
            failed.append(True)
            raise RuntimeError("PRIVATE_SQL_CHECKPOINT")
        return await original(repository, run, event_type, payload)

    monkeypatch.setattr(SpeakingTranscriptRepository, "append", append)
    created = await create_durable(durable_transcript)
    await SpeakingTranscriptWorker(
        factory, settings, provider=Partial(), storage=storage, executor=fake_decode
    ).execute(created.run_id)
    async with factory() as session:
        result = await SpeakingTranscriptService(
            session, actor, settings, identity=FakeASR.identity
        ).get(aid, created.run_id)
        by_id = {r.response_id: r for r in result.responses}
        assert result.status == "PARTIAL"
        assert [by_id[r].status for r in ids] == ["READY", "FAILED", "FAILED", "READY"]
        assert "PRIVATE" not in result.model_dump_json()
        async with session.begin():
            assert {
                t.response_id
                for t in await session.scalars(
                    select(SpeakingTranscript).where(SpeakingTranscript.run_id == created.run_id)
                )
            } == {ids[0], ids[3]}
    await create_durable(durable_transcript)
    provider = FakeASR()
    await SpeakingTranscriptWorker(
        factory, settings, provider=provider, storage=storage, executor=fake_decode
    ).execute(created.run_id)
    assert len(provider.calls) == 2


async def test_http_create_replay_authorization_and_disconnect_are_observation_only(
    durable_transcript, monkeypatch
):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from teacher_helpers import api_client, make_user

    import app.services.speaking_transcript as service_module
    from app.api.v1.speaking import get_transcript_worker, transcript_event_stream
    from app.core.config import get_settings
    from app.main import app
    from app.models.speaking_transcript import SpeakingTranscriptRun
    from app.services.speaking_transcript_worker import _tasks, stop_speaking_transcript_workers

    factory, actor, aid, _, storage, settings = durable_transcript
    for configured in (settings, get_settings()):
        monkeypatch.setattr(configured, "speaking_asr_enabled", True)
        monkeypatch.setattr(configured, "speaking_asr_model_directory", "fake-only")
    monkeypatch.setattr(service_module, "provider_identity", lambda _: FakeASR.identity)
    entered, release = asyncio.Event(), asyncio.Event()

    class Blocked(FakeASR):
        async def transcribe(self, audio):
            entered.set()
            await release.wait()
            return await super().transcribe(audio)

    worker = SpeakingTranscriptWorker(
        factory, settings, provider=Blocked(), storage=storage, executor=fake_decode
    )
    app.dependency_overrides[get_transcript_worker] = lambda: worker
    try:
        async with factory() as session, api_client(session, actor) as client:
            path = f"/api/v1/speaking-attempts/{aid}/transcript-runs"
            posted = await asyncio.wait_for(client.post(path), 3)
            assert posted.status_code == 200
            run_id = __import__("uuid").UUID(posted.json()["run_id"])
            await asyncio.wait_for(entered.wait(), 3)
            async with factory() as fresh:
                durable = await fresh.get(SpeakingTranscriptRun, run_id)
                assert durable.status == "RUNNING"
            assert (await client.post(path)).json()["run_id"] == str(run_id)
            # A disconnected subscriber cannot cancel the detached worker.
            observer = transcript_event_stream(
                SimpleNamespace(is_disconnected=AsyncMock(return_value=True)),
                aid,
                run_id,
                actor,
                worker,
                0,
            )
            assert [event async for event in observer] == [] and run_id in _tasks
            release.set()
            await asyncio.wait_for(_tasks[run_id], 5)
            got = await client.get(f"{path}/{run_id}")
            assert got.json()["status"] == "COMPLETED"
            stream = await asyncio.wait_for(
                client.get(f"{path}/{run_id}/events?after=7", headers={"Last-Event-ID": "8"}), 3
            )
            assert (
                stream.status_code == 200
                and stream.headers["cache-control"] == "no-cache, no-store"
                and stream.headers["x-accel-buffering"] == "no"
            )
            assert [
                int(line[4:]) for line in stream.text.splitlines() if line.startswith("id: ")
            ] == [9, 10, 11]
            assert (
                "He go" not in stream.text
                and "storage_key" not in got.text
                and str(storage.root) not in got.text
            )
            assert (await client.get(f"{path}/{uuid4()}")).status_code == 404
            assert (
                await client.get(f"{path}/{run_id}/events", headers={"Last-Event-ID": "bad"})
            ).status_code == 422
        async with factory() as session:
            outsider = await make_user(session, "TEACHER")
            try:
                async with api_client(session, outsider) as client:
                    assert (await client.get(f"{path}/{run_id}/events")).status_code in {403, 404}
            finally:
                from sqlalchemy import delete

                from app.models import User

                async with session.begin():
                    await session.execute(delete(User).where(User.id == outsider.id))
    finally:
        release.set()
        await stop_speaking_transcript_workers()
        app.dependency_overrides.pop(get_transcript_worker, None)


async def test_assignment_provenance_grants_read_only_transcript_access(db_session, tmp_path):
    from teacher_helpers import make_user

    from app.models import Attempt, Classroom, ClassroomAssignment

    teacher, unrelated = (
        await make_user(db_session, "TEACHER"),
        await make_user(db_session, "TEACHER"),
    )
    aid, _, media = await completed(db_session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    owner = SpeakingTranscriptService(
        db_session, db_session.info["current_user_identity"], settings, identity=FakeASR.identity
    )
    created = await owner.create(aid)
    await worker_for(db_session, settings, media.storage, FakeASR()).execute(created.run_id)
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        classrooms = [Classroom(teacher_id=t.id, name="Fictional") for t in (teacher, unrelated)]
        db_session.add_all(classrooms)
        await db_session.flush()
        assignment = ClassroomAssignment(
            classroom_id=classrooms[0].id,
            test_version_id=attempt.test_version_id,
            created_by_user_id=teacher.id,
        )
        db_session.add(assignment)
        await db_session.flush()
        attempt.classroom_assignment_id = assignment.id
    allowed = SpeakingTranscriptService(db_session, teacher, settings, identity=FakeASR.identity)
    assert (await allowed.get(aid, created.run_id)).responses[0].verbatim
    with pytest.raises(AppError) as caught:
        await allowed.create(aid)
    assert caught.value.code == "SPEAKING_MEDIA_FORBIDDEN"
    with pytest.raises(AppError):
        await SpeakingTranscriptService(db_session, unrelated, settings).get(aid, created.run_id)
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        attempt.classroom_assignment_id = None
    with pytest.raises(AppError):
        await allowed.get(aid, created.run_id)


async def test_shutdown_and_stale_restart_preserve_checkpoints(durable_transcript, monkeypatch):
    import asyncio
    from datetime import timedelta

    from app.domains.timers import TimerService
    from app.models.speaking_transcript import SpeakingTranscriptRun
    from app.services.speaking_transcript_worker import _tasks, stop_speaking_transcript_workers

    factory, actor, aid, _, storage, settings = durable_transcript
    blocked = asyncio.Event()

    class Waiting(FakeASR):
        async def transcribe(self, audio):
            if self.calls:
                blocked.set()
                await asyncio.Event().wait()
            return await super().transcribe(audio)

    created = await create_durable(durable_transcript)
    worker = SpeakingTranscriptWorker(
        factory, settings, provider=Waiting(), storage=storage, executor=fake_decode
    )
    worker.launch(created.run_id)
    try:
        await asyncio.wait_for(blocked.wait(), 5)
        await stop_speaking_transcript_workers()
        assert not _tasks
        async with factory() as session, session.begin():
            run = await session.get(SpeakingTranscriptRun, created.run_id)
            assert run.status == "PENDING" and run.lease_token is None
            assert sum(s["status"] == "READY" for s in run.responses_json.values()) == 1
            run.status, run.lease_token = "RUNNING", "expired-lease"
            run.heartbeat_at = TimerService.now() - timedelta(seconds=301)
        recovered = []
        monkeypatch.setattr(worker, "launch", recovered.append)
        await worker.recover()
        assert created.run_id in recovered
        provider = FakeASR()
        await SpeakingTranscriptWorker(
            factory, settings, provider=provider, storage=storage, executor=fake_decode
        ).execute(created.run_id)
        async with factory() as session:
            snapshot = await SpeakingTranscriptService(
                session, actor, settings, identity=provider.identity
            ).get(aid, created.run_id)
            assert snapshot.status == "COMPLETED" and len(provider.calls) == 3
    finally:
        await stop_speaking_transcript_workers()


@pytest.mark.parametrize("failure", ["empty", "oversized", "timing", "timeout", "unavailable"])
async def test_invalid_provider_outputs_never_become_ready(db_session, tmp_path, failure):
    aid, _, media = await completed(db_session, tmp_path)
    settings = Settings(storage_root=tmp_path)

    class Invalid(FakeASR):
        async def transcribe(self, audio):
            if failure == "timeout":
                raise TimeoutError("PRIVATE_TIMEOUT")
            if failure == "unavailable":
                raise AppError("SPEAKING_ASR_UNAVAILABLE", "PRIVATE_PROVIDER_MESSAGE", 503)
            return {
                "text": ""
                if failure == "empty"
                else "x" * 60001
                if failure == "oversized"
                else "word",
                "words": [{"word": "word", "start": 0, "end": 5}] if failure == "timing" else [],
                "provider": "fake",
                "model": "fixture",
                "version": "v1",
            }

    service = SpeakingTranscriptService(
        db_session, db_session.info["current_user_identity"], settings, identity=FakeASR.identity
    )
    created = await service.create(aid)
    await worker_for(db_session, settings, media.storage, Invalid()).execute(created.run_id)
    snapshot = await service.get(aid, created.run_id)
    assert snapshot.status == "FAILED" and snapshot.responses[0].verbatim is None
    assert snapshot.responses[0].error_code == (
        "SPEAKING_ASR_UNAVAILABLE" if failure == "unavailable" else "TRANSCRIPT_GENERATION_FAILED"
    )
    assert "PRIVATE" not in snapshot.model_dump_json()


async def test_quality_gate_persists_before_asr_and_versions_run_cache(db_session, tmp_path):
    from app.models.speaking_transcript import SpeakingNormalizedAudio

    aid, _, media = await completed(db_session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    actor = db_session.info["current_user_identity"]
    service = SpeakingTranscriptService(db_session, actor, settings, identity=FakeASR.identity)
    created = await service.create(aid)

    def silent_decode(args, timeout):
        with wave.open(str(args[-1]), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\0\0" * 16000)

    provider = FakeASR()
    worker = worker_for(db_session, settings, media.storage, provider)
    worker.executor = silent_decode
    await worker.execute(created.run_id)
    result = await service.get(aid, created.run_id)
    assert (
        result.status == "FAILED"
        and result.responses[0].error_code == "NO_SPEECH"
        and not provider.calls
    )
    async with db_session.begin():
        row = await db_session.scalar(select(SpeakingNormalizedAudio))
        assert row.metadata_json["quality"]["state"] == "NO_SPEECH"
    settings.speaking_quality.version = "quality-next"
    current = SpeakingTranscriptService(db_session, actor, settings, identity=FakeASR.identity)
    assert await current.latest(aid) is None
    assert (await current.create(aid)).run_id != created.run_id


async def test_part2_bundle_round_trip_and_unavailable_pr_preserve_transcript(durable_transcript):
    factory, actor, aid, ids, storage, settings = durable_transcript
    settings.speaking_pronunciation_enabled = False

    class Aligned(FakeASR):
        async def transcribe(self, audio):
            self.calls.append(audio)
            return ASRResult(
                text="He go",
                words=[
                    WordTiming(word="He", start=0, end=0.2, confidence=0.9),
                    WordTiming(word="go", start=0.2, end=0.4, confidence=0.9),
                ],
                provider="fake",
                model="fixture",
                version="v1",
            )

    created = await create_durable(durable_transcript)
    await SpeakingTranscriptWorker(
        factory, settings, provider=Aligned(), storage=storage, executor=fake_decode
    ).execute(created.run_id)
    async with factory() as session, session.begin():
        rows = list(
            await session.scalars(
                select(SpeakingTranscript).where(
                    SpeakingTranscript.run_id == created.run_id,
                    SpeakingTranscript.kind == "VERBATIM",
                )
            )
        )
        assert len(rows) == 4
        by_id = {r.response_id: r.provider_json["evidence"] for r in rows}
        assert by_id[ids[1]]["fluency"]["part2_sustained_seconds"] == 0.4
        assert by_id[ids[0]]["fluency"]["part2_sustained_seconds"] is None
        assert by_id[ids[2]]["fluency"]["part2_sustained_seconds"] is None  # authored follow-up
        assert all(
            b["pronunciation"]["error_code"] == "PROVIDER_UNAVAILABLE" for b in by_id.values()
        )
        assert "THIS_SECRET_NOTE_MUST_NOT_ENTER_SPEECH_ANALYSIS_98765" not in str(by_id)
    async with factory() as session:
        current = SpeakingTranscriptService(session, actor, settings, identity=FakeASR.identity)
        assert (await current.get(aid, created.run_id)).status == "COMPLETED"
        settings.speaking_pronunciation.version = "prosody-next"
        assert (
            await SpeakingTranscriptService(
                session, actor, settings, identity=FakeASR.identity
            ).latest(aid)
            is None
        )
