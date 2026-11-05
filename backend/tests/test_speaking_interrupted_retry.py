"""Explicit interrupted-call recovery uses fictional audio and never a live provider."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from teacher_helpers import make_user
from test_speaking_attempts import concurrent_speaking  # noqa: F401
from test_speaking_hybrid_worker import Analyzer
from test_speaking_transcript import (
    completed,
    durable_transcript,  # noqa: F401
    fake_decode,
    worker_for,
)

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models.speaking_transcript import (
    SpeakingNormalizedAudio,
    SpeakingTranscriptEvent,
    SpeakingTranscriptRun,
)
from app.providers.speaking_asr import provider_identity
from app.schemas.speaking_ai import TranscriptCreateRequest
from app.services.speaking_transcript import SpeakingTranscriptService
from app.services.speaking_transcript_worker import SpeakingTranscriptWorker


def configured():
    return Settings(
        _env_file=None,
        speaking_profile="speaking_hybrid_v1",
        speaking_asr_enabled=True,
        speaking_azure_billing_mode="free_only",
    )


def retry_request(snapshot, response_ids):
    return {
        "retry_interrupted_response_ids": response_ids,
        "retry_interrupted_run_id": snapshot.run_id,
        "retry_interrupted_after_sequence": snapshot.last_sequence,
    }


def test_interrupted_retry_request_defaults_and_rejects_unbounded_or_unknown_inputs():
    assert TranscriptCreateRequest().retry_interrupted_response_ids == []
    rid, run_id = uuid4(), uuid4()
    assert TranscriptCreateRequest(
        retry_interrupted_response_ids=[str(rid)],
        retry_interrupted_run_id=run_id,
        retry_interrupted_after_sequence=1,
    ).retry_interrupted_response_ids == [rid]
    for body in (
        {"allow_interrupted_retry": True},
        {"retry_interrupted_response_ids": ["not-a-uuid"]},
        {"retry_interrupted_response_ids": [str(rid)] * 1001},
        {"retry_interrupted_response_ids": [str(rid)]},
        {"retry_interrupted_response_ids": [str(rid)], "retry_interrupted_run_id": run_id},
        {"retry_interrupted_run_id": run_id, "retry_interrupted_after_sequence": 1},
        {
            "retry_interrupted_response_ids": [str(rid)],
            "retry_interrupted_run_id": run_id,
            "retry_interrupted_after_sequence": -1,
        },
    ):
        with pytest.raises(ValidationError):
            TranscriptCreateRequest.model_validate(body)


async def test_transcript_post_accepts_no_body_and_passes_only_explicit_retry_ids(monkeypatch):
    from unittest.mock import AsyncMock, Mock, call

    import httpx

    from app.api.dependencies import get_current_user
    from app.api.v1 import speaking
    from app.core.database import get_session
    from app.main import app
    from app.schemas.speaking_ai import TranscriptCreated

    aid, rid, run_id = uuid4(), uuid4(), uuid4()
    service = SimpleNamespace(
        create=AsyncMock(
            return_value=TranscriptCreated(run_id=run_id, cache_hit=False, existing_active=False)
        )
    )
    worker = SimpleNamespace(launch=Mock())
    monkeypatch.setattr(speaking, "SpeakingTranscriptService", lambda *_args: service)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: SimpleNamespace())
    monkeypatch.setitem(app.dependency_overrides, get_session, lambda: None)
    monkeypatch.setitem(app.dependency_overrides, speaking.get_transcript_worker, lambda: worker)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fictional.test"
    ) as client:
        path = f"/api/v1/speaking-attempts/{aid}/transcript-runs"
        assert (await client.post(path)).status_code == 200
        assert (await client.post(path, json={})).status_code == 200
        explicit = await client.post(
            path,
            json={
                "retry_interrupted_response_ids": [str(rid)],
                "retry_interrupted_run_id": str(run_id),
                "retry_interrupted_after_sequence": 3,
            },
        )
        assert explicit.status_code == 200 and explicit.json()["run_id"] == str(run_id)
    assert service.create.await_args_list == [
        call(
            aid,
            retry_interrupted_response_ids=(),
            retry_interrupted_run_id=None,
            retry_interrupted_after_sequence=None,
        ),
        call(
            aid,
            retry_interrupted_response_ids=[],
            retry_interrupted_run_id=None,
            retry_interrupted_after_sequence=None,
        ),
        call(
            aid,
            retry_interrupted_response_ids=[rid],
            retry_interrupted_run_id=run_id,
            retry_interrupted_after_sequence=3,
        ),
    ]
    assert worker.launch.call_count == 3


@pytest.mark.parametrize(
    "run_status,response_status,error_code",
    [
        ("PENDING", "FAILED", "SPEAKING_ANALYSIS_BILLING_UNKNOWN"),
        ("RUNNING", "FAILED", "SPEAKING_ANALYSIS_BILLING_UNKNOWN"),
        ("COMPLETED", "READY", None),
        ("PARTIAL", "READY", None),
        ("PARTIAL", "PARTIAL", None),
        ("FAILED", "FAILED", "TOO_SHORT"),
        ("FAILED", "FAILED", "SPEAKING_AZURE_QUOTA_EXCEEDED"),
    ],
)
async def test_explicit_retry_rejects_active_ready_or_other_failures(
    db_session, tmp_path, run_status, response_status, error_code
):
    aid, rid, media = await completed(db_session, tmp_path)
    settings = configured()
    identity = provider_identity(settings)
    service = SpeakingTranscriptService(db_session, media.actor, settings, identity=identity)
    created = await service.create(aid)
    state = {"status": response_status}
    if error_code:
        state["error_code"] = error_code
    async with db_session.begin():
        run = await db_session.get(SpeakingTranscriptRun, created.run_id)
        run.status = run_status
        run.responses_json = {str(rid): state}
    with pytest.raises(AppError) as error:
        await service.create(
            aid,
            retry_interrupted_response_ids=[rid],
            retry_interrupted_run_id=created.run_id,
            retry_interrupted_after_sequence=1,
        )
    assert error.value.code == "SPEAKING_INTERRUPTED_RETRY_NOT_AVAILABLE"
    async with db_session.begin():
        run = await db_session.get(SpeakingTranscriptRun, created.run_id)
        assert run.status == run_status and run.responses_json == {str(rid): state}


async def test_explicit_retry_requires_owner_and_exact_existing_response_subset(
    db_session, tmp_path
):
    aid, rid, media = await completed(db_session, tmp_path)
    settings = configured()
    identity = provider_identity(settings)
    service = SpeakingTranscriptService(db_session, media.actor, settings, identity=identity)
    with pytest.raises(AppError) as missing:
        await service.create(aid, retry_interrupted_response_ids=[rid])
    assert missing.value.code == "SPEAKING_INTERRUPTED_RETRY_NOT_AVAILABLE"
    created = await service.create(aid)
    state = {"status": "FAILED", "error_code": "SPEAKING_ANALYSIS_BILLING_UNKNOWN"}
    async with db_session.begin():
        run = await db_session.get(SpeakingTranscriptRun, created.run_id)
        run.status, run.responses_json = "FAILED", {str(rid): state}
    outsider = await make_user(db_session)
    with pytest.raises(AppError) as unauthorized:
        await SpeakingTranscriptService(db_session, outsider, settings, identity=identity).create(
            aid,
            retry_interrupted_response_ids=[rid],
            retry_interrupted_run_id=created.run_id,
            retry_interrupted_after_sequence=1,
        )
    assert unauthorized.value.code == "SPEAKING_MEDIA_FORBIDDEN"
    with pytest.raises(AppError) as unrelated:
        await service.create(
            aid,
            retry_interrupted_response_ids=[rid, uuid4()],
            retry_interrupted_run_id=created.run_id,
            retry_interrupted_after_sequence=1,
        )
    assert unrelated.value.code == "SPEAKING_INTERRUPTED_RETRY_NOT_AVAILABLE"
    async with db_session.begin():
        run = await db_session.get(SpeakingTranscriptRun, created.run_id)
        assert run.status == "FAILED" and run.responses_json == {str(rid): state}


async def test_explicit_retry_replays_only_selected_interruption_and_preserves_ready_and_history(
    durable_transcript,  # noqa: F811
):
    factory, actor, aid, _, storage, _ = durable_transcript
    settings = configured()

    class Interrupted(Analyzer):
        async def analyze(self, audio, **identity):
            # Simulate two interrupted requests whose final results were never checkpointed.
            result = await super().analyze(audio, **identity)
            if len(self.calls) in (2, 3):
                raise RuntimeError("fictional interrupted checkpoint")
            return result

    analyzer = Interrupted(settings)
    provider = SimpleNamespace(identity=provider_identity(settings), analyzer=analyzer)
    worker = SpeakingTranscriptWorker(
        factory, settings, provider=provider, storage=storage, executor=fake_decode
    )

    async def create(**kwargs):
        async with factory() as session:
            return await SpeakingTranscriptService(
                session, actor, settings, identity=provider.identity
            ).create(aid, **kwargs)

    async def snapshot(run_id):
        async with factory() as session:
            return await SpeakingTranscriptService(
                session, actor, settings, identity=provider.identity
            ).get(aid, run_id)

    created = await create()
    await worker.execute(created.run_id)
    first = await snapshot(created.run_id)
    ready_ids = {r.response_id for r in first.responses if r.status == "READY"}
    assert len(ready_ids) == 2 and len(analyzer.calls) == 4

    # An ordinary retry remains fail-closed and cannot submit either ambiguous request again.
    await create()
    await worker.execute(created.run_id)
    failed = await snapshot(created.run_id)
    unknown_ids = [
        r.response_id
        for r in failed.responses
        if r.error_code == "SPEAKING_ANALYSIS_BILLING_UNKNOWN"
    ]
    assert len(unknown_ids) == 2 and len(analyzer.calls) == 4
    async with factory() as session, session.begin():
        rows = list(
            await session.scalars(
                select(SpeakingNormalizedAudio).where(
                    SpeakingNormalizedAudio.response_id.in_(unknown_ids)
                )
            )
        )
        assert all(row.metadata_json["quality"]["state"] == "AUDIO_OK" for row in rows)
        assert all(row.metadata_json["quality"]["asr_usable"] is None for row in rows)
    selected, unselected = unknown_ids

    await create(**retry_request(failed, [selected]))
    async with factory() as session, session.begin():
        run = await session.get(SpeakingTranscriptRun, created.run_id)
        assert run.responses_json[str(selected)] == {
            "status": "WAITING",
            "allow_interrupted_retry": True,
        }
        assert run.responses_json[str(unselected)] == {"status": "WAITING"}
        assert all(run.responses_json[str(rid)]["status"] == "READY" for rid in ready_ids)
        events = list(
            await session.scalars(
                select(SpeakingTranscriptEvent)
                .where(
                    SpeakingTranscriptEvent.run_id == run.id,
                    SpeakingTranscriptEvent.event_type == "run.queued",
                )
                .order_by(SpeakingTranscriptEvent.sequence)
            )
        )
        assert events[-1].payload == {"retry_interrupted_response_ids": str(selected)}

    await worker.execute(created.run_id)
    recovered = await snapshot(created.run_id)
    assert len(analyzer.calls) == 5
    assert all(
        r.status == "READY" for r in recovered.responses if r.response_id in {*ready_ids, selected}
    )
    assert next(r for r in recovered.responses if r.response_id == unselected).error_code == (
        "SPEAKING_ANALYSIS_BILLING_UNKNOWN"
    )
    async with factory() as session, session.begin():
        row = await session.scalar(
            select(SpeakingNormalizedAudio).where(SpeakingNormalizedAudio.response_id == selected)
        )
        record = next(iter(row.metadata_json["speech_analysis"].values()))
        assert record["status"] == "COMPLETE"
        assert len(record["previous_attempts"]) == 1
        previous = record["previous_attempts"][0]
        assert previous == {
            "status": "ATTEMPTED",
            "attempt_token": previous["attempt_token"],
            "results": [],
            "billing": "UNKNOWN",
            "maximum_possible_calls": 1,
        }
        assert previous["attempt_token"] != record["attempt_token"]

    await create()
    await worker.execute(created.run_id)
    assert len(analyzer.calls) == 5, "Consent is one attempt, never an automatic future replay"


@pytest.mark.parametrize("status", ["COMPLETE", "PARTIAL", "FAILED"])
async def test_explicit_cache_flag_never_resets_a_terminal_checkpoint(db_session, tmp_path, status):
    from app.services.speaking_analysis_cache import cached_speech_analysis
    from app.services.speaking_audio import normalize_committed_take, stage_normalized_audio

    _, rid, media = await completed(db_session, tmp_path)
    settings = configured()

    class Terminal(Analyzer):
        async def analyze(self, audio, **identity):
            result = await super().analyze(audio, **identity)
            return result.model_copy(
                update={
                    "status": status,
                    **({"lexical_transcript": "", "words": []} if status == "FAILED" else {}),
                }
            )

    analyzer = Terminal(settings)
    worker = worker_for(db_session, settings, media.storage, None)
    ref = await normalize_committed_take(
        db_session, rid, settings, storage=media.storage, executor=fake_decode
    )
    async with stage_normalized_audio(media.storage, ref, 600) as audio:
        first = await cached_speech_analysis(worker.sessions, audio, settings, analyzer)
        again = await cached_speech_analysis(
            worker.sessions, audio, settings, analyzer, allow_interrupted_retry=True
        )
    assert first == again and len(analyzer.calls) == 1


async def test_superseded_interrupted_call_cannot_overwrite_new_result_or_history(
    durable_transcript,  # noqa: F811
):
    import asyncio

    from app.services.speaking_analysis_cache import cached_speech_analysis
    from app.services.speaking_audio import normalize_committed_take, stage_normalized_audio

    factory, _, _, ids, storage, _ = durable_transcript
    settings = configured()
    entered, release = asyncio.Event(), asyncio.Event()

    class Deferred(Analyzer):
        async def analyze(self, audio, **identity):
            result = await super().analyze(audio, **identity)
            if len(self.calls) == 1:
                entered.set()
                await release.wait()
                return result.model_copy(update={"lexical_transcript": "old fictional result"})
            return result.model_copy(update={"lexical_transcript": "new fictional result"})

    analyzer = Deferred(settings)
    async with factory() as session:
        ref = await normalize_committed_take(
            session, ids[0], settings, storage=storage, executor=fake_decode
        )
    async with stage_normalized_audio(storage, ref, 600) as audio:
        old = asyncio.create_task(cached_speech_analysis(factory, audio, settings, analyzer))
        try:
            await asyncio.wait_for(entered.wait(), 3)
            current = await cached_speech_analysis(
                factory, audio, settings, analyzer, allow_interrupted_retry=True
            )
            assert current[0].lexical_transcript == "new fictional result"
            release.set()
            with pytest.raises(AppError) as superseded:
                await old
            assert superseded.value.code == "SPEAKING_ANALYSIS_BILLING_UNKNOWN"
        finally:
            release.set()
            await asyncio.gather(old, return_exceptions=True)
        cached = await cached_speech_analysis(factory, audio, settings, analyzer)
        assert cached[0].lexical_transcript == "new fictional result"
    async with factory() as session, session.begin():
        row = await session.scalar(
            select(SpeakingNormalizedAudio).where(SpeakingNormalizedAudio.response_id == ids[0])
        )
        record = next(iter(row.metadata_json["speech_analysis"].values()))
        assert record["status"] == "COMPLETE"
        assert len(record["previous_attempts"]) == 1
        assert record["previous_attempts"][0]["status"] == "ATTEMPTED"
        assert record["previous_attempts"][0]["attempt_token"] != record["attempt_token"]
    assert len(analyzer.calls) == 2


async def test_retry_consent_is_consumed_when_authorized_worker_is_interrupted_again(
    durable_transcript,  # noqa: F811
):
    import asyncio

    from app.services.speaking_transcript_worker import (
        _tasks,
        stop_speaking_transcript_workers,
    )

    factory, actor, aid, _, storage, _ = durable_transcript
    settings = configured()
    entered = asyncio.Event()

    class InterruptedTwice(Analyzer):
        async def analyze(self, audio, **identity):
            result = await super().analyze(audio, **identity)
            if len(self.calls) == 1:
                raise RuntimeError("fictional initial interruption")
            if len(self.calls) == 5:
                entered.set()
                await asyncio.Event().wait()
            return result

    analyzer = InterruptedTwice(settings)
    provider = SimpleNamespace(identity=provider_identity(settings), analyzer=analyzer)
    worker = SpeakingTranscriptWorker(
        factory, settings, provider=provider, storage=storage, executor=fake_decode
    )

    async def create(**kwargs):
        async with factory() as session:
            return await SpeakingTranscriptService(
                session, actor, settings, identity=provider.identity
            ).create(aid, **kwargs)

    async def snapshot(run_id):
        async with factory() as session:
            return await SpeakingTranscriptService(
                session, actor, settings, identity=provider.identity
            ).get(aid, run_id)

    created = await create()
    await worker.execute(created.run_id)
    await create()
    await worker.execute(created.run_id)
    failed = await snapshot(created.run_id)
    unknown = next(
        r.response_id
        for r in failed.responses
        if r.error_code == "SPEAKING_ANALYSIS_BILLING_UNKNOWN"
    )
    assert len(analyzer.calls) == 4
    authorization = retry_request(failed, [unknown])
    await create(**authorization)
    worker.launch(created.run_id)
    try:
        await asyncio.wait_for(entered.wait(), 3)
        await stop_speaking_transcript_workers()
        pending = await snapshot(created.run_id)
        assert pending.status == "PENDING"
        async with factory() as session, session.begin():
            run = await session.get(SpeakingTranscriptRun, created.run_id)
            assert "allow_interrupted_retry" not in run.responses_json[str(unknown)]
        await create()  # Ordinary retry must not restore the consumed authorization.
        await worker.recover()
        task = _tasks.get(created.run_id)
        if task:
            await asyncio.wait_for(task, 3)
        final = await snapshot(created.run_id)
        assert next(r for r in final.responses if r.response_id == unknown).error_code == (
            "SPEAKING_ANALYSIS_BILLING_UNKNOWN"
        )
        assert len(analyzer.calls) == 5, "Startup recovery cannot submit a third ambiguous call"
        with pytest.raises(AppError) as stale:
            await create(**authorization)
        assert stale.value.code == "SPEAKING_INTERRUPTED_RETRY_NOT_AVAILABLE"
        assert len(analyzer.calls) == 5, "The same old consent cannot authorize another call"
        async with factory() as session, session.begin():
            row = await session.scalar(
                select(SpeakingNormalizedAudio).where(
                    SpeakingNormalizedAudio.response_id == unknown
                )
            )
            record = next(iter(row.metadata_json["speech_analysis"].values()))
            assert record["status"] == "ATTEMPTED" and len(record["previous_attempts"]) == 1
        await create(**retry_request(final, [unknown]))
        await worker.execute(created.run_id)
        assert len(analyzer.calls) == 6, "Fresh consent authorizes exactly the next attempt"
        async with factory() as session, session.begin():
            row = await session.scalar(
                select(SpeakingNormalizedAudio).where(
                    SpeakingNormalizedAudio.response_id == unknown
                )
            )
            record = next(iter(row.metadata_json["speech_analysis"].values()))
            assert record["status"] == "COMPLETE" and len(record["previous_attempts"]) == 2
    finally:
        await stop_speaking_transcript_workers()
