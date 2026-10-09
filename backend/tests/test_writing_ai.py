import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.dependencies import get_current_user
from app.api.v1 import writing_ai as routes
from app.core.config import Settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.domains.scoring.mts_prompts import TRAIT_NAMES
from app.domains.scoring.writing import WritingScoringProvider, WritingScoringRequest
from app.main import app
from app.models import (
    Attempt,
    AttemptWritingResponse,
    AttemptWritingScore,
    WritingAIGradingEvent,
    WritingAIGradingRun,
    WritingTask,
)
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AttemptStatus, ModuleType, TimerMode, VersionStatus, WritingAIRunStatus
from app.providers.writing_llm import create_provider, is_configured
from app.providers.writing_llm.base import Completion, ProviderFailure
from app.schemas.writing_ai import TRAITS, CriterionResult, EventPayload, TraitScore
from app.services.mts_writing import MTSWritingScoringService
from app.services.writing_ai import CANCELLATION_CODE, WritingAIService, input_fingerprint
from app.services.writing_ai_worker import RunStopped, WritingAIWorker

ESSAY = "Fictional parks improve city life. However, funding should be transparent."


@pytest.mark.integration
@pytest.mark.parametrize("status", [WritingAIRunStatus.PENDING, WritingAIRunStatus.RUNNING])
async def test_owner_cancels_active_run_with_durable_idempotent_event(
    db_session, writing, settings, status
):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    async with db_session.begin():
        row = await db_session.get(WritingAIGradingRun, created.run_id)
        row.status = status
    cancelled = await api.cancel(created.run_id)
    assert cancelled.status == WritingAIRunStatus.FAILED
    assert cancelled.error_code == CANCELLATION_CODE
    assert cancelled.error_message == "Bạn đã dừng bài chấm AI."
    assert cancelled.completed_at is not None and cancelled.result is None
    again = await api.cancel(created.run_id)
    assert again == cancelled
    refreshed, events = await api.snapshot(created.run_id, 0)
    assert refreshed == cancelled
    assert [(event.sequence, event.event_type) for event in events] == [(1, "run.failed")]
    assert events[0].payload.error_code == CANCELLATION_CODE
    async with db_session.begin():
        row = await db_session.get(WritingAIGradingRun, created.run_id)
        assert row.updated_at == row.completed_at
    # Even without force, FAILED rows never qualify as completed cache entries.
    regrade = await api.create(attempt_id, task_id, force=False)
    assert regrade.run_id != created.run_id and not regrade.cache_hit


@pytest.mark.integration
@pytest.mark.parametrize("foreign", [False, True])
async def test_cancel_missing_or_foreign_run_is_not_found(db_session, writing, settings, foreign):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    with pytest.raises(AppError) as failure:
        await service(db_session, settings, uuid4() if foreign else None).cancel(
            created.run_id if foreign else uuid4()
        )
    assert failure.value.code == "AI_RUN_NOT_FOUND" and failure.value.status_code == 404
    assert (await api.get(created.run_id)).status == WritingAIRunStatus.PENDING


@pytest.mark.integration
@pytest.mark.parametrize("completed", [False, True])
async def test_cancel_does_not_rewrite_terminal_run(db_session, writing, settings, completed):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    runner = worker(db_session, settings)
    if completed:
        await runner.execute(created.run_id)
    else:
        await runner._fail(created.run_id, "AI_PROVIDER_TIMEOUT", "Provider timeout", None)
    before, events_before = await api.snapshot(created.run_id, 0)
    assert await api.cancel(created.run_id) == before
    _, events_after = await api.snapshot(created.run_id, 0)
    assert events_after == events_before


@pytest.mark.integration
async def test_cancelled_pending_worker_never_calls_provider(db_session, writing, settings):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    await api.cancel(created.run_id)
    provider = FakeProvider()
    await worker(db_session, settings, provider).execute(created.run_id)
    assert provider.calls == []
    assert (await api.get(created.run_id)).error_code == CANCELLATION_CODE


@pytest.mark.integration
async def test_cancel_preserves_partial_and_official_scores_blocks_late_worker_updates(
    db_session, writing, settings
):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    runner = worker(db_session, settings)
    result = CriterionResult(
        score=6, feedback="Fictional feedback", strengths=[], improvements=[], evidence=[]
    )
    for trait in ("ta", "cc"):
        await runner._checkpoint(
            created.run_id, "criterion.completed", EventPayload(criterion=trait, result=result)
        )
    await runner._checkpoint(created.run_id, "criterion.started", EventPayload(criterion="lr"))
    before = await api.get(created.run_id)
    stopped = await api.cancel(created.run_id)
    assert stopped.progress == before.progress and set(stopped.progress) == {"ta", "cc"}
    assert stopped.failures == {} and stopped.result is None
    with pytest.raises(RunStopped):
        await runner._checkpoint(
            created.run_id, "criterion.completed", EventPayload(criterion="lr", result=result)
        )
    # Must return before accessing the proposed result: cancellation acquired its lock first.
    await runner._complete(created.run_id, Mock(), Mock())
    await runner._fail(created.run_id, "RUN_INTERRUPTED", "Interrupted", None)
    saved, events = await api.snapshot(created.run_id, 0)
    assert saved == stopped
    assert events[-1].event_type == "run.failed"
    assert not any(event.event_type == "criterion.failed" for event in events)
    async with db_session.begin():
        db_session.expire_all()
        row = await db_session.get(WritingAIGradingRun, created.run_id)
        assert row.raw_mean is None and row.overall_band is None
        attempt = await db_session.get(Attempt, attempt_id)
        assert attempt.band_score == Decimal("7.0")
        essay = await db_session.scalar(
            select(AttemptWritingResponse).where(AttemptWritingResponse.attempt_id == attempt_id)
        )
        assert essay.content == ESSAY
        score = await db_session.scalar(
            select(AttemptWritingScore).where(AttemptWritingScore.attempt_id == attempt_id)
        )
        assert (score.ta, score.cc, score.lr, score.gra, score.ta_feedback) == (
            7,
            7,
            7,
            7,
            "Human feedback stays.",
        )


@pytest.mark.integration
@pytest.mark.parametrize("local_stop", [False, True])
async def test_user_cancel_stops_provider_work_and_survives_asyncio_cleanup(
    db_session, writing, settings, local_stop
):
    class WaitingProvider(FakeProvider):
        def __init__(self):
            super().__init__()
            self.waiting = asyncio.Event()
            self.release = asyncio.Event()
            self.interrupted = asyncio.Event()

        async def ensure_ready(self):
            self.waiting.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.interrupted.set()
                raise

    from app.services.writing_ai_worker import _tasks

    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    provider = WaitingProvider()
    runner = worker(db_session, settings, provider)
    runner.launch(created.run_id)
    job = _tasks[created.run_id]
    try:
        await asyncio.wait_for(provider.waiting.wait(), timeout=5)
        assert (await api.get(created.run_id)).status == WritingAIRunStatus.RUNNING
        await api.cancel(created.run_id)
        if local_stop:
            # A separately instantiated API worker still finds the process-wide registry.
            worker(db_session, settings).cancel(created.run_id)
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(job, timeout=5)
            assert provider.interrupted.is_set()
        else:
            # Simulates another process: the next durable checkpoint stops provider work.
            provider.release.set()
            await asyncio.wait_for(job, timeout=5)
        assert provider.calls == []
        saved = await api.get(created.run_id)
        assert saved.error_code == CANCELLATION_CODE and saved.result is None
        await asyncio.sleep(0)
        assert created.run_id not in _tasks
    finally:
        if not job.done():
            job.cancel()
            await asyncio.gather(job, return_exceptions=True)


@pytest.mark.integration
async def test_cancel_endpoint_authorization_commit_then_stop_and_sse_replay(
    db_session, writing, settings, monkeypatch
):
    attempt_id, _, task_id = writing
    created = await service(db_session, settings).create(attempt_id, task_id, force=False)
    runner = worker(db_session, settings)
    stops = []

    def stop_after_commit(run_id):
        assert not db_session.in_transaction()
        stops.append(run_id)

    monkeypatch.setattr(runner, "cancel", stop_after_commit)
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    app.dependency_overrides[routes.get_worker] = lambda: runner
    app.dependency_overrides[get_current_user] = lambda: db_session.info["current_user_identity"]

    async def session_override():
        yield db_session

    app.dependency_overrides[get_session] = session_override
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            url = f"/api/v1/ai-writing-grading-runs/{created.run_id}"
            response = await client.post(url + "/cancel")
            assert (
                response.status_code == 200 and response.json()["error_code"] == CANCELLATION_CODE
            )
            assert stops == [created.run_id]
            assert (await client.post(url + "/cancel")).json() == response.json()
            stream = await client.get(url + "/events")
            assert "event: run.failed" in stream.text and CANCELLATION_CODE in stream.text
            assert (await client.get(url + "/events", headers={"Last-Event-ID": "1"})).text == ""
            assert (await client.get(url)).json() == response.json()
            assert (
                await client.post(f"/api/v1/ai-writing-grading-runs/{uuid4()}/cancel")
            ).status_code == 404
            app.dependency_overrides[get_current_user] = lambda: Mock(id=uuid4())
            assert (await client.post(url + "/cancel")).status_code == 404
            app.dependency_overrides.pop(get_current_user)
            assert (await client.post(url + "/cancel")).status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
async def test_cancel_interrupts_inflight_criteria_and_retains_completed_results(
    db_session, writing, settings
):
    from app.services.writing_ai_worker import _tasks

    class PartialProvider(FakeProvider):
        def __init__(self):
            super().__init__()
            self.blocked = set()
            self.interrupted = set()
            self.waiting = asyncio.Event()

        async def complete(self, messages, schema, *, options=None):
            trait = next(trait for trait in TRAITS if TRAIT_NAMES[trait] in messages[0]["content"])
            if trait in {"lr", "gra"}:
                self.blocked.add(trait)
                if len(self.blocked) == 2:
                    self.waiting.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.interrupted.add(trait)
                    raise
            return await super().complete(messages, schema, options=options)

    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    provider = PartialProvider()
    runner = worker(
        db_session,
        settings.model_copy(update={"ai_writing_max_concurrent_llm_requests": 4}),
        provider,
    )
    completed = set()
    partial_ready = asyncio.Event()
    checkpoint = runner._checkpoint

    async def record_checkpoint(run_id, event, payload, *args):
        await checkpoint(run_id, event, payload, *args)
        if event == "criterion.completed":
            completed.add(payload.criterion)
            if len(completed) == 2:
                partial_ready.set()

    runner._checkpoint = record_checkpoint
    runner.launch(created.run_id)
    job = _tasks[created.run_id]
    try:
        await asyncio.wait_for(asyncio.gather(provider.waiting.wait(), partial_ready.wait()), 5)
        stopped = await api.cancel(created.run_id)
        runner.cancel(created.run_id)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(job, 5)
        assert provider.interrupted == {"lr", "gra"} and provider.scored == 2
        saved = await api.get(created.run_id)
        assert saved == stopped and set(saved.progress) == {"ta", "cc"}
        assert saved.error_code == CANCELLATION_CODE and saved.result is None
        assert saved.failures == {}
    finally:
        if not job.done():
            job.cancel()
            await asyncio.gather(job, return_exceptions=True)


class FakeProvider:
    def __init__(self, overrides=None):
        self.calls = []
        self.overrides = overrides or {}
        self.scored = 0
        self.attempts = {}

    async def ensure_ready(self):
        pass

    async def complete(self, messages, schema, *, options=None):
        trait = next(trait for trait in TRAITS if TRAIT_NAMES[trait] in messages[0]["content"])
        stage = "evidence" if "evidence" in schema["properties"] else "scoring"
        self.attempts[trait, stage] = self.attempts.get((trait, stage), 0) + 1
        identity = trait, stage, self.attempts[trait, stage]
        self.calls.append(messages)
        if identity in self.overrides:
            output = self.overrides[identity]
            if isinstance(output, Exception):
                raise output
            return Completion(output)
        if "evidence" in schema["properties"]:
            value = {
                "evidence": [
                    {
                        "source_id": "P1S1",
                        "assessment": "Luận điểm trả lời trực tiếp yêu cầu của đề.",
                    }
                ]
            }
        else:
            value = {
                "score": {"ta": 6.5, "cc": 6, "lr": 7, "gra": 6}[trait],
                "feedback": "Cần phát triển chi tiết hỗ trợ cho luận điểm.",
                "strengths": ["Diễn đạt rõ ràng."],
                "improvements": ["Bổ sung một ví dụ cụ thể."],
            }
            self.scored += 1
        return Completion(json.dumps(value), {"total_tokens": 10})


@pytest.fixture
def settings():
    return Settings(
        _env_file=None, ai_writing_enabled=True, ai_writing_vllm_base_url="https://llm.example/v1"
    )


@pytest_asyncio.fixture
async def writing(db_session):
    now = datetime.now(UTC)
    test = DomainTest(title=f"Fictional AI writing {uuid4()}")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED, published_at=now)
    module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
    task_one = WritingTask(task_number=1, prompt="Describe fictional data.", order_index=0)
    task_two = WritingTask(task_number=2, prompt="Discuss fictional city parks.", order_index=1)
    test.versions.append(version)
    version.modules.append(module)
    module.writing_tasks.extend([task_one, task_two])
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
        attempt = Attempt(
            user_id=db_session.info["current_user_id"],
            test_version_id=version.id,
            module_type=ModuleType.WRITING,
            status=AttemptStatus.SUBMITTED,
            timer_mode=TimerMode.COUNT_UP,
            started_at=now,
            last_active_at=now,
            finished_at=now,
            band_score=Decimal("7.0"),
        )
        db_session.add(attempt)
        await db_session.flush()
        db_session.add_all(
            [
                AttemptWritingResponse(
                    attempt_id=attempt.id, writing_task_id=task_two.id, content=ESSAY, word_count=12
                ),
                AttemptWritingScore(
                    attempt_id=attempt.id,
                    writing_task_id=task_two.id,
                    ta=7,
                    cc=7,
                    lr=7,
                    gra=7,
                    ta_feedback="Human feedback stays.",
                ),
            ]
        )
    return attempt.id, task_one.id, task_two.id


def service(session, settings, owner=None):
    return WritingAIService(session, owner or session.info["current_user_id"], settings)


def worker(session, settings, provider=None):
    # Separate worker sessions, same rollback-isolated PostgreSQL test connection.
    factory = async_sessionmaker(
        session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    return WritingAIWorker(factory, settings, provider or FakeProvider())


@pytest.mark.integration
async def test_concurrent_out_of_order_checkpoints_are_canonical_replayable_and_measured(
    db_session, writing, settings
):
    release_cc = asyncio.Event()
    completed = []

    class Provider(FakeProvider):
        async def complete(self, messages, schema, *, options=None):
            if TRAIT_NAMES["cc"] in messages[0]["content"] and "score" in schema["properties"]:
                await release_cc.wait()
            return await super().complete(messages, schema, options=options)

    api = service(db_session, settings)
    created = await api.create(writing[0], writing[2], force=False)
    runner = worker(db_session, settings, Provider())
    original = runner._checkpoint

    async def checkpoint(run_id, event, payload, *args):
        await original(run_id, event, payload, *args)
        if event == "criterion.completed":
            completed.append(payload.criterion)
            partial = await api.get(run_id)
            assert list(partial.progress) == [trait for trait in TRAITS if trait in completed]
            if len(completed) == 3:
                assert "cc" not in partial.progress and partial.result is None
                release_cc.set()

    runner._checkpoint = checkpoint
    await asyncio.wait_for(runner.execute(created.run_id), 10)
    run, events = await api.snapshot(created.run_id, 0)
    assert completed[-1] == "cc" and run.status == WritingAIRunStatus.COMPLETED
    assert list(run.progress) == list(run.result.criteria.model_dump()) == list(TRAITS)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    gra = next(
        event
        for event in events
        if event.event_type == "criterion.completed" and event.payload.criterion == "gra"
    )
    restored, replay = await api.snapshot(run.id, gra.sequence)
    assert restored == run and any(
        event.payload.criterion == "cc" and event.event_type == "criterion.completed"
        for event in replay
    )
    async with db_session.begin():
        db_session.expire_all()
        stored = await db_session.get(WritingAIGradingRun, run.id)
        metrics = stored.usage_json["latency"]
        assert metrics["run_total_ms"] >= metrics["time_to_first_criterion_ms"] > 0
        assert metrics["provider_ready_ms"] >= 0
        assert metrics["llm_concurrency_limit"] == 2 and metrics["peak_active_llm_requests"] <= 2
        assert set(metrics["stages"]) == {"provider_ready"} | {
            f"{trait}.{stage}" for trait in TRAITS for stage in ("evidence", "scoring")
        }
        assert ESSAY not in json.dumps(metrics)


@pytest.mark.parametrize("score", [Decimal(i) / 2 for i in range(19)])
def test_ai_half_band_validation(score):
    assert TraitScore(score=score, feedback="Useful.", strengths=[], improvements=[]).score == score


@pytest.mark.parametrize("score", [-0.5, 9.5, 7.25, "NaN", "Infinity", "-Infinity"])
def test_invalid_ai_scores(score):
    with pytest.raises(ValidationError):
        TraitScore(score=score, feedback="Useful.", strengths=[], improvements=[])


def test_ai_mean_uses_existing_half_rounding(monkeypatch):
    import app.domains.scoring.ai_writing as domain

    original = domain.round_to_half
    spy = Mock(side_effect=original)
    monkeypatch.setattr(domain, "round_to_half", spy)
    assert aggregate_ai_task_two(*map(Decimal, ["6.5", "6", "7", "6"])) == (
        Decimal("6.375"),
        Decimal("6.5"),
    )
    spy.assert_called_once_with(Decimal("6.375"))


@pytest.mark.parametrize("changed", ["prompt", "response", "version", "provider", "model"])
def test_fingerprint_changes_with_each_input(changed):
    request = WritingScoringRequest(
        attempt_id=uuid4(), writing_task_id=uuid4(), prompt="Fictional", response=ESSAY
    )
    baseline = input_fingerprint(request, "v1", "fake", "model")
    updated = (
        request.model_copy(update={changed: "changed"})
        if changed in {"prompt", "response"}
        else request
    )
    other = input_fingerprint(
        updated,
        "v2" if changed == "version" else "v1",
        "other" if changed == "provider" else "fake",
        "other" if changed == "model" else "model",
    )
    assert len(baseline) == 64 and baseline != other
    assert baseline == input_fingerprint(request, "v1", "fake", "model")


@pytest.mark.integration
async def test_success_persistence_cache_force_events_and_official_isolation(
    db_session, writing, settings
):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    duplicate = await api.create(attempt_id, task_id, force=False)
    assert duplicate.run_id == created.run_id and duplicate.existing_active
    provider = FakeProvider()
    runner = worker(db_session, settings, provider)
    await runner.execute(created.run_id)
    saved, events = await api.snapshot(created.run_id, 0)
    assert saved.status == WritingAIRunStatus.COMPLETED
    assert saved.result.raw_mean == Decimal("6.375")
    assert saved.result.overall_band == Decimal("6.5")
    assert len(events) == 32
    assert [event.sequence for event in events] == list(range(1, 33))
    assert [event.event_type for event in events[1:4]] == [
        "provider.starting",
        "provider.ready",
        "criterion.started",
    ]
    assert events[0].event_type == "run.started" and events[-1].event_type == "run.completed"
    assert len(provider.calls) == 8
    for trait in TRAITS:
        assert [event.event_type for event in events if event.payload.criterion == trait] == [
            "criterion.started",
            "evidence.request.started",
            "evidence.validation.started",
            "criterion.evidence.completed",
            "criterion.scoring.started",
            "criterion.scoring.validation.started",
            "criterion.completed",
        ]
        assert all(event.created_at is not None for event in events)
        calls = [call for call in provider.calls if TRAIT_NAMES[trait] in call[0]["content"]]
        assert len(calls) == 2
        assert all(
            TRAIT_NAMES[other] not in calls[1][0]["content"] for other in TRAITS if other != trait
        )
        assert "UNTRUSTED DATA" in calls[0][0]["content"]
    cached = await api.create(attempt_id, task_id, force=False)
    assert cached.run_id == created.run_id and cached.cache_hit
    forced = await api.create(attempt_id, task_id, force=True)
    assert forced.run_id != created.run_id and not forced.cache_hit
    history = await api.list(attempt_id, task_id)
    assert len(history.items) == 2
    assert history.items[1].result is not None
    async with db_session.begin():
        db_session.expire_all()
        attempt = await db_session.get(Attempt, attempt_id)
        score = await db_session.scalar(
            select(AttemptWritingScore).where(AttemptWritingScore.attempt_id == attempt_id)
        )
        run = await db_session.get(WritingAIGradingRun, created.run_id)
        assert run.raw_mean == Decimal("6.375")
        assert run.usage_json["calls"] == [{"total_tokens": 10}] * 8
        assert run.usage_json["diagnostics"] == []
        assert run.usage_json["activity"]["phase"] == "completed"
        assert attempt.band_score == Decimal("7.0")
        assert (score.ta, score.cc, score.lr, score.gra, score.ta_feedback) == (
            7,
            7,
            7,
            7,
            "Human feedback stays.",
        )
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(AttemptWritingScore)
                .where(AttemptWritingScore.attempt_id == attempt_id)
            )
            == 1
        )


@pytest.mark.integration
async def test_ai_does_not_create_manual_score_for_ungraded_attempt(db_session, writing, settings):
    from sqlalchemy import delete

    attempt_id, _, task_id = writing
    async with db_session.begin():
        await db_session.execute(
            delete(AttemptWritingScore).where(AttemptWritingScore.attempt_id == attempt_id)
        )
        attempt = await db_session.get(Attempt, attempt_id)
        attempt.band_score = None
    created = await service(db_session, settings).create(attempt_id, task_id, force=False)
    await worker(db_session, settings).execute(created.run_id)
    async with db_session.begin():
        db_session.expire_all()
        assert (await db_session.get(Attempt, attempt_id)).band_score is None
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(AttemptWritingScore)
                .where(AttemptWritingScore.attempt_id == attempt_id)
            )
            == 0
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "violation,code",
    [
        ("task1", "AI_EMPTY_ESSAY"),
        ("active", "ATTEMPT_NOT_FINALIZED"),
        ("paused", "ATTEMPT_NOT_FINALIZED"),
        ("empty", "AI_EMPTY_ESSAY"),
        ("missing", "AI_EMPTY_ESSAY"),
        ("foreign", "INVALID_WRITING_TASK"),
        ("owner", "ATTEMPT_NOT_FOUND"),
        ("reading", "WRITING_ATTEMPT_REQUIRED"),
        ("long", "AI_INPUT_TOO_LONG"),
    ],
)
async def test_ai_scope_enforced(db_session, writing, settings, violation, code):
    from sqlalchemy import delete

    attempt_id, task_one_id, task_id = writing
    async with db_session.begin():
        if violation in {"active", "paused", "reading"}:
            attempt = await db_session.get(Attempt, attempt_id)
            if violation == "reading":
                attempt.module_type = ModuleType.READING
            else:
                attempt.status = (
                    AttemptStatus.PAUSED if violation == "paused" else AttemptStatus.IN_PROGRESS
                )
        if violation in {"empty", "long"}:
            essay = await db_session.scalar(
                select(AttemptWritingResponse).where(
                    AttemptWritingResponse.attempt_id == attempt_id
                )
            )
            essay.content = " " if violation == "empty" else "x" * 12_001
        if violation == "missing":
            await db_session.execute(
                delete(AttemptWritingResponse).where(
                    AttemptWritingResponse.attempt_id == attempt_id
                )
            )
    requested_task = (
        task_one_id if violation == "task1" else uuid4() if violation == "foreign" else task_id
    )
    with pytest.raises(AppError) as error:
        await service(db_session, settings, uuid4() if violation == "owner" else None).create(
            attempt_id, requested_task, force=False
        )
    assert error.value.code == code
    async with db_session.begin():
        assert await db_session.scalar(select(func.count()).select_from(WritingAIGradingRun)) == 0


@pytest.mark.integration
async def test_task_from_other_version_rejected(db_session, writing, settings):
    attempt_id, _, _ = writing
    async with db_session.begin():
        test = DomainTest(title="Foreign fictional version")
        version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
        module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
        task = WritingTask(task_number=2, prompt="Foreign fictional prompt", order_index=0)
        test.versions.append(version)
        version.modules.append(module)
        module.writing_tasks.append(task)
        db_session.add(test)
        await db_session.flush()
        foreign_id = task.id
    with pytest.raises(AppError, match="INVALID_WRITING_TASK"):
        await service(db_session, settings).create(attempt_id, foreign_id, force=False)


@pytest.mark.integration
@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        '{"score":7.25,"feedback":"x","strengths":[],"improvements":[]}',
        '{"score":10,"feedback":"x","strengths":[],"improvements":[]}',
    ],
)
async def test_bad_trait_call_repaired_once(db_session, writing, settings, bad):
    attempt_id, _, task_id = writing
    created = await service(db_session, settings).create(attempt_id, task_id, force=False)
    provider = FakeProvider({("ta", "scoring", 1): bad})
    await worker(db_session, settings, provider).execute(created.run_id)
    assert (
        await service(db_session, settings).get(created.run_id)
    ).status == WritingAIRunStatus.COMPLETED
    assert len(provider.calls) == 9
    ta_scores = [
        call
        for call in provider.calls
        if TRAIT_NAMES["ta"] in call[0]["content"]
        and "Return only four fields" in call[0]["content"]
    ]
    assert len(ta_scores) == 2 and "Correction (" in ta_scores[1][-1]["content"]
    assert ta_scores[0][0] == ta_scores[1][0]


@pytest.mark.integration
async def test_second_bad_call_fails_and_preserves_partial_progress(db_session, writing, settings):
    attempt_id, _, task_id = writing
    created = await service(db_session, settings).create(attempt_id, task_id, force=False)
    provider = FakeProvider(
        {
            ("cc", "scoring", 1): "malformed secret raw text",
            ("cc", "scoring", 2): "still malformed secret raw text",
        }
    )
    await worker(db_session, settings, provider).execute(created.run_id)
    run, events = await service(db_session, settings).snapshot(created.run_id, 0)
    assert run.status == WritingAIRunStatus.FAILED and run.error_code == "AI_PROVIDER_BAD_RESPONSE"
    assert set(run.progress) == {"ta", "lr", "gra"} and run.result is None
    assert len(provider.calls) == 9 and events[-1].event_type == "run.failed"
    assert "secret" not in run.model_dump_json() + str(events)
    retried = await service(db_session, settings).create(attempt_id, task_id, force=False)
    assert retried.run_id != run.id


@pytest.mark.integration
async def test_lr_evidence_failure_retains_ta_cc_runs_gra_and_terminates_replay(
    db_session, writing, settings
):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    invalid_source = json.dumps({"evidence": [{"source_id": "P99S1", "assessment": "Nhận xét."}]})
    provider = FakeProvider(
        {("lr", "evidence", 1): invalid_source, ("lr", "evidence", 2): invalid_source}
    )
    runner = worker(db_session, settings, provider)
    await runner.execute(created.run_id)
    run, events = await api.snapshot(created.run_id, 0)
    assert run.status == WritingAIRunStatus.FAILED and run.result is None
    assert set(run.progress) == {"ta", "cc", "gra"}
    assert run.activity.phase == "failed" and run.activity.criterion == "lr"
    assert run.activity.stage == "evidence"
    assert not any(
        e.event_type == "criterion.scoring.started" and e.payload.criterion == "lr" for e in events
    )
    assert len(provider.calls) == 8
    assert set(run.failures) == {"lr"}
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))
    async with db_session.begin():
        db_session.expire_all()
        stored = await db_session.get(WritingAIGradingRun, run.id)
        assert stored.raw_mean is None and stored.overall_band is None
        assert stored.usage_json["diagnostics"] == [
            {
                "stage": "evidence",
                "criterion": "lr",
                "reason": "EVIDENCE_UNKNOWN_SOURCE_ID",
                "attempt": n,
                "finish_reason": "stop",
                "validation_issues": [],
            }
            for n in [1, 2]
        ]
        assert "private invented" not in json.dumps(stored.usage_json) + json.dumps(
            stored.result_json
        )
    connected = Mock()

    async def no():
        return False

    connected.is_disconnected = no
    stream = "".join(
        [
            item
            async for item in routes.event_stream(
                connected, run.id, db_session.info["current_user_id"], events[-3].sequence, runner
            )
        ]
    )
    assert "event: run.failed" in stream
    assert "QUOTE_NOT_EXACT" not in stream + run.model_dump_json()
    assert "private invented" not in stream + run.model_dump_json()
    assert "event: criterion.completed" in stream
    forced = await api.create(attempt_id, task_id, force=True)
    fresh = FakeProvider()
    await worker(db_session, settings, fresh).execute(forced.run_id)
    assert len(fresh.calls) == 8
    assert (await api.get(run.id)).progress == run.progress


@pytest.mark.integration
async def test_interruption_after_lr_failure_persists_gra_failure_and_partial_results(
    db_session, writing, settings
):
    ready_to_cancel = asyncio.Event()
    done = set()

    class InterruptedProvider(FakeProvider):
        async def complete(self, messages, schema, *, options=None):
            if TRAIT_NAMES["gra"] in messages[0]["content"]:
                await ready_to_cancel.wait()
                raise asyncio.CancelledError
            return await super().complete(messages, schema, options=options)

    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    bad = '{"evidence":[{"source_id":"P99S1","assessment":"Nhận xét."}]}'
    runner = worker(
        db_session,
        settings,
        InterruptedProvider({("lr", "evidence", 1): bad, ("lr", "evidence", 2): bad}),
    )
    original = runner._checkpoint

    async def checkpoint(run_id, event, payload, *args):
        await original(run_id, event, payload, *args)
        if event in {"criterion.completed", "criterion.failed"}:
            done.add(payload.criterion)
            if {"ta", "cc", "lr"} <= done:
                ready_to_cancel.set()

    runner._checkpoint = checkpoint
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(runner.execute(created.run_id), 5)
    run, events = await api.snapshot(created.run_id, 0)
    assert run.status == WritingAIRunStatus.FAILED and run.result is None
    assert set(run.progress) == {"ta", "cc"}
    assert set(run.failures) == {"lr", "gra"}
    assert run.failures["gra"].error_code == "RUN_INTERRUPTED"
    assert [e.payload.criterion for e in events if e.event_type == "criterion.failed"] == [
        "lr",
        "gra",
    ]
    assert events[-1].event_type == "run.failed"


@pytest.mark.integration
async def test_partial_checkpoint_visible_during_concurrent_work_and_heartbeat_is_only_liveness(
    db_session, writing, settings
):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    runner = worker(db_session, settings)

    original = runner._checkpoint

    async def checkpoint(run_id, event, payload, *args):
        await original(run_id, event, payload, *args)
        if event == "criterion.completed" and payload.criterion == "ta":
            before = await api.get(created.run_id)
            assert "ta" in before.progress and before.result is None
            await original(created.run_id, "heartbeat", EventPayload())
            after = await api.get(created.run_id)
            assert after.progress == before.progress and after.activity == before.activity

    runner._checkpoint = checkpoint
    await runner.execute(created.run_id)
    saved, events = await api.snapshot(created.run_id, 0)
    assert saved.status == WritingAIRunStatus.COMPLETED
    assert any(event.event_type == "heartbeat" for event in events)


@pytest.mark.integration
@pytest.mark.parametrize(
    "calibration",
    [
        {
            "next_band": 8.5,
            "support": [{"source_id": "P99S1", "assessment": "Nhận xét."}],
            "next_band_blockers": [],
        },
        "malformed private metadata",
    ],
)
async def test_gra_optional_calibration_completes_persists_and_replays_without_retry(
    db_session, writing, settings, calibration
):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    gra = {
        "score": 8.5,
        "feedback": "Câu phức được sử dụng linh hoạt, nhưng một vài dấu câu cần rà soát.",
        "strengths": ["Phần lớn câu chính xác."],
        "improvements": ["Kiểm tra dấu câu ở các mệnh đề dài."],
        "calibration": calibration,
    }
    provider = FakeProvider({("gra", "scoring", 1): json.dumps(gra)})
    runner = worker(db_session, settings, provider)
    await runner.execute(created.run_id)
    saved, events = await api.snapshot(created.run_id, 0)
    assert saved.status == WritingAIRunStatus.COMPLETED and not saved.failures
    assert saved.result.criteria.gra.score == Decimal("8.5")
    assert saved.result.raw_mean == Decimal("7") and saved.result.overall_band == Decimal("7")
    assert set(saved.progress) == set(TRAITS) and len(provider.calls) == 8
    assert not any(e.event_type in {"criterion.retrying", "criterion.failed"} for e in events)
    completed = [e for e in events if e.event_type == "criterion.completed"]
    assert {e.payload.criterion for e in completed} == set(TRAITS)
    assert next(
        e for e in completed if e.payload.criterion == "gra"
    ).payload.result.score == Decimal("8.5")
    assert completed[-1].sequence < events[-1].sequence
    assert events[-1].event_type == "run.completed"
    # Reconnecting with an event cursor restores the completed result and does
    # not launch inference again. A fresh snapshot retains all four cards.
    restored, replay = await api.snapshot(created.run_id, completed[-1].sequence - 1)
    assert restored.progress == saved.progress
    assert [e.event_type for e in replay] == ["criterion.completed", "run.completed"]
    await runner.execute(created.run_id)
    assert len(provider.calls) == 8
    assert "private" not in saved.model_dump_json() + str(events)
    async with db_session.begin():
        db_session.expire_all()
        stored = await db_session.get(WritingAIGradingRun, created.run_id)
        assert len(stored.usage_json["calls"]) == 8
        assert stored.usage_json["diagnostics"]
        assert all(d["reason"].startswith("CALIBRATION_") for d in stored.usage_json["diagnostics"])
        assert "private" not in json.dumps(stored.usage_json)
        human = await db_session.scalar(
            select(AttemptWritingScore).where(AttemptWritingScore.attempt_id == attempt_id)
        )
        assert human.gra == 7 and human.ta_feedback == "Human feedback stays."
        assert (await db_session.get(Attempt, attempt_id)).band_score == Decimal("7")


@pytest.mark.integration
@pytest.mark.parametrize(
    "old_version",
    [
        "mts-task2-v1",
        "mts-task2-v2",
        "mts-task2-v3",
        "mts-task2-v4",
        "mts-task2-v5",
        "mts-task2-v6",
    ],
)
async def test_old_cache_is_preserved_but_never_reused_for_v7(
    db_session, writing, settings, old_version
):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    legacy = await api.create(attempt_id, task_id, force=False)
    await worker(db_session, settings).execute(legacy.run_id)
    old_result = (await api.get(legacy.run_id)).result
    async with db_session.begin():
        request = await api.input(attempt_id, task_id)
        stored = await db_session.get(WritingAIGradingRun, legacy.run_id)
        stored.prompt_version = old_version
        stored.input_fingerprint = input_fingerprint(
            request, stored.prompt_version, stored.provider, stored.model
        )
    settings.ai_writing_prompt_version = old_version  # Existing deployed secret.
    upgraded = await api.create(attempt_id, task_id, force=False)
    assert upgraded.run_id != legacy.run_id and not upgraded.cache_hit
    assert (await api.get(upgraded.run_id)).prompt_version == "mts-task2-v7"
    history = await api.list(attempt_id, task_id)
    assert len(history.items) == 2
    assert history.items[1].prompt_version == old_version and history.items[1].result == old_result


@pytest.mark.integration
async def test_verbose_lr_normalizes_persists_live_and_replays_without_inference(
    db_session, writing, settings
):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    paragraph = (
        "Từ vựng phù hợp để trình bày quan điểm, nhưng một số cách kết hợp từ chưa tự nhiên. "
        "Cần lựa chọn từ chính xác hơn và kiểm tra dạng từ trong các ví dụ hỗ trợ. "
    ) * 8
    lr = {
        "score": 6.5,
        "feedback": paragraph,
        "strengths": ["  ", paragraph, "Từ vựng phù hợp.", "Diễn đạt rõ ý.", "Một ý khác."],
        "improvements": [paragraph, "Chọn từ chính xác hơn."],
    }

    provider = FakeProvider({("lr", "scoring", 1): json.dumps(lr)})
    runner = worker(db_session, settings, provider)
    original = runner._checkpoint

    async def checkpoint(run_id, event, payload, *args):
        await original(run_id, event, payload, *args)
        if event == "criterion.completed" and payload.criterion == "lr":
            live = await api.get(created.run_id)
            assert live.status == WritingAIRunStatus.RUNNING and live.result is None
            assert "lr" in live.progress and not live.failures
            assert live.progress["lr"].score == Decimal("6.5")
            assert len(live.progress["lr"].feedback) <= 800

    runner._checkpoint = checkpoint
    await runner.execute(created.run_id)
    saved, events = await api.snapshot(created.run_id, 0)
    assert saved.status == WritingAIRunStatus.COMPLETED
    assert saved.result.overall_band == Decimal("6.5") and len(provider.calls) == 8
    result = saved.progress["lr"]
    assert result.score == Decimal("6.5") and result.feedback.endswith("…")
    assert len(result.feedback) <= 800 and paragraph.startswith(result.feedback[:-1])
    assert len(result.strengths) == 3 and result.strengths[0].endswith("…")
    assert all(0 < len(v) <= 240 for v in result.strengths + result.improvements)
    assert result.evidence[0].quote == "Fictional parks improve city life."
    assert not any(e.event_type in {"criterion.retrying", "criterion.failed"} for e in events)
    completed = next(
        e for e in events if e.event_type == "criterion.completed" and e.payload.criterion == "lr"
    )
    gra_started = next(
        e for e in events if e.event_type == "criterion.started" and e.payload.criterion == "gra"
    )
    assert gra_started.sequence < completed.sequence
    snapshot, replay = await api.snapshot(created.run_id, completed.sequence - 1)
    assert snapshot.progress == saved.progress
    assert replay[0].payload.result == result
    await runner.execute(created.run_id)
    assert len(provider.calls) == 8
    public = saved.model_dump_json() + str(events)
    assert "SCORE_PRESENTATION_NORMALIZED" not in public and "validation_issues" not in public
    async with db_session.begin():
        db_session.expire_all()
        stored = await db_session.get(WritingAIGradingRun, created.run_id)
        diagnostic = stored.usage_json["diagnostics"][0]
        assert diagnostic["reason"] == "SCORE_PRESENTATION_NORMALIZED"
        assert {"field": "feedback", "validation_type": "string_too_long"} in diagnostic[
            "validation_issues"
        ]
        assert paragraph[:50] not in json.dumps(stored.usage_json)
        assert stored.result_json["criteria"]["lr"]["feedback"] == result.feedback
        human = await db_session.scalar(
            select(AttemptWritingScore).where(AttemptWritingScore.attempt_id == attempt_id)
        )
        assert human.lr == 7 and (await db_session.get(Attempt, attempt_id)).band_score == Decimal(
            "7"
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "code",
    [
        "PROVIDER_TIMEOUT",
        "PROVIDER_HTTP_ERROR",
        "AI_PROVIDER_AUTH_FAILED",
        "AI_PROVIDER_TIMEOUT",
        "AI_PROVIDER_UNREACHABLE",
    ],
)
async def test_provider_failure_safe_retryable(db_session, writing, settings, code):
    attempt_id, _, task_id = writing
    created = await service(db_session, settings).create(attempt_id, task_id, force=False)
    await worker(
        db_session, settings, FakeProvider({("ta", "evidence", 1): ProviderFailure(code)})
    ).execute(created.run_id)
    run, events = await service(db_session, settings).snapshot(created.run_id, 0)
    assert run.status == WritingAIRunStatus.FAILED and run.error_code == code
    assert events[-1].event_type == "run.failed"


@pytest.mark.integration
@pytest.mark.parametrize("status", [WritingAIRunStatus.PENDING, WritingAIRunStatus.RUNNING])
async def test_stale_run_recovery_and_no_resurrection(db_session, writing, settings, status):
    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    async with db_session.begin():
        run = await db_session.get(WritingAIGradingRun, created.run_id)
        run.status = status
        run.updated_at = datetime.now(UTC) - timedelta(seconds=100)
    result, events = await api.snapshot(created.run_id, 0)
    assert result.status == WritingAIRunStatus.FAILED and result.error_code == "STALE_RUN"
    assert [item.event_type for item in events] == ["run.failed"]
    provider = FakeProvider()
    await worker(db_session, settings, provider).execute(created.run_id)
    assert provider.calls == []
    assert (await api.create(attempt_id, task_id, force=False)).run_id != created.run_id


@pytest.mark.integration
async def test_disabled_provider_graceful_and_key_independence(db_session, writing, settings):
    attempt_id, _, task_id = writing
    assert is_configured(settings)  # vLLM does not need an OpenAI key.
    settings.ai_writing_enabled = False
    assert not (await service(db_session, settings).list(attempt_id, task_id)).configured
    with pytest.raises(AppError, match="AI_NOT_CONFIGURED"):
        await service(db_session, settings).create(attempt_id, task_id, force=False)
    settings.ai_writing_enabled = True
    settings.ai_writing_provider = "openai"
    assert not is_configured(settings)
    with pytest.raises(AppError, match="AI_NOT_CONFIGURED"):
        create_provider(settings)


@pytest.mark.integration
async def test_sse_api_replay_auth_disconnect_and_no_raw_content(
    db_session, writing, settings, monkeypatch
):
    attempt_id, _, task_id = writing
    runner = worker(db_session, settings)
    launches = []
    monkeypatch.setattr(runner, "launch", launches.append)
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    app.dependency_overrides[routes.get_worker] = lambda: runner
    app.dependency_overrides[get_current_user] = lambda: db_session.info["current_user_identity"]

    async def session_override():
        async with runner.sessions() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            path = f"/api/v1/attempts/{attempt_id}/writing/{task_id}/ai-grading-runs"
            created = await client.post(path, json={"force": False})
            assert created.status_code == 200 and len(launches) == 1
            duplicate = await client.post(path, json={})
            assert duplicate.json()["existing_active"] and len(launches) == 1
            run_id = launches[0]
            await runner.execute(run_id)
            url = f"/api/v1/ai-writing-grading-runs/{run_id}"
            assert (await client.get(url)).json()["result"]["overall_band"] == 6.5
            stream = await client.get(url + "/events")
            assert stream.headers["content-type"].startswith("text/event-stream")
            assert stream.headers["x-accel-buffering"] == "no"
            assert "id: 1\n" in stream.text and "id: 32\n" in stream.text
            replay = await client.get(url + "/events?after=3", headers={"Last-Event-ID": "16"})
            assert "id: 16\n" not in replay.text and "id: 17\n" in replay.text
            assert "UNTRUSTED DATA" not in stream.text and "usage" not in stream.text
            assert (
                await client.get(url + "/events", headers={"Last-Event-ID": "bad"})
            ).status_code == 422
            assert (await client.get(url + "/events?after=32")).text == ""
            assert len((await client.get(path)).json()["items"]) == 1
            assert (await client.post(path, json={})).json()["cache_hit"]
            assert (await client.post(path, json={"force": True})).json()["run_id"] != str(run_id)
            # A disconnected stream exits without cancelling or changing the job.
            disconnected = Mock()

            async def yes():
                return True

            disconnected.is_disconnected = yes
            assert [
                item
                async for item in routes.event_stream(
                    disconnected, run_id, db_session.info["current_user_id"], 0, runner
                )
            ] == []
            foreign = Mock(id=uuid4())
            app.dependency_overrides[get_current_user] = lambda: foreign
            assert (await client.get(url)).status_code == 404
            assert (await client.get(url + "/events")).status_code == 404
            assert (await client.get(path)).status_code == 404
            assert (await client.post(path, json={})).status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_protocol_adapter_and_unknown_source_repair():
    request = WritingScoringRequest(
        attempt_id=uuid4(), writing_task_id=uuid4(), prompt="Fictional parks?", response=ESSAY
    )
    provider = FakeProvider(
        {("ta", "evidence", 1): '{"evidence":[{"source_id":"P99S1","assessment":"Nhận xét."}]}'}
    )
    scoring: WritingScoringProvider = MTSWritingScoringService(provider)
    result = await scoring.score(request)
    assert result.overall_band == 6.5 and len(provider.calls) == 9


@pytest.mark.integration
async def test_worker_heartbeat_is_persisted(db_session, writing, settings):
    attempt_id, _, task_id = writing
    created = await service(db_session, settings).create(attempt_id, task_id, force=False)
    await worker(db_session, settings)._checkpoint(created.run_id, "heartbeat", EventPayload())
    async with db_session.begin():
        event = await db_session.scalar(
            select(WritingAIGradingEvent).where(WritingAIGradingEvent.run_id == created.run_id)
        )
        assert event.event_type == "heartbeat" and event.sequence == 1


@pytest.mark.integration
async def test_readiness_failure_emits_failed_before_essay_inference(db_session, writing, settings):
    class UnreadyProvider(FakeProvider):
        async def ensure_ready(self):
            raise ProviderFailure("AI_MODEL_UNAVAILABLE")

    attempt_id, _, task_id = writing
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    provider = UnreadyProvider()
    await worker(db_session, settings, provider).execute(created.run_id)
    run, events = await api.snapshot(created.run_id, 0)
    assert run.status == WritingAIRunStatus.FAILED
    assert run.error_code == "AI_MODEL_UNAVAILABLE"
    assert [event.event_type for event in events] == [
        "run.started",
        "provider.starting",
        "run.failed",
    ]
    assert not provider.calls
    assert (await api.create(attempt_id, task_id, force=True)).run_id != created.run_id


@pytest.mark.integration
@pytest.mark.parametrize("cancel_job", [False, True])
async def test_disconnect_keeps_job_alive_and_shutdown_cancellation_is_retryable(
    db_session, writing, settings, cancel_job
):
    class WaitingProvider(FakeProvider):
        def __init__(self):
            super().__init__()
            self.waiting = asyncio.Event()
            self.release = asyncio.Event()

        async def complete(self, messages, schema, *, options=None):
            if not self.calls:
                self.waiting.set()
                await self.release.wait()
            return await super().complete(messages, schema, options=options)

    attempt_id, _, task_id = writing
    created = await service(db_session, settings).create(attempt_id, task_id, force=False)
    provider = WaitingProvider()
    runner = worker(db_session, settings, provider)
    job = asyncio.create_task(runner.execute(created.run_id))
    await asyncio.wait_for(provider.waiting.wait(), timeout=5)
    disconnected = Mock()

    async def yes():
        return True

    disconnected.is_disconnected = yes
    assert [
        item
        async for item in routes.event_stream(
            disconnected, created.run_id, db_session.info["current_user_id"], 0, runner
        )
    ] == []
    assert not job.done()
    if cancel_job:
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        run = await service(db_session, settings).get(created.run_id)
        assert run.status == WritingAIRunStatus.FAILED and run.error_code == "RUN_INTERRUPTED"
    else:
        provider.release.set()
        await job
        assert (
            await service(db_session, settings).get(created.run_id)
        ).status == WritingAIRunStatus.COMPLETED
