"""Personal latest snapshots are copied from durable AI output, never official scores."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from test_writing_ai import settings as settings
from test_writing_ai import worker
from test_writing_ai import writing as writing
from test_writing_relevance import RelevanceProvider, assessment

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.exceptions import AppError
from app.main import app
from app.models import (
    Attempt,
    AttemptWritingScore,
    User,
    WritingAIGradingRun,
    WritingAIPracticeFeedback,
    WritingTask,
)
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import (
    AttemptScope,
    AttemptStatus,
    ModuleType,
    TimerMode,
    UserRole,
    VersionStatus,
    WritingAIRunStatus,
)
from app.services.writing_ai import WritingAIService
from app.services.writing_ai_practice_feedback import WritingAIPracticeFeedbackService


@pytest_asyncio.fixture
async def focused(db_session, writing, settings, test_user):
    attempt_id, _, task_id = writing
    async with db_session.begin():
        attempt = await db_session.get(Attempt, attempt_id)
        attempt.user_id = test_user.id
        attempt.scope = AttemptScope.FOCUSED_UNIT
        attempt.focused_writing_task_id = task_id
    api = WritingAIService(db_session, test_user.id, settings)
    run = await api.create(attempt_id, task_id, force=False)
    await worker(
        db_session, settings, RelevanceProvider(output=assessment("WHOLLY_UNRELATED"))
    ).execute(run.run_id)
    return attempt_id, task_id, run.run_id, test_user.id


async def mutate(session, model, identity, **values):
    async with session.begin():
        row = await session.get(model, identity)
        for key, value in values.items():
            setattr(row, key, value)


async def test_latest_snapshot_upsert_official_isolation_and_cascade(db_session, focused, settings):
    attempt_id, task_id, run_id, user_id = focused
    service = WritingAIPracticeFeedbackService(db_session, user_id)
    assert await service.get(attempt_id, task_id) is None
    first = await service.save(attempt_id, task_id, run_id)
    assert first.source_run_id == run_id and first.criteria.ta.score == 1
    assert first.relevance.short_circuit_applied
    assert first.created_at and first.updated_at
    assert set(first.criteria.model_dump()) == {"ta", "cc", "lr", "gra"}
    assert "overall_band" not in first.model_dump()
    assert await service.get(attempt_id, task_id) == first
    next_run = await WritingAIService(db_session, user_id, settings).create(
        attempt_id, task_id, force=True
    )
    await worker(db_session, settings, RelevanceProvider()).execute(next_run.run_id)
    assert (await service.get(attempt_id, task_id)).source_run_id == run_id  # No auto-overwrite.
    updated = await service.save(attempt_id, task_id, next_run.run_id)
    assert updated.id == first.id and updated.created_at == first.created_at
    assert updated.source_run_id == next_run.run_id and updated.criteria.ta.score == 7
    assert updated.updated_at >= first.updated_at
    async with db_session.begin():
        assert (
            await db_session.scalar(select(func.count()).select_from(WritingAIPracticeFeedback))
            == 1
        )
        assert (await db_session.get(Attempt, attempt_id)).band_score == Decimal(7)
        official = await db_session.scalar(
            select(AttemptWritingScore).where(AttemptWritingScore.attempt_id == attempt_id)
        )
        assert official.ta == official.cc == official.lr == official.gra == 7
        assert official.ta_feedback == "Human feedback stays."
        await db_session.execute(delete(Attempt).where(Attempt.id == attempt_id))
        assert (
            await db_session.scalar(select(func.count()).select_from(WritingAIPracticeFeedback))
            == 0
        )


@pytest.mark.parametrize("change", ["full", "mock", "other_task", "reading", "foreign"])
async def test_only_own_standalone_focused_writing_is_eligible(
    db_session, focused, writing, change
):
    attempt_id, task_id, run_id, user_id = focused
    if change == "full":
        await mutate(
            db_session,
            Attempt,
            attempt_id,
            scope=AttemptScope.FULL_MODULE,
            focused_writing_task_id=None,
        )
    elif change == "mock":
        # The domain normally rejects focused Full Mock attempts; test defence in depth without an invalid FK.
        service = WritingAIPracticeFeedbackService(db_session, user_id)
        async with db_session.begin():
            row = await db_session.get(Attempt, attempt_id)
            row.test_session_id = uuid4()
            with pytest.raises(AppError):
                service.require_focused(row, task_id)
            row.test_session_id = None
        return
    elif change == "other_task":
        task_id = writing[1]
    elif change == "reading":
        # Pure eligibility guard; do not violate the existing DB module/scope check.
        service = WritingAIPracticeFeedbackService(db_session, user_id)
        async with db_session.begin():
            row = await db_session.get(Attempt, attempt_id)
            old = row.module_type
            row.module_type = ModuleType.READING
            with pytest.raises(AppError):
                service.require_focused(row, task_id)
            row.module_type = old
        return
    else:
        user_id = uuid4()
    service = WritingAIPracticeFeedbackService(db_session, user_id)
    for action in (service.get(attempt_id, task_id), service.save(attempt_id, task_id, run_id)):
        with pytest.raises(AppError):
            await action


@pytest.mark.parametrize(
    "change",
    [
        "pending",
        "running",
        "failed",
        "task",
        "requester",
        "attempt",
        "missing",
        "malformed",
        "incomplete",
        "invalid_score",
    ],
)
async def test_only_complete_same_owner_task_attempt_durable_results_can_be_saved(
    db_session, focused, writing, change
):
    attempt_id, task_id, run_id, user_id = focused
    if change in {"pending", "running", "failed"}:
        await mutate(
            db_session, WritingAIGradingRun, run_id, status=WritingAIRunStatus(change.upper())
        )
    elif change == "task":
        await mutate(db_session, WritingAIGradingRun, run_id, writing_task_id=writing[1])
    elif change == "requester":
        await mutate(
            db_session,
            WritingAIGradingRun,
            run_id,
            requested_by_user_id=db_session.info["current_user_id"],
        )
    elif change == "attempt":
        # A real run owned by the same user on another attempt must still be rejected.
        async with db_session.begin():
            original = await db_session.get(Attempt, attempt_id)
            now = datetime.now(UTC)
            other = Attempt(
                user_id=user_id,
                test_version_id=original.test_version_id,
                module_type=ModuleType.WRITING,
                scope=AttemptScope.FOCUSED_UNIT,
                focused_writing_task_id=task_id,
                status=AttemptStatus.SUBMITTED,
                timer_mode=TimerMode.COUNT_UP,
                started_at=now,
                last_active_at=now,
                finished_at=now,
            )
            db_session.add(other)
            await db_session.flush()
            run = await db_session.get(WritingAIGradingRun, run_id)
            run.attempt_id = other.id
    elif change == "missing":
        await mutate(db_session, WritingAIGradingRun, run_id, result_json=None)
    else:
        async with db_session.begin():
            row = await db_session.get(WritingAIGradingRun, run_id)
            value = dict(row.result_json)
            if change == "malformed":
                value["criteria"] = "private invalid data"
            elif change == "incomplete":
                value["criteria"] = {"ta": value["criteria"]["ta"]}
            else:
                value["criteria"] = {
                    **value["criteria"],
                    "ta": {**value["criteria"]["ta"], "score": 1.2},
                }
            row.result_json = value
    with pytest.raises(AppError):
        await WritingAIPracticeFeedbackService(db_session, user_id).save(
            attempt_id, task_id, run_id
        )
    async with db_session.begin():
        assert (
            await db_session.scalar(select(func.count()).select_from(WritingAIPracticeFeedback))
            == 0
        )


async def test_historical_result_without_relevance_can_be_saved(db_session, focused):
    attempt_id, task_id, run_id, user_id = focused
    async with db_session.begin():
        row = await db_session.get(WritingAIGradingRun, run_id)
        row.result_json = {k: v for k, v in row.result_json.items() if k != "relevance"}
    assert (
        await WritingAIPracticeFeedbackService(db_session, user_id).save(
            attempt_id, task_id, run_id
        )
    ).relevance is None


async def test_concurrent_saves_converge_on_one_row(db_session, focused):
    _, _, run_id, _ = focused
    async with db_session.begin():
        run = await db_session.get(WritingAIGradingRun, run_id)
        result_json = run.result_json
    from app.core.database import SessionFactory

    # Independently committed fictional records allow two actual DB connections.
    now = datetime.now(UTC)
    async with SessionFactory() as session, session.begin():
        user = User(
            email=f"snapshot-concurrency-{uuid4()}@example.com",
            display_name="Fictional learner",
            role=UserRole.USER,
            is_active=True,
            email_verified=True,
        )
        test = DomainTest(title="Fictional snapshot concurrency")
        version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED, published_at=now)
        module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
        task = WritingTask(task_number=2, prompt="Discuss fictional parks.", order_index=0)
        test.versions.append(version)
        version.modules.append(module)
        module.writing_tasks.append(task)
        session.add_all([user, test])
        await session.flush()
        attempt = Attempt(
            user_id=user.id,
            test_version_id=version.id,
            module_type=ModuleType.WRITING,
            scope=AttemptScope.FOCUSED_UNIT,
            focused_writing_task_id=task.id,
            status=AttemptStatus.SUBMITTED,
            timer_mode=TimerMode.COUNT_UP,
            started_at=now,
            last_active_at=now,
            finished_at=now,
        )
        session.add(attempt)
        await session.flush()
        own_run = WritingAIGradingRun(
            attempt_id=attempt.id,
            writing_task_id=task.id,
            requested_by_user_id=user.id,
            status=WritingAIRunStatus.COMPLETED,
            provider="fake",
            model="fictional",
            prompt_version="mts-task2-v8",
            input_fingerprint="f" * 64,
            result_json=result_json,
        )
        session.add(own_run)
        await session.flush()
        identities = user.id, test.id, attempt.id, task.id, own_run.id

    owner, test_id, attempt_id, task_id, source_id = identities

    async def save():
        async with SessionFactory() as session:
            return await WritingAIPracticeFeedbackService(session, owner).save(
                attempt_id, task_id, source_id
            )

    try:
        results = await asyncio.gather(save(), save())
        assert results[0].id == results[1].id
        async with SessionFactory() as session, session.begin():
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(WritingAIPracticeFeedback)
                    .where(WritingAIPracticeFeedback.attempt_id == attempt_id)
                )
                == 1
            )
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Attempt).where(Attempt.id == attempt_id))
            await session.execute(delete(DomainTest).where(DomainTest.id == test_id))
            await session.execute(delete(User).where(User.id == owner))


async def test_snapshot_accepts_only_run_id_and_personal_final_save_is_explicit(
    db_session, focused, test_user
):
    attempt_id, task_id, run_id, _ = focused

    async def session_override():
        yield db_session

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: test_user
    path = f"/api/v1/attempts/{attempt_id}/writing/{task_id}/ai-practice-feedback"
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get(path)).json() is None
            for extra in ({"ta_score": 9}, {"feedback": "forged"}, {"criteria": {}}):
                assert (
                    await client.put(path, json={"source_run_id": str(run_id), **extra})
                ).status_code == 422
            response = await client.put(path, json={"source_run_id": str(run_id)})
            assert response.status_code == 200 and response.json()["criteria"]["ta"]["score"] == 1
            assert (await client.get(path)).json() == response.json()
            official = await client.put(
                f"/api/v1/attempts/{attempt_id}/writing-scores/{task_id}",
                json={"ta": 9, "cc": 9, "lr": 9, "gra": 9},
            )
            assert official.status_code == 200
            assert official.json()["tasks"][0]["score"]["ta"] == 9
            assert (await client.get(path)).json() == response.json()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


async def test_relevance_events_and_completed_metadata_are_durable(db_session, focused, settings):
    attempt_id, task_id, run_id, user_id = focused
    run, events = await WritingAIService(db_session, user_id, settings).snapshot(run_id, 0)
    assert run.status == WritingAIRunStatus.COMPLETED and run.result.relevance.short_circuit_applied
    assert run.relevance == run.result.relevance
    gate = [e for e in events if e.event_type.startswith("relevance.")]
    assert [e.event_type for e in gate] == ["relevance.started", "relevance.completed"]
    assert gate[-1].payload.relevance == run.relevance
    _, replay = await WritingAIService(db_session, user_id, settings).snapshot(
        run_id, gate[0].sequence
    )
    assert all(e.sequence > gate[0].sequence for e in replay)
    assert (
        next(e for e in replay if e.event_type == "relevance.completed").payload.relevance
        == run.relevance
    )


async def test_failed_auxiliary_relevance_event_is_not_a_failed_run(db_session, writing, settings):
    attempt_id, _, task_id = writing
    api = WritingAIService(db_session, db_session.info["current_user_id"], settings)
    created = await api.create(attempt_id, task_id, force=False)
    await worker(db_session, settings, RelevanceProvider(failures=3)).execute(created.run_id)
    run, events = await api.snapshot(created.run_id, 0)
    assert run.status == WritingAIRunStatus.COMPLETED and run.result.relevance is None
    assert "relevance.failed" in [e.event_type for e in events]
    assert not run.failures


async def test_partial_relevance_metadata_and_auxiliary_activity_survive_reconnect(
    db_session, writing, settings
):
    from app.schemas.writing_ai import EventPayload, WritingRelevanceResult

    attempt_id, _, task_id = writing
    api = WritingAIService(db_session, db_session.info["current_user_id"], settings)
    created = await api.create(attempt_id, task_id, force=False)
    runner = worker(db_session, settings)
    relevance = WritingRelevanceResult(
        verdict="PARTIALLY_RELEVANT",
        confidence="MEDIUM",
        reason="Có liên hệ một phần với đề.",
        evidence=[],
        short_circuit_applied=False,
    )
    await runner._checkpoint(
        created.run_id, "relevance.started", EventPayload(criterion="ta", stage="relevance")
    )
    partial = await api.get(created.run_id)
    assert partial.activity.phase == "checking_relevance" and partial.result is None
    await runner._checkpoint(
        created.run_id,
        "relevance.completed",
        EventPayload(criterion="ta", stage="relevance", relevance=relevance),
    )
    partial, events = await api.snapshot(created.run_id, 0)
    assert partial.result is None and partial.relevance == relevance
    assert (
        partial.activity.phase == "relevance_checked" and events[-1].payload.relevance == relevance
    )
    await runner._checkpoint(
        created.run_id,
        "relevance.failed",
        EventPayload(criterion="ta", stage="relevance", error_code="AI_RELEVANCE_FAILED"),
    )
    partial = await api.get(created.run_id)
    assert (
        partial.status == WritingAIRunStatus.PENDING
        and partial.activity.phase == "relevance_failed"
    )
    assert not partial.failures
