"""Durable grading contracts on PostgreSQL, using fake speech/LLM boundaries."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from test_speaking_transcript import (  # noqa: F401
    FakeASR,
    completed,
    concurrent_speaking,
    durable_transcript,
)

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models.speaking_ai import SpeakingAIGradingEvent, SpeakingAIGradingRun
from app.services.speaking_ai import SpeakingAIService
from app.services.speaking_ai_worker import SpeakingAIWorker

IDENTITY = {"provider": "fake", "model": "fixture", "version": "v1"}


class FakeLLM:
    def __init__(self, *, fail_feedback=False):
        self.calls = []
        self.fail_feedback = fail_feedback

    async def ensure_ready(self):
        pass

    async def complete(self, messages, schema, *, options=None):
        import json

        from app.providers.speaking_llm.base import Completion

        self.calls.append((messages, schema, options))
        if "score" in schema["properties"]:
            return Completion(text=json.dumps({"score": 6.5}))
        if self.fail_feedback:
            raise RuntimeError("PRIVATE_FEEDBACK_BODY /private/path")
        return Completion(
            text=json.dumps(
                {
                    "feedback": "Fictional concise feedback",
                    "strengths": ["Clear contribution"],
                    "improvements": ["Extend ideas"],
                }
            )
        )


def grading_worker(session, settings, storage, provider):
    from test_speaking_transcript import worker_for

    from app.services.speaking_scorer import SpeakingScorer

    transcript = worker_for(session, settings, storage, FakeASR())
    return SpeakingAIWorker(
        transcript.sessions,
        settings,
        scorer=SpeakingScorer(provider),
        llm_identity=IDENTITY,
        transcript_identity=FakeASR.identity,
        transcript_worker=transcript,
    )


async def test_worker_reuses_transcript_and_feedback_failure_preserves_all_scores(
    db_session, tmp_path, caplog
):
    from test_speaking_transcript import worker_for

    from app.services.speaking_transcript import SpeakingTranscriptService

    aid, _, media = await completed(db_session, tmp_path)
    configured = Settings(storage_root=tmp_path)
    transcript_service = SpeakingTranscriptService(
        db_session, db_session.info["current_user_identity"], configured, identity=FakeASR.identity
    )
    transcript_run = await transcript_service.create(aid)
    speech = FakeASR()
    await worker_for(db_session, configured, media.storage, speech).execute(transcript_run.run_id)
    api = service(db_session, configured)
    created = await api.create(aid)
    provider = FakeLLM(fail_feedback=True)
    worker = grading_worker(db_session, configured, media.storage, provider)
    await worker.execute(created.run_id)
    snapshot = await api.get(aid, created.run_id)
    assert snapshot.status == "COMPLETED" and snapshot.overall_band == snapshot.raw_mean == 6.5
    assert all(
        c.score == 6.5 and c.feedback_status == "FALLBACK" for c in snapshot.criteria.values()
    )
    assert len(provider.calls) == 8 and worker.transcript_worker.provider.calls == []
    assert "PRIVATE" not in snapshot.model_dump_json() + caplog.text
    assert (await api.create(aid)).cache_hit


async def test_grading_waits_for_matching_active_transcript_without_duplicate_job(
    db_session, tmp_path, monkeypatch
):
    import asyncio

    from app.services.speaking_transcript import SpeakingTranscriptService
    from app.services.speaking_transcript_worker import _tasks, stop_speaking_transcript_workers

    aid, _, media = await completed(db_session, tmp_path)
    configured = Settings(storage_root=tmp_path)
    entered, joined, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Waiting(FakeASR):
        async def transcribe(self, audio):
            entered.set()
            await release.wait()
            return await super().transcribe(audio)

    worker = grading_worker(db_session, configured, media.storage, FakeLLM())
    worker.transcript_worker.provider = Waiting()
    transcript = await worker.transcript_service(
        db_session,
        db_session.info["current_user_identity"],
    ).create(aid)
    created = await service(db_session, configured).create(aid)
    original = SpeakingTranscriptService.create

    async def observe_create(instance, attempt_id):
        result = await original(instance, attempt_id)
        if result.existing_active:
            assert result.run_id == transcript.run_id
            joined.set()
        return result

    monkeypatch.setattr(SpeakingTranscriptService, "create", observe_create)
    worker.transcript_worker.launch(transcript.run_id)
    task = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        previous = _tasks[transcript.run_id]
        task = asyncio.create_task(worker.execute(created.run_id))
        await asyncio.wait_for(joined.wait(), 5)
        assert _tasks[transcript.run_id] is previous
        release.set()
        await asyncio.wait_for(task, 5)
        assert len(worker.transcript_worker.provider.calls) == 1
        assert (
            await service(db_session, configured).get(aid, created.run_id)
        ).status == "COMPLETED"
    finally:
        release.set()
        if task:
            await asyncio.gather(task, return_exceptions=True)
        await stop_speaking_transcript_workers()


async def test_worker_generates_missing_transcript_without_duplicate_asr(db_session, tmp_path):
    aid, _, media = await completed(db_session, tmp_path)
    configured = Settings(storage_root=tmp_path)
    api = service(db_session, configured)
    created = await api.create(aid)
    worker = grading_worker(db_session, configured, media.storage, FakeLLM())
    await worker.execute(created.run_id)
    assert (await api.get(aid, created.run_id)).status == "COMPLETED"
    assert len(worker.transcript_worker.provider.calls) == 1


def service(session, settings, actor=None):
    return SpeakingAIService(
        session,
        actor or session.info["current_user_identity"],
        settings,
        llm_identity=IDENTITY,
        transcript_identity=FakeASR.identity,
    )


async def test_create_active_dedup_and_fresh_persisted_contract(db_session, tmp_path):
    aid, _, _ = await completed(db_session, tmp_path)
    configured = Settings(storage_root=tmp_path)
    api = service(db_session, configured)
    first = await api.create(aid)
    second = await api.create(aid)
    assert first.run_id == second.run_id and second.existing_active
    snapshot = await api.get(aid, first.run_id)
    assert snapshot.status == "PENDING" and snapshot.advisory and snapshot.overall_band is None
    async with db_session.begin():
        run = await db_session.get(SpeakingAIGradingRun, first.run_id)
        assert run.attempt_id == aid and run.requested_by_user_id == api.actor.id
        assert run.identity_json["llm"] == IDENTITY and run.created_at and run.heartbeat_at
        events = list(
            await db_session.scalars(
                select(SpeakingAIGradingEvent).where(SpeakingAIGradingEvent.run_id == run.id)
            )
        )
        assert len(events) == 1 and events[0].sequence == 1 and events[0].event_type == "run.queued"


async def test_cancel_is_durable_idempotent_and_completed_result_wins(db_session, tmp_path):
    aid, _, _ = await completed(db_session, tmp_path)
    api = service(db_session, Settings(storage_root=tmp_path))
    created = await api.create(aid)
    assert (await api.cancel(aid, created.run_id)).status == "CANCELLED"
    assert (await api.cancel(aid, created.run_id)).status == "CANCELLED"
    async with db_session.begin():
        events = list(
            await db_session.scalars(
                select(SpeakingAIGradingEvent).where(
                    SpeakingAIGradingEvent.run_id == created.run_id
                )
            )
        )
        assert [e.event_type for e in events] == ["run.queued", "run.cancelled"]
    retry = await api.create(aid)
    assert retry.run_id == created.run_id and not retry.existing_active
    async with db_session.begin():
        run = await db_session.get(SpeakingAIGradingRun, created.run_id)
        run.status = run.stage = "COMPLETED"
        run.raw_mean = run.overall_band = 6.5
    assert (await api.cancel(aid, created.run_id)).status == "COMPLETED"
    assert (await api.create(aid)).cache_hit


async def test_unrelated_users_and_run_ids_do_not_grant_access(db_session, tmp_path):
    from teacher_helpers import make_user

    aid, _, _ = await completed(db_session, tmp_path)
    configured = Settings(storage_root=tmp_path)
    owner = service(db_session, configured)
    created = await owner.create(aid)
    for role in ("USER", "TEACHER"):
        outsider = await make_user(db_session, role)
        api = service(db_session, configured, outsider)
        for action in (
            lambda api=api: api.get(aid, created.run_id),
            lambda api=api: api.create(aid),
            lambda api=api: api.cancel(aid, created.run_id),
        ):
            with pytest.raises(AppError) as caught:
                await action()
            assert caught.value.status_code in {403, 404}
    with pytest.raises(AppError):
        await owner.get(aid, uuid4())
    with pytest.raises(AppError):
        await owner.get(uuid4(), created.run_id)


async def test_true_concurrent_create_and_worker_claim_one_job(durable_transcript):  # noqa: F811
    import asyncio

    from test_speaking_transcript import fake_decode

    from app.services.speaking_scorer import SpeakingScorer
    from app.services.speaking_transcript_worker import SpeakingTranscriptWorker

    factory, actor, aid, _, storage, configured = durable_transcript

    async def create():
        async with factory() as session:
            return await service(session, configured, actor).create(aid)

    first, second = await asyncio.gather(create(), create())
    assert first.run_id == second.run_id and sum(r.existing_active for r in (first, second)) == 1
    provider, speech = FakeLLM(), FakeASR()
    transcript = SpeakingTranscriptWorker(
        factory, configured, provider=speech, storage=storage, executor=fake_decode
    )
    workers = [
        SpeakingAIWorker(
            factory,
            configured,
            scorer=SpeakingScorer(provider),
            llm_identity=IDENTITY,
            transcript_identity=FakeASR.identity,
            transcript_worker=transcript,
        )
        for _ in range(2)
    ]
    await asyncio.gather(*(w.execute(first.run_id) for w in workers))
    assert len(provider.calls) == 8 and len(speech.calls) == 4
    async with factory() as fresh:
        api = service(fresh, configured, actor)
        run, events = await api.snapshot(aid, first.run_id)
        assert run.status == "COMPLETED" and run.overall_band == 6.5
        assert [e.sequence for e in events] == list(range(1, len(events) + 1))
        assert all(set(e.payload) <= {"status", "stage", "criterion", "error_code"} for e in events)
        assert "THIS_SECRET_NOTE_MUST_NOT_ENTER_SPEECH_ANALYSIS_98765" not in run.model_dump_json()
        assert (
            "storage_key" not in run.model_dump_json()
            and str(storage.root) not in run.model_dump_json()
        )
        assert (await api.create(aid)).cache_hit


async def test_score_checkpoint_visible_before_feedback_and_shutdown_resumes_only_feedback(
    durable_transcript,  # noqa: F811
):  # noqa: F811
    import asyncio

    from test_speaking_transcript import fake_decode

    from app.services.speaking_ai_worker import _tasks, stop_speaking_ai_workers
    from app.services.speaking_scorer import SpeakingScorer
    from app.services.speaking_transcript_worker import SpeakingTranscriptWorker

    factory, actor, aid, _, storage, configured = durable_transcript
    entered = asyncio.Event()

    class Blocked(FakeLLM):
        async def complete(self, messages, schema, *, options=None):
            if "score" not in schema["properties"]:
                entered.set()
                await asyncio.Event().wait()
            return await super().complete(messages, schema, options=options)

    async with factory() as session:
        created = await service(session, configured, actor).create(aid)
    transcript = SpeakingTranscriptWorker(
        factory, configured, provider=FakeASR(), storage=storage, executor=fake_decode
    )
    provider = Blocked()
    worker = SpeakingAIWorker(
        factory,
        configured,
        scorer=SpeakingScorer(provider),
        llm_identity=IDENTITY,
        transcript_identity=FakeASR.identity,
        transcript_worker=transcript,
    )
    worker.launch(created.run_id)
    try:
        await asyncio.wait_for(entered.wait(), 20)
        async with factory() as fresh:
            score = (await service(fresh, configured, actor).get(aid, created.run_id)).criteria[
                "fc"
            ]
            assert (
                score.score == 6.5
                and score.status == "SCORED"
                and score.feedback_status == "PENDING"
            )
        await stop_speaking_ai_workers()
        assert not _tasks
        async with factory() as fresh:
            assert (
                await service(fresh, configured, actor).get(aid, created.run_id)
            ).status == "PENDING"
        provider = FakeLLM(fail_feedback=True)
        worker.scorer = SpeakingScorer(provider)
        await worker.execute(created.run_id)
        assert sum("score" in schema["properties"] for _, schema, _ in provider.calls) == 3
        async with factory() as fresh:
            result = await service(fresh, configured, actor).get(aid, created.run_id)
            assert result.status == "COMPLETED" and result.criteria["fc"].score == 6.5
            assert result.criteria["fc"].feedback_status == "FALLBACK"
    finally:
        await stop_speaking_ai_workers()


@pytest.mark.parametrize(
    "change",
    ["audio", "take", "normalizer", "asr", "quality", "features", "rubric", "prompt", "llm"],
)
async def test_each_material_cache_identity_invalidates(db_session, tmp_path, change):
    from app.models.speaking import SpeakingResponse

    aid, rid, _ = await completed(db_session, tmp_path)
    configured = Settings(storage_root=tmp_path)
    old = service(db_session, configured)
    created = await old.create(aid)
    if change in {"audio", "take"}:
        async with db_session.begin():
            row = await db_session.get(SpeakingResponse, rid)
            row.committed_audio_fingerprint = "b" * 64
            if change == "take":
                row.active_take_number += 1
        assert (await old.get(aid, created.run_id)).error_code == "SPEAKING_AI_SOURCE_CHANGED"
    elif change == "normalizer":
        configured.speaking_normalizer_version = "pcm-next"
    elif change == "quality":
        configured.speaking_quality.version = "quality-next"
    elif change == "features":
        configured.speaking_pronunciation.version = "prosody-next"
    elif change == "rubric":
        configured.speaking_ai_rubric_version = "speaking-rubric-next"
    elif change == "prompt":
        configured.speaking_ai_prompt_version = "speaking-score-next"
    changed = SpeakingAIService(
        db_session,
        db_session.info["current_user_identity"],
        configured,
        llm_identity={**IDENTITY, "version": "v2"} if change == "llm" else IDENTITY,
        transcript_identity={**FakeASR.identity, "version": "v2"}
        if change == "asr"
        else FakeASR.identity,
    )
    assert await changed.latest(aid) is None
    assert (await changed.create(aid)).run_id != created.run_id


async def test_assignment_teacher_read_only_survives_archive(db_session, tmp_path):
    from teacher_helpers import make_user

    from app.models import Attempt, Classroom, ClassroomAssignment

    teacher, other = await make_user(db_session, "TEACHER"), await make_user(db_session, "TEACHER")
    aid, _, _ = await completed(db_session, tmp_path)
    configured = Settings(storage_root=tmp_path)
    owner = service(db_session, configured)
    created = await owner.create(aid)
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        room = Classroom(teacher_id=teacher.id, name="Fictional retained class")
        db_session.add_all([room, Classroom(teacher_id=other.id, name="Unrelated owned class")])
        await db_session.flush()
        assignment = ClassroomAssignment(
            classroom_id=room.id,
            test_version_id=attempt.test_version_id,
            created_by_user_id=teacher.id,
        )
        db_session.add(assignment)
        await db_session.flush()
        attempt.classroom_assignment_id = assignment.id
    read_only = service(db_session, configured, teacher)
    assert (await read_only.get(aid, created.run_id)).advisory
    for action in (lambda: read_only.create(aid), lambda: read_only.cancel(aid, created.run_id)):
        with pytest.raises(AppError):
            await action()
    with pytest.raises(AppError):
        await service(db_session, configured, other).get(aid, created.run_id)
    async with db_session.begin():
        room.archived_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
    assert (await read_only.get(aid, created.run_id)).advisory
    async with db_session.begin():
        attempt.classroom_assignment_id = None
    with pytest.raises(AppError):
        await read_only.get(aid, created.run_id)


async def test_unassessable_audio_never_calls_llm_or_creates_low_band(db_session, tmp_path):
    import wave

    aid, _, media = await completed(db_session, tmp_path)
    configured = Settings(storage_root=tmp_path)
    api = service(db_session, configured)
    created = await api.create(aid)
    provider = FakeLLM()
    worker = grading_worker(db_session, configured, media.storage, provider)

    def silent_decode(args, timeout):
        with wave.open(str(args[-1]), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\0\0" * 16000)

    worker.transcript_worker.executor = silent_decode
    await worker.execute(created.run_id)
    result = await api.get(aid, created.run_id)
    assert result.status == "FAILED" and result.error_code == "SPEAKING_AUDIO_UNASSESSABLE"
    assert result.overall_band is None and all(
        c.score is None and c.status == "UNAVAILABLE" for c in result.criteria.values()
    )
    assert not provider.calls


@pytest.mark.parametrize("winner", ["completion", "cancel"])
async def test_completion_cancel_race_has_one_durable_terminal_state(
    durable_transcript,  # noqa: F811
    winner,
    monkeypatch,  # noqa: F811
):
    import asyncio

    from app.repositories.speaking_ai import SpeakingAIRepository
    from app.services.speaking_ai_worker import GradingStopped

    factory, actor, aid, _, _, configured = durable_transcript
    async with factory() as session:
        created = await service(session, configured, actor).create(aid)
    async with factory() as session, session.begin():
        run = await session.get(SpeakingAIGradingRun, created.run_id)
        run.status, run.lease_token = "RUNNING", "race-owner"
        run.criteria_json = {trait: {"score": 6.5} for trait in ("fc", "lr", "gra", "pr")}
    entered, release = asyncio.Event(), asyncio.Event()
    original = SpeakingAIRepository.append

    async def pause_before_commit(repository, run, event_type, payload=None):
        event = await original(repository, run, event_type, payload)
        if event_type == ("run.completed" if winner == "completion" else "run.cancelled"):
            entered.set()
            await release.wait()
        return event

    monkeypatch.setattr(SpeakingAIRepository, "append", pause_before_commit)
    worker = SpeakingAIWorker(
        factory, configured, llm_identity=IDENTITY, transcript_identity=FakeASR.identity
    )

    async def cancel():
        async with factory() as session:
            return await service(session, configured, actor).cancel(aid, created.run_id)

    async def finish():
        await worker._finish(created.run_id, "race-owner")

    first = asyncio.create_task(finish() if winner == "completion" else cancel())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        second = asyncio.create_task(cancel() if winner == "completion" else finish())
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True), 5)
        if winner == "cancel":
            assert isinstance(results[1], GradingStopped)
        else:
            assert results[1].status == "COMPLETED"
        async with factory() as session:
            snapshot, events = await service(session, configured, actor).snapshot(
                aid, created.run_id
            )
            assert snapshot.status == ("COMPLETED" if winner == "completion" else "CANCELLED")
            assert sum(e.event_type in {"run.completed", "run.cancelled"} for e in events) == 1
            assert all(c.score == 6.5 for c in snapshot.criteria.values())
    finally:
        release.set()
        await asyncio.gather(first, return_exceptions=True)


async def test_stale_restart_fences_old_lease_and_event_sequence_is_unique(
    db_session, tmp_path, monkeypatch
):
    from datetime import timedelta

    from sqlalchemy.exc import IntegrityError

    from app.domains.timers import TimerService
    from app.services.speaking_ai_worker import GradingStopped

    aid, _, media = await completed(db_session, tmp_path)
    configured = Settings(storage_root=tmp_path)
    api = service(db_session, configured)
    created = await api.create(aid)
    async with db_session.begin():
        run = await db_session.get(SpeakingAIGradingRun, created.run_id)
        run.status, run.lease_token = "RUNNING", "stale-owner"
        run.heartbeat_at = TimerService.now() - timedelta(seconds=301)
        run.criteria_json = {"fc": {"score": 6.5, "status": "SCORE_READY"}}
    worker = grading_worker(db_session, configured, media.storage, FakeLLM())
    recovered = []
    monkeypatch.setattr(worker, "launch", recovered.append)
    await worker.recover()
    assert recovered == [created.run_id]
    async with db_session.begin():
        run = await db_session.get(SpeakingAIGradingRun, created.run_id)
        assert run.status == "PENDING" and run.lease_token is None
        assert run.criteria_json["fc"]["score"] == 6.5
    with pytest.raises(GradingStopped):
        await worker._finish(created.run_id, "stale-owner")
    async with db_session.begin():
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(
                    SpeakingAIGradingEvent(
                        run_id=created.run_id, sequence=1, event_type="run.queued", payload={}
                    )
                )
                await db_session.flush()
    assert (await api.get(aid, created.run_id)).status == "PENDING"


async def test_disabled_grader_fails_safely_without_creating_run(db_session, tmp_path):
    aid, _, _ = await completed(db_session, tmp_path)
    api = SpeakingAIService(
        db_session, db_session.info["current_user_identity"], Settings(storage_root=tmp_path)
    )
    with pytest.raises(AppError) as caught:
        await api.create(aid)
    assert caught.value.code == "SPEAKING_AI_NOT_CONFIGURED" and caught.value.status_code == 503
    async with db_session.begin():
        assert (
            await db_session.scalar(
                select(SpeakingAIGradingRun.id).where(SpeakingAIGradingRun.attempt_id == aid)
            )
            is None
        )


async def test_configured_modal_transport_post_creates_durable_run_without_llm_call(
    db_session, tmp_path, monkeypatch
):
    from teacher_helpers import api_client

    from app.api.v1.speaking_ai import get_speaking_ai_worker
    from app.main import app

    aid, _, _ = await completed(db_session, tmp_path)
    settings = Settings(
        storage_root=tmp_path,
        speaking_ai_enabled=True,
        ai_writing_enabled=True,
        ai_writing_provider="vllm",
        ai_writing_vllm_base_url="https://fictional.modal.run/v1",
        ai_writing_modal_key="fixture-key",
        ai_writing_modal_secret="fixture-secret",
    )
    worker = SpeakingAIWorker(
        None, settings, llm_identity=IDENTITY, transcript_identity=FakeASR.identity
    )
    launched = []
    monkeypatch.setattr(worker, "launch", lambda run_id, **_: launched.append(run_id))
    app.dependency_overrides[get_speaking_ai_worker] = lambda: worker
    try:
        async with api_client(db_session, db_session.info["current_user_identity"]) as client:
            result = await client.post(f"/api/v1/speaking-attempts/{aid}/ai-runs")
        assert result.status_code == 200, result.json()
        run_id = UUID(result.json()["run_id"])
        assert launched == [run_id]
        async with db_session.begin():
            saved = await db_session.get(SpeakingAIGradingRun, run_id)
            assert saved is not None and saved.attempt_id == aid and saved.status == "PENDING"
    finally:
        app.dependency_overrides.pop(get_speaking_ai_worker, None)


async def test_cancel_then_immediate_retry_hands_off_after_old_task_cleanup(db_session, tmp_path):
    import asyncio

    from app.services.speaking_ai_worker import (
        _tasks,
        cancel_speaking_ai_worker,
        stop_speaking_ai_workers,
    )

    aid, _, media = await completed(db_session, tmp_path)
    configured = Settings(storage_root=tmp_path)
    api = service(db_session, configured)
    created = await api.create(aid)
    entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Cleanup(FakeLLM):
        blocked = True

        async def complete(self, messages, schema, *, options=None):
            if "score" not in schema["properties"] and self.blocked:
                entered.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.blocked = False
                    cleaning.set()
                    await release.wait()
                    raise
            return await super().complete(messages, schema, options=options)

    provider = Cleanup()
    worker = grading_worker(db_session, configured, media.storage, provider)
    worker.launch(created.run_id)
    try:
        await asyncio.wait_for(entered.wait(), 10)
        await api.cancel(aid, created.run_id)
        cancel_speaking_ai_worker(created.run_id)
        await asyncio.wait_for(cleaning.wait(), 5)
        previous = _tasks[created.run_id]
        retried = await api.create(aid)
        worker.launch(retried.run_id, restart=not retried.existing_active)
        assert _tasks[created.run_id] is not previous
        successor = _tasks[created.run_id]
        release.set()
        await asyncio.wait_for(successor, 10)
        assert (await api.get(aid, created.run_id)).status == "COMPLETED"
        assert sum("score" in schema["properties"] for _, schema, _ in provider.calls) == 4
    finally:
        release.set()
        await stop_speaking_ai_workers()


async def test_real_http_sse_replay_disconnect_and_explicit_cancel(durable_transcript, monkeypatch):  # noqa: F811
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from teacher_helpers import api_client
    from test_speaking_transcript import fake_decode

    import app.providers.speaking_llm as llm_module
    import app.services.speaking_transcript as transcript_module
    from app.api.v1.speaking_ai import event_stream, get_speaking_ai_worker
    from app.main import app
    from app.services.speaking_ai_worker import _tasks, stop_speaking_ai_workers
    from app.services.speaking_scorer import SpeakingScorer
    from app.services.speaking_transcript_worker import SpeakingTranscriptWorker

    factory, actor, aid, _, storage, configured = durable_transcript
    monkeypatch.setattr(llm_module, "config_identity", lambda _: IDENTITY)
    monkeypatch.setattr(transcript_module, "provider_identity", lambda _: FakeASR.identity)
    entered, release = asyncio.Event(), asyncio.Event()

    class Blocked(FakeLLM):
        async def complete(self, messages, schema, *, options=None):
            if "score" not in schema["properties"]:
                entered.set()
                await release.wait()
            return await super().complete(messages, schema, options=options)

    transcript = SpeakingTranscriptWorker(
        factory, configured, provider=FakeASR(), storage=storage, executor=fake_decode
    )
    worker = SpeakingAIWorker(
        factory,
        configured,
        scorer=SpeakingScorer(Blocked()),
        llm_identity=IDENTITY,
        transcript_identity=FakeASR.identity,
        transcript_worker=transcript,
    )
    app.dependency_overrides[get_speaking_ai_worker] = lambda: worker
    path = f"/api/v1/speaking-attempts/{aid}/ai-runs"
    try:
        async with factory() as session, api_client(session, actor) as client:
            posted = await asyncio.wait_for(client.post(path), 3)
            assert posted.status_code == 200
            run_id = UUID(posted.json()["run_id"])
            await asyncio.wait_for(entered.wait(), 20)
            snapshot = (await client.get(f"{path}/{run_id}")).json()
            assert snapshot["criteria"]["fc"]["score"] == 6.5
            assert (await client.post(path)).json()["existing_active"]
            observer = event_stream(
                SimpleNamespace(is_disconnected=AsyncMock(return_value=True)),
                aid,
                run_id,
                actor,
                worker,
                0,
            )
            assert [e async for e in observer] == [] and run_id in _tasks
            stopped_task = _tasks[run_id]
            stopped = await client.post(f"{path}/{run_id}/cancel")
            assert (
                stopped.json()["status"] == "CANCELLED"
                and stopped.json()["criteria"]["fc"]["score"] == 6.5
            )
            await asyncio.wait_for(asyncio.gather(stopped_task, return_exceptions=True), 5)
            last = stopped.json()["last_sequence"]
            replay = await asyncio.wait_for(
                client.get(f"{path}/{run_id}/events?after=1", headers={"Last-Event-ID": "2"}), 3
            )
            sequences = [
                int(line[4:]) for line in replay.text.splitlines() if line.startswith("id: ")
            ]
            assert sequences == list(range(3, last + 1))
            assert (
                replay.headers["cache-control"] == "no-cache, no-store"
                and replay.headers["x-accel-buffering"] == "no"
            )
            assert (
                "He go" not in replay.text
                and "PRIVATE" not in replay.text
                and "storage_key" not in stopped.text
            )
            assert (
                await client.get(
                    f"{path}/{run_id}/events", headers={"Last-Event-ID": "999999999999999999999"}
                )
            ).status_code == 422
            assert (await client.get(f"{path}/{uuid4()}")).status_code == 404
    finally:
        release.set()
        await stop_speaking_ai_workers()
        app.dependency_overrides.pop(get_speaking_ai_worker, None)
