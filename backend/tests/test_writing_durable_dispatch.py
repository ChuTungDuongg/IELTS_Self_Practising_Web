"""Durable queue/lease boundaries, using fictional content and fake providers only."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_writing_ai import ESSAY, FakeProvider

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.models import (
    Attempt,
    AttemptWritingResponse,
    User,
    WritingAIGradingEvent,
    WritingAIGradingRun,
    WritingTask,
)
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import (
    AttemptStatus,
    ModuleType,
    TimerMode,
    UserRole,
    VersionStatus,
    WritingAIRunStatus,
)
from app.repositories.writing_ai import WritingAIRepository
from app.schemas.writing_ai import CriterionResult, EventPayload
from app.services.writing_ai import CANCELLATION_CODE, WritingAIService
from app.services.writing_ai_worker import (
    RunStopped,
    WritingAIWorker,
    _tasks,
    stop_writing_ai_workers,
)
from testsupport.test_database import validate_test_database_url


async def test_launch_is_a_hint_and_does_not_allocate_a_task_for_each_queued_run():
    # Removing bounded dispatch must not turn a burst of persisted queue entries
    # back into an unbounded set of in-memory tasks waiting for capacity.
    worker = WritingAIWorker(None, Settings(_env_file=None))
    before = set(_tasks)
    try:
        for _ in range(1000):
            worker.launch(uuid4())
        assert set(_tasks) == before
    finally:
        jobs = [task for key, task in _tasks.items() if key not in before]
        for task in jobs:
            task.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)


async def test_disabled_replica_does_not_consume_another_replicas_writing_queue():
    worker = WritingAIWorker(None, Settings(_env_file=None, ai_writing_enabled=False))
    try:
        worker.start()
        assert worker.consumers == [] and worker.scanner is None
    finally:
        await stop_writing_ai_workers()


@pytest_asyncio.fixture
async def durable_queue():
    """Committed fixtures and independent connections, never a shared savepoint."""
    url = os.environ.get("P2_TEST_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires an explicitly provisioned PostgreSQL test database")
    validate_test_database_url(url, get_settings().database_url)
    engine = create_async_engine(url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_vllm_base_url="https://fictional.invalid/v1",
        ai_writing_worker_poll_seconds=0.02,
        ai_writing_lease_seconds=10,
    )
    now = datetime.now(UTC)
    users = [
        User(
            email=f"durable-{uuid4()}@example.test",
            display_name="Fictional",
            role=UserRole.USER,
            is_active=True,
            email_verified=True,
        )
        for _ in range(2)
    ]
    test = DomainTest(title=f"Fictional durable queue {uuid4()}")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED, published_at=now)
    module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
    task = WritingTask(task_number=2, prompt="Discuss fictional city parks.", order_index=0)
    test.versions.append(version)
    version.modules.append(module)
    module.writing_tasks.append(task)
    async with sessions() as session, session.begin():
        session.add_all([test, *users])
        await session.flush()
        attempts = [
            Attempt(
                user_id=user.id,
                test_version_id=version.id,
                module_type=ModuleType.WRITING,
                status=AttemptStatus.SUBMITTED,
                timer_mode=TimerMode.COUNT_UP,
                started_at=now,
                last_active_at=now,
                finished_at=now,
            )
            for user in users
        ]
        session.add_all(attempts)
        await session.flush()
        session.add_all(
            [
                AttemptWritingResponse(
                    attempt_id=attempt.id, writing_task_id=task.id, content=ESSAY, word_count=12
                )
                for attempt in attempts
            ]
        )

    async def create(index=0, *, force=False):
        async with sessions() as session:
            return await WritingAIService(session, users[index].id, settings).create(
                attempts[index].id, task.id, force=force
            )

    async def get(run_id, index=0):
        async with sessions() as session:
            return await WritingAIService(session, users[index].id, settings).get(run_id)

    try:
        yield SimpleNamespace(
            sessions=sessions,
            settings=settings,
            users=users,
            attempts=attempts,
            task=task,
            create=create,
            get=get,
        )
    finally:
        await stop_writing_ai_workers()
        async with sessions() as session, session.begin():
            await session.execute(delete(Attempt).where(Attempt.id.in_([a.id for a in attempts])))
            await session.execute(delete(DomainTest).where(DomainTest.id == test.id))
            await session.execute(delete(User).where(User.id.in_([u.id for u in users])))
        await engine.dispose()


@pytest.mark.integration
async def test_queue_admission_serializes_different_users_and_dedup_still_wins(durable_queue):
    q = durable_queue
    q.settings.ai_writing_max_pending_runs = 1
    results = await asyncio.gather(q.create(0), q.create(1), return_exceptions=True)
    accepted = [item for item in results if not isinstance(item, Exception)]
    rejected = [item for item in results if isinstance(item, AppError)]
    assert len(accepted) == len(rejected) == 1
    assert rejected[0].code == "AI_WRITING_QUEUE_FULL" and rejected[0].status_code == 503
    owner = next(i for i, result in enumerate(results) if not isinstance(result, Exception))
    duplicate = await q.create(owner)
    assert duplicate.run_id == accepted[0].run_id and duplicate.existing_active
    async with q.sessions() as session:
        with pytest.raises(AppError) as error:
            await WritingAIService(session, q.users[1 - owner].id, q.settings).cancel(
                accepted[0].run_id
            )
        assert error.value.code == "AI_RUN_NOT_FOUND"


@pytest.mark.integration
async def test_duplicate_dispatch_uses_independent_connections_and_one_owner(durable_queue):
    q = durable_queue
    created = await q.create()
    providers = [FakeProvider(), FakeProvider()]
    workers = [WritingAIWorker(q.sessions, q.settings, provider) for provider in providers]
    await asyncio.gather(*(worker.execute(created.run_id) for worker in workers))
    assert sorted(len(provider.calls) for provider in providers) == [0, 13]
    assert (await q.get(created.run_id)).status == WritingAIRunStatus.COMPLETED
    async with q.sessions() as session:
        events = list(
            await session.scalars(
                select(WritingAIGradingEvent)
                .where(WritingAIGradingEvent.run_id == created.run_id)
                .order_by(WritingAIGradingEvent.sequence)
            )
        )
        assert sum(event.event_type == "run.started" for event in events) == 1
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))


class BlockedProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.waiting = asyncio.Event()
        self.interrupted = asyncio.Event()

    async def ensure_ready(self):
        self.waiting.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.interrupted.set()
            raise


@pytest.mark.integration
async def test_global_running_cap_and_remote_cancel_interrupt_blocked_provider(durable_queue):
    q = durable_queue
    q.settings.ai_writing_max_running_runs = 1
    first, second = await q.create(0), await q.create(1)
    provider = BlockedProvider()
    runner = WritingAIWorker(q.sessions, q.settings, provider)
    job = asyncio.create_task(runner.execute(first.run_id))
    try:
        await asyncio.wait_for(provider.waiting.wait(), 3)
        other_provider = FakeProvider()
        assert (
            await WritingAIWorker(q.sessions, q.settings, other_provider).execute(second.run_id)
            is False
        )
        assert other_provider.calls == []
        async with q.sessions() as session:
            await WritingAIService(session, q.users[0].id, q.settings).cancel(first.run_id)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(job, 6)
        assert provider.interrupted.is_set()
        assert (await q.get(first.run_id)).error_code == CANCELLATION_CODE
        await WritingAIWorker(q.sessions, q.settings, other_provider).execute(second.run_id)
        assert (await q.get(second.run_id, 1)).status == WritingAIRunStatus.COMPLETED
    finally:
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)


@pytest.mark.integration
async def test_periodic_scan_dispatches_commit_without_launch_and_bounds_consumers(durable_queue):
    q = durable_queue
    q.settings.ai_writing_worker_concurrency = 1
    first, second = await q.create(0), await q.create(1)
    provider = BlockedProvider()
    runner = WritingAIWorker(q.sessions, q.settings, provider)
    runner.start()  # Deliberately never call launch: simulate crash after commit.
    await asyncio.wait_for(provider.waiting.wait(), 3)
    async with q.sessions() as session:
        rows = list(
            await session.scalars(
                select(WritingAIGradingRun).where(
                    WritingAIGradingRun.id.in_([first.run_id, second.run_id])
                )
            )
        )
        assert sorted(run.status.value for run in rows) == ["PENDING", "RUNNING"]
    assert len(runner.consumers) == len(_tasks) == 1
    assert not runner.consumers[0].done()


@pytest.mark.integration
async def test_expired_owner_cannot_write_and_scanner_preserves_partial_checkpoint(durable_queue):
    q = durable_queue
    created = await q.create()
    runner = WritingAIWorker(q.sessions, q.settings, FakeProvider())
    async with q.sessions() as session, session.begin():
        run = await WritingAIRepository(session).claim(
            run_id=created.run_id, lease_seconds=10, max_running=4
        )
        token = run.lease_token
    result = CriterionResult(
        score=6, feedback="Fictional saved feedback", strengths=[], improvements=[], evidence=[]
    )
    await runner._checkpoint(
        created.run_id,
        "criterion.completed",
        EventPayload(criterion="ta", result=result),
        token=token,
    )
    with pytest.raises(RunStopped):
        await runner._checkpoint(created.run_id, "heartbeat", EventPayload(), token=uuid4())
    # A late owner cannot overwrite either a result or a failure while another
    # valid lease exists. None proposed output is intentionally inaccessible.
    await runner._complete(created.run_id, None, None, uuid4())
    await runner._fail(created.run_id, "STALE_OWNER", "Fictional stale worker", None, uuid4())
    assert (await q.get(created.run_id)).status == WritingAIRunStatus.RUNNING
    async with q.sessions() as session, session.begin():
        run = await WritingAIRepository(session).run(created.run_id, lock=True)
        run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(RunStopped):
        await runner._checkpoint(created.run_id, "heartbeat", EventPayload(), token=token)
    await runner._complete(created.run_id, None, None, token)
    assert (await q.get(created.run_id)).status == WritingAIRunStatus.RUNNING
    await runner.recover()
    saved = await q.get(created.run_id)
    assert saved.status == WritingAIRunStatus.FAILED and saved.error_code == "RUN_INTERRUPTED"
    assert saved.progress["ta"] == result
    assert await runner.execute(created.run_id) is False
    assert (await q.create()).run_id != created.run_id
