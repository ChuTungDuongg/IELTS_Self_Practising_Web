"""Forced interleavings on independent PostgreSQL connections; fictional content only."""

import asyncio
from datetime import UTC, datetime, timedelta
from io import BytesIO
from threading import Event as ThreadEvent
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy import delete, select, text, update
from starlette.datastructures import Headers
from test_attempt_response_concurrency import response_context as response_context
from test_writing_ai import ESSAY, FakeProvider

from app.api.v1 import assets
from app.core.config import Settings
from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import Asset, Attempt, AttemptAnswer, User
from app.models import Test as ContentRecord
from app.models import TestModule as ModuleRecord
from app.models import TestSession as MockSession
from app.models import TestVersion as Version
from app.models.enums import (
    AssetType,
    AttemptStatus,
    ModuleType,
    TimerMode,
    UserRole,
    VersionStatus,
)
from app.services.attempts import AttemptService
from app.services.test_sessions import TestSessionService as MockService
from app.storage import LocalAssetStorage


@pytest_asyncio.fixture
async def mock_context(response_context):
    ctx = response_context
    async with ctx.session() as session, session.begin():
        version_id = await session.scalar(
            select(Attempt.test_version_id).where(Attempt.id == ctx.writing_attempt_id)
        )
        parent = MockSession(
            user_id=ctx.owner_id,
            test_version_id=version_id,
            module_order_json=["LISTENING", "READING", "WRITING"],
            started_at=datetime.now(UTC),
        )
        session.add(parent)
        await session.flush()
        parent_id = parent.id
        await session.execute(
            update(Attempt)
            .where(Attempt.id.in_([ctx.reading_attempt_id, ctx.listening_attempt_id]))
            .values(test_session_id=parent_id, status=AttemptStatus.SUBMITTED)
        )
        await session.execute(
            update(Attempt)
            .where(Attempt.id == ctx.writing_attempt_id)
            .values(
                test_session_id=parent_id,
                timer_mode=TimerMode.COUNTDOWN,
                timer_limit_seconds=1,
                started_at=datetime.now(UTC) - timedelta(seconds=10),
            )
        )
    try:
        yield ctx, parent_id
    finally:
        async with ctx.session() as session, session.begin():
            await session.execute(delete(Attempt).where(Attempt.test_session_id == parent_id))
            await session.execute(delete(MockSession).where(MockSession.id == parent_id))


def locked_entity(statement):
    if getattr(statement, "_for_update_arg", None) is None:
        return None
    return statement.column_descriptions[0].get("entity")


@pytest.mark.integration
@pytest.mark.parametrize("operation", ["get", "advance", "delete"])
async def test_mock_timeout_submit_and_session_operations_have_stable_lock_order(
    mock_context, monkeypatch, operation
):
    ctx, parent_id = mock_context
    first_lock = asyncio.Event()
    parent_acquired = asyncio.Event()
    poll_started = asyncio.Event()
    release = asyncio.Event()
    async with ctx.session() as writer, ctx.session() as poller, ctx.session() as observer:
        poller_pid = None
        writer_scalar, poller_scalar = writer.scalar, poller.scalar

        async def hold_first(statement, *args, **kwargs):
            result = await writer_scalar(statement, *args, **kwargs)
            if locked_entity(statement) in {Attempt, MockSession} and not first_lock.is_set():
                first_lock.set()
                await release.wait()
            return result

        async def observe_parent(statement, *args, **kwargs):
            nonlocal poller_pid
            parent_lock = locked_entity(statement) is MockSession
            if parent_lock:
                poller_pid = await poller_scalar(text("select pg_backend_pid()"))
                poll_started.set()
            result = await poller_scalar(statement, *args, **kwargs)
            if parent_lock:
                parent_acquired.set()
            return result

        monkeypatch.setattr(writer, "scalar", hold_first)
        monkeypatch.setattr(poller, "scalar", observe_parent)
        jobs = [
            asyncio.create_task(AttemptService(writer, ctx.owner_id).submit(ctx.writing_attempt_id))
        ]
        try:
            await asyncio.wait_for(first_lock.wait(), 5)
            jobs.append(
                asyncio.create_task(
                    getattr(MockService(poller, ctx.owner_id), operation)(parent_id)
                )
            )
            await asyncio.wait_for(poll_started.wait(), 5)

            async def parent_is_acquired_or_blocked():
                # Observe the actual PostgreSQL lock wait, not a scheduling sleep.
                while not parent_acquired.is_set():
                    blocked = await observer.scalar(
                        text("select cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": poller_pid}
                    )
                    if blocked:
                        return

            await asyncio.wait_for(parent_is_acquired_or_blocked(), 5)
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*jobs), 8)
            assert results[0].status == AttemptStatus.AUTO_SUBMITTED
        finally:
            release.set()
            for job in jobs:
                if not job.done():
                    job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)


@pytest_asyncio.fixture
async def upload_context(response_context, tmp_path, monkeypatch):
    ctx = response_context
    async with ctx.session() as session, session.begin():
        version = Version(test_id=ctx.test_id, version_number=2, status=VersionStatus.DRAFT)
        session.add(version)
        await session.flush()
        version_id = version.id
    monkeypatch.setattr(
        assets,
        "get_settings",
        lambda: SimpleNamespace(
            resolved_storage_root=tmp_path,
            max_image_upload_mb=1,
            max_audio_upload_mb=1,
        ),
    )
    actor = User(id=ctx.owner_id, role=UserRole.ADMIN, is_active=True)
    # AccessPolicy refreshes the actor from PostgreSQL before authoring.
    async with ctx.session() as session, session.begin():
        await session.execute(
            update(User).where(User.id == ctx.owner_id).values(role=UserRole.ADMIN)
        )
    yield ctx, version_id, actor, tmp_path


def image_upload(content=b"fictional-image"):
    return UploadFile(
        BytesIO(content), filename="fictional.png", headers=Headers({"content-type": "image/png"})
    )


@pytest.mark.integration
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_asset_file_is_compensated_when_database_flush_fails(
    upload_context, monkeypatch, failure
):
    ctx, version_id, actor, root = upload_context
    async with ctx.session() as session:

        async def fail_flush(*args, **kwargs):
            raise failure("injected failure after file creation")

        monkeypatch.setattr(session, "flush", fail_flush)
        with pytest.raises(failure):
            await assets._upload(
                version_id=version_id,
                upload=image_upload(),
                category="images",
                asset_type=AssetType.QUESTION_IMAGE,
                session=session,
                actor=actor,
            )
    assert not [path for path in root.rglob("*") if path.is_file()]
    async with ctx.session() as verify:
        assert (
            await verify.scalar(select(Asset.id).where(Asset.test_version_id == version_id)) is None
        )


@pytest.mark.integration
async def test_asset_upload_never_uses_an_unbounded_read(upload_context, monkeypatch):
    ctx, version_id, actor, root = upload_context
    upload = image_upload()
    read = upload.read

    async def bounded_read(size=-1):
        assert 0 < size <= 1024 * 1024, "Unbounded read allocates the whole user upload"
        return await read(size)

    monkeypatch.setattr(upload, "read", bounded_read)
    async with ctx.session() as session:
        result = await assets._upload(
            version_id=version_id,
            upload=upload,
            category="images",
            asset_type=AssetType.QUESTION_IMAGE,
            session=session,
            actor=actor,
        )
    assert (root / result.relative_path).read_bytes() == b"fictional-image"


@pytest.mark.integration
async def test_oversized_upload_reads_only_limit_plus_one_and_leaves_no_file(upload_context):
    ctx, version_id, actor, root = upload_context

    class BoundedStream(BytesIO):
        bytes_read = 0

        def read(self, size=-1):
            assert 0 < size <= 1024 * 1024
            result = super().read(size)
            self.bytes_read += len(result)
            return result

    stream = BoundedStream(b"x" * (2 * 1024 * 1024))
    upload = UploadFile(
        stream, filename="fictional.png", headers=Headers({"content-type": "image/png"})
    )
    async with ctx.session() as session:
        with pytest.raises(AppError) as error:
            await assets._upload(
                version_id=version_id,
                upload=upload,
                category="images",
                asset_type=AssetType.QUESTION_IMAGE,
                session=session,
                actor=actor,
            )
    assert error.value.code == "ASSET_UPLOAD_INVALID"
    assert stream.bytes_read == 1024 * 1024 + 1
    assert not [path for path in root.rglob("*") if path.is_file()]


@pytest.mark.integration
async def test_cancellation_joins_file_writer_before_compensation(upload_context, monkeypatch):
    ctx, version_id, actor, root = upload_context
    written, release = asyncio.Event(), ThreadEvent()
    loop = asyncio.get_running_loop()
    original = LocalAssetStorage.store_stream

    def hold_file_writer(storage, **kwargs):
        stored = original(storage, **kwargs)
        loop.call_soon_threadsafe(written.set)
        assert release.wait(10)
        return stored

    monkeypatch.setattr(LocalAssetStorage, "store_stream", hold_file_writer)
    async with ctx.session() as session:
        job = asyncio.create_task(
            assets._upload(
                version_id=version_id,
                upload=image_upload(),
                category="images",
                asset_type=AssetType.QUESTION_IMAGE,
                session=session,
                actor=actor,
            )
        )
        try:
            await asyncio.wait_for(written.wait(), 5)
            job.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(job, 5)
        finally:
            release.set()
            await asyncio.gather(job, return_exceptions=True)
    assert not [path for path in root.rglob("*") if path.is_file()]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("transition", "error_code"),
    [
        ("publish", "TEST_VERSION_IMMUTABLE"),
        ("archive", "TEST_ARCHIVED"),
        ("delete", "TEST_VERSION_NOT_FOUND"),
    ],
)
async def test_staged_upload_rechecks_committed_draft_transition(
    upload_context, monkeypatch, transition, error_code
):
    ctx, version_id, actor, root = upload_context
    written, release = asyncio.Event(), ThreadEvent()
    loop = asyncio.get_running_loop()
    original = LocalAssetStorage.store_stream

    def hold_file_writer(storage, **kwargs):
        stored = original(storage, **kwargs)
        loop.call_soon_threadsafe(written.set)
        assert release.wait(10)
        return stored

    async def commit_transition():
        async with ctx.session() as contender, contender.begin():
            # Model the competing lifecycle commit at its database boundary.
            # It must finish while staging is paused, without authoring locks.
            if transition == "publish":
                await contender.execute(
                    update(Version)
                    .where(
                        Version.test_id == ctx.test_id,
                        Version.status == VersionStatus.PUBLISHED,
                    )
                    .values(status=VersionStatus.ARCHIVED)
                )
                await contender.execute(
                    update(Version)
                    .where(Version.id == version_id)
                    .values(status=VersionStatus.PUBLISHED)
                )
            elif transition == "archive":
                await contender.execute(
                    update(ContentRecord)
                    .where(ContentRecord.id == ctx.test_id)
                    .values(archived_at=datetime.now(UTC))
                )
            else:
                await contender.execute(delete(Version).where(Version.id == version_id))

    monkeypatch.setattr(LocalAssetStorage, "store_stream", hold_file_writer)
    async with ctx.session() as session:
        job = asyncio.create_task(
            assets._upload(
                version_id=version_id,
                upload=image_upload(),
                category="images",
                asset_type=AssetType.QUESTION_IMAGE,
                session=session,
                actor=actor,
            )
        )
        try:
            await asyncio.wait_for(written.wait(), 5)
            await asyncio.wait_for(commit_transition(), 5)
            release.set()
            with pytest.raises(AppError) as error:
                await asyncio.wait_for(job, 5)
            assert error.value.code == error_code
        finally:
            release.set()
            if not job.done():
                job.cancel()
            await asyncio.gather(job, return_exceptions=True)
    assert not [path for path in root.rglob("*") if path.is_file()]
    async with ctx.session() as verify:
        assert (
            await verify.scalar(select(Asset.id).where(Asset.test_version_id == version_id)) is None
        )


@pytest.mark.integration
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_lost_commit_acknowledgement_never_deletes_committed_asset(
    upload_context, monkeypatch, failure
):
    ctx, version_id, actor, root = upload_context
    async with ctx.session() as session:
        begin = session.begin

        class LostAcknowledgement:
            async def __aenter__(self):
                self.transaction = begin()
                return await self.transaction.__aenter__()

            async def __aexit__(self, *args):
                committing_asset = any(
                    isinstance(row, Asset) for row in session.identity_map.values()
                )
                await self.transaction.__aexit__(*args)
                if committing_asset:
                    raise failure("injected lost commit acknowledgement")

        monkeypatch.setattr(session, "begin", LostAcknowledgement)
        with pytest.raises(failure):
            await assets._upload(
                version_id=version_id,
                upload=image_upload(),
                category="images",
                asset_type=AssetType.QUESTION_IMAGE,
                session=session,
                actor=actor,
            )
    async with ctx.session() as verify:
        asset = await verify.scalar(select(Asset).where(Asset.test_version_id == version_id))
        assert asset is not None
        assert (root / asset.relative_path).read_bytes() == b"fictional-image"


@pytest.mark.integration
async def test_simultaneous_mock_advances_create_only_one_next_module(mock_context, monkeypatch):
    ctx, parent_id = mock_context
    async with ctx.session() as setup, setup.begin():
        version_id = await setup.scalar(
            select(Attempt.test_version_id).where(Attempt.id == ctx.writing_attempt_id)
        )
        await setup.execute(
            update(ModuleRecord)
            .where(ModuleRecord.test_version_id == version_id)
            .values(recommended_duration_seconds=3600)
        )
        await setup.execute(delete(Attempt).where(Attempt.id == ctx.writing_attempt_id))
    acquired, waiting, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async with ctx.session() as first, ctx.session() as second:
        first_scalar, second_scalar = first.scalar, second.scalar

        async def hold(statement, *args, **kwargs):
            result = await first_scalar(statement, *args, **kwargs)
            if locked_entity(statement) is MockSession:
                acquired.set()
                await release.wait()
            return result

        async def observe(statement, *args, **kwargs):
            if locked_entity(statement) is MockSession:
                waiting.set()
            return await second_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(first, "scalar", hold)
        monkeypatch.setattr(second, "scalar", observe)
        jobs = [asyncio.create_task(MockService(first, ctx.owner_id).advance(parent_id))]
        try:
            await asyncio.wait_for(acquired.wait(), 5)
            jobs.append(asyncio.create_task(MockService(second, ctx.owner_id).advance(parent_id)))
            await asyncio.wait_for(waiting.wait(), 5)
            assert not jobs[1].done()
            release.set()
            result = await asyncio.wait_for(jobs[0], 5)
            assert result.current_attempt.module == ModuleType.WRITING
            with pytest.raises(AppError) as error:
                await asyncio.wait_for(jobs[1], 5)
            assert error.value.code == "FULL_MOCK_MODULE_ACTIVE"
        finally:
            release.set()
            for job in jobs:
                if not job.done():
                    job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
    async with ctx.session() as verify:
        attempts = list(
            await verify.scalars(select(Attempt).where(Attempt.test_session_id == parent_id))
        )
        assert sorted(a.module_type.value for a in attempts) == ["LISTENING", "READING", "WRITING"]


@pytest.mark.integration
async def test_unrelated_learner_can_save_and_submit_while_an_attempt_is_locked(response_context):
    ctx = response_context
    async with ctx.session() as setup, setup.begin():
        original = await setup.get(Attempt, ctx.reading_attempt_id)
        other = Attempt(
            user_id=ctx.other_id,
            test_version_id=original.test_version_id,
            module_type=ModuleType.READING,
            timer_mode=TimerMode.COUNT_UP,
            started_at=datetime.now(UTC),
            last_active_at=datetime.now(UTC),
            status=AttemptStatus.IN_PROGRESS,
        )
        setup.add(other)
        await setup.flush()
        other_id = other.id
    try:
        async with ctx.session() as locked, ctx.session() as independent:
            async with locked.begin():
                await locked.scalar(
                    select(Attempt).where(Attempt.id == ctx.reading_attempt_id).with_for_update()
                )
                saved = await asyncio.wait_for(
                    AttemptService(independent, ctx.other_id).save_answer(
                        other_id,
                        ctx.reading_questions[0],
                        "TRUE",
                        0,
                    ),
                    5,
                )
                assert saved.revision == 1
                submitted = await asyncio.wait_for(
                    AttemptService(independent, ctx.other_id).submit(other_id), 5
                )
                assert submitted.status == AttemptStatus.SUBMITTED
        async with ctx.session() as verify:
            assert (
                await verify.scalar(
                    select(AttemptAnswer.id).where(
                        AttemptAnswer.attempt_id == ctx.reading_attempt_id
                    )
                )
                is None
            )
    finally:
        async with ctx.session() as cleanup, cleanup.begin():
            await cleanup.execute(delete(Attempt).where(Attempt.id == other_id))


@pytest.mark.integration
@pytest.mark.parametrize("save_first", [True, False])
async def test_inflight_autosave_and_submit_score_only_committed_answers(
    response_context, monkeypatch, save_first
):
    ctx = response_context
    acquired, waiting, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async with ctx.session() as first, ctx.session() as second:
        first_scalar, second_scalar = first.scalar, second.scalar

        async def hold(statement, *args, **kwargs):
            result = await first_scalar(statement, *args, **kwargs)
            if locked_entity(statement) is Attempt:
                acquired.set()
                await release.wait()
            return result

        async def observe(statement, *args, **kwargs):
            if locked_entity(statement) is Attempt:
                waiting.set()
            return await second_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(first, "scalar", hold)
        monkeypatch.setattr(second, "scalar", observe)

        async def invoke(session, save):
            service = AttemptService(session, ctx.owner_id)
            if save:
                return await service.save_answer(
                    ctx.reading_attempt_id, ctx.reading_questions[0], "TRUE", 0
                )
            return await service.submit(ctx.reading_attempt_id)

        jobs = [asyncio.create_task(invoke(first, save_first))]
        try:
            await asyncio.wait_for(acquired.wait(), 5)
            jobs.append(asyncio.create_task(invoke(second, not save_first)))
            await asyncio.wait_for(waiting.wait(), 5)
            assert not jobs[1].done()
            release.set()
            await asyncio.wait_for(jobs[0], 5)
            if save_first:
                assert (await asyncio.wait_for(jobs[1], 5)).status == AttemptStatus.SUBMITTED
            else:
                with pytest.raises(AppError) as error:
                    await asyncio.wait_for(jobs[1], 5)
                assert error.value.code == "ATTEMPT_FINALIZED"
        finally:
            release.set()
            for job in jobs:
                if not job.done():
                    job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
    async with ctx.session() as verify:
        attempt = await verify.get(Attempt, ctx.reading_attempt_id)
        assert attempt.status == AttemptStatus.SUBMITTED
        assert attempt.raw_score == (1 if save_first else 0)
        answer = await verify.scalar(
            select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id)
        )
        assert (answer.revision if answer else 0) == (1 if save_first else 0)


@pytest.mark.integration
async def test_save_waiting_for_lock_rechecks_server_deadline(response_context, monkeypatch):
    ctx = response_context
    now = datetime.now(UTC)
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))
    async with ctx.session() as setup, setup.begin():
        await setup.execute(
            update(Attempt)
            .where(Attempt.id == ctx.reading_attempt_id)
            .values(
                timer_mode=TimerMode.COUNTDOWN,
                timer_limit_seconds=2,
                started_at=now,
            )
        )
    waiting = asyncio.Event()
    async with ctx.session() as holder, ctx.session() as saver:
        scalar = saver.scalar

        async def observe(statement, *args, **kwargs):
            if locked_entity(statement) is Attempt:
                waiting.set()
            return await scalar(statement, *args, **kwargs)

        monkeypatch.setattr(saver, "scalar", observe)
        async with holder.begin():
            await holder.scalar(
                select(Attempt).where(Attempt.id == ctx.reading_attempt_id).with_for_update()
            )
            job = asyncio.create_task(
                AttemptService(saver, ctx.owner_id).save_answer(
                    ctx.reading_attempt_id,
                    ctx.reading_questions[0],
                    "TRUE",
                    0,
                )
            )
            await asyncio.wait_for(waiting.wait(), 5)
            assert not job.done()
            now += timedelta(seconds=3)
        try:
            with pytest.raises(AppError) as error:
                await asyncio.wait_for(job, 5)
            assert error.value.code == "ATTEMPT_EXPIRED"
        finally:
            if not job.done():
                job.cancel()
            await asyncio.gather(job, return_exceptions=True)
    async with ctx.session() as verifier:
        finalized = await AttemptService(verifier, ctx.owner_id).submit(ctx.reading_attempt_id)
        assert finalized.status == AttemptStatus.AUTO_SUBMITTED
    async with ctx.session() as verifier:
        assert (
            await verifier.scalar(
                select(AttemptAnswer.id).where(AttemptAnswer.attempt_id == ctx.reading_attempt_id)
            )
            is None
        )


@pytest.mark.integration
@pytest.mark.parametrize("cancel", [False, True])
async def test_writing_workers_claim_once_and_obey_durable_cancellation(response_context, cancel):
    from app.models import WritingAIGradingEvent, WritingAIGradingRun
    from app.models.enums import WritingAIRunStatus
    from app.services.writing_ai import CANCELLATION_CODE, WritingAIService
    from app.services.writing_ai_worker import WritingAIWorker

    ctx = response_context
    task_id = ctx.writing_tasks[1]
    settings = Settings(
        _env_file=None, ai_writing_enabled=True, ai_writing_vllm_base_url="https://llm.example/v1"
    )
    async with ctx.session() as setup:
        await AttemptService(setup, ctx.owner_id).save_writing_response(
            ctx.writing_attempt_id, task_id, ESSAY, 0
        )
        await AttemptService(setup, ctx.owner_id).submit(ctx.writing_attempt_id)

    async def create(force=False):
        async with ctx.session() as session:
            return await WritingAIService(session, ctx.owner_id, settings).create(
                ctx.writing_attempt_id, task_id, force=force
            )

    first, second = await asyncio.gather(create(), create())
    assert first.run_id == second.run_id
    assert first.existing_active != second.existing_active
    entered, release = asyncio.Event(), asyncio.Event()

    class BlockedProvider(FakeProvider):
        ready_calls = 0

        async def ensure_ready(self):
            self.ready_calls += 1
            entered.set()
            await release.wait()

    provider = BlockedProvider()
    workers = [WritingAIWorker(ctx.factory, settings, provider) for _ in range(2)]
    job = asyncio.create_task(workers[0].execute(first.run_id))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        await asyncio.wait_for(workers[1].execute(first.run_id), 5)
        assert provider.ready_calls == 1
        if cancel:
            async with ctx.session() as session:
                stopped = await WritingAIService(session, ctx.owner_id, settings).cancel(
                    first.run_id
                )
                assert stopped.status == WritingAIRunStatus.FAILED
        release.set()
        await asyncio.wait_for(job, 15)
        async with ctx.session() as verify:
            run = await verify.get(WritingAIGradingRun, first.run_id)
            assert run.status == (
                WritingAIRunStatus.FAILED if cancel else WritingAIRunStatus.COMPLETED
            )
            events = list(
                await verify.scalars(
                    select(WritingAIGradingEvent)
                    .where(WritingAIGradingEvent.run_id == run.id)
                    .order_by(WritingAIGradingEvent.sequence)
                )
            )
            assert [event.sequence for event in events] == list(range(1, len(events) + 1))
            assert sum(event.event_type in {"run.completed", "run.failed"} for event in events) == 1
            if cancel:
                assert not provider.calls and run.error_code == CANCELLATION_CODE
        if not cancel:
            assert (await create()).cache_hit
            assert (await create(force=True)).run_id != first.run_id
    finally:
        release.set()
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


@pytest.mark.integration
async def test_independent_mock_sessions_do_not_share_lifecycle_locks(mock_context):
    ctx, parent_id = mock_context
    async with ctx.session() as setup, setup.begin():
        version_id = await setup.scalar(
            select(Attempt.test_version_id).where(Attempt.id == ctx.writing_attempt_id)
        )
        other = MockSession(
            user_id=ctx.other_id, test_version_id=version_id, started_at=datetime.now(UTC)
        )
        setup.add(other)
        await setup.flush()
        other_id = other.id
        setup.add(
            Attempt(
                user_id=ctx.other_id,
                test_version_id=version_id,
                test_session_id=other_id,
                module_type=ModuleType.LISTENING,
                timer_mode=TimerMode.COUNT_UP,
                status=AttemptStatus.IN_PROGRESS,
                started_at=datetime.now(UTC),
                last_active_at=datetime.now(UTC),
            )
        )
    try:
        async with ctx.session() as holder, ctx.session() as independent:
            async with holder.begin():
                await holder.scalar(
                    select(MockSession).where(MockSession.id == parent_id).with_for_update()
                )
                response = await asyncio.wait_for(
                    MockService(independent, ctx.other_id).get(other_id), 5
                )
                assert response.current_attempt.module == ModuleType.LISTENING
    finally:
        async with ctx.session() as cleanup, cleanup.begin():
            await cleanup.execute(delete(Attempt).where(Attempt.test_session_id == other_id))
            await cleanup.execute(delete(MockSession).where(MockSession.id == other_id))


@pytest.mark.integration
async def test_bounded_eight_connection_smoke_keeps_attempts_isolated(response_context):
    from statistics import median
    from time import perf_counter

    ctx = response_context
    ids = []
    async with ctx.session() as setup, setup.begin():
        version_id = await setup.scalar(
            select(Attempt.test_version_id).where(Attempt.id == ctx.reading_attempt_id)
        )
        for index in range(8):
            owner = ctx.owner_id if index % 2 else ctx.other_id
            attempt = Attempt(
                user_id=owner,
                test_version_id=version_id,
                module_type=ModuleType.READING,
                timer_mode=TimerMode.COUNT_UP,
                status=AttemptStatus.IN_PROGRESS,
                started_at=datetime.now(UTC),
                last_active_at=datetime.now(UTC),
            )
            setup.add(attempt)
            await setup.flush()
            ids.append((attempt.id, owner))
    barrier = asyncio.Barrier(8)
    pids, latencies = set(), []

    async def request(aid, owner):
        async with ctx.session() as session:
            scalar = session.scalar
            entered = False

            async def synchronized_lock(statement, *args, **kwargs):
                nonlocal entered
                result = await scalar(statement, *args, **kwargs)
                if locked_entity(statement) is Attempt and not entered:
                    entered = True
                    pids.add(await scalar(text("select pg_backend_pid()")))
                    await barrier.wait()
                return result

            session.scalar = synchronized_lock
            start = perf_counter()
            service = AttemptService(session, owner)
            saved = await service.save_answer(aid, ctx.reading_questions[0], "TRUE", 0)
            submitted = await service.submit(aid)
            latencies.append((perf_counter() - start) * 1000)
            assert saved.revision == 1 and submitted.status == AttemptStatus.SUBMITTED

    try:
        await asyncio.wait_for(asyncio.gather(*(request(*row) for row in ids)), 20)
        assert len(pids) == 8
        async with ctx.session() as verify:
            rows = list(
                await verify.scalars(select(Attempt).where(Attempt.id.in_([aid for aid, _ in ids])))
            )
            assert len(rows) == 8 and all(row.raw_score == 1 for row in rows)
        print(
            f"Eight-connection smoke: median={median(latencies):.1f}ms max={max(latencies):.1f}ms, independent PostgreSQL connections={len(pids)}"
        )
    finally:
        async with ctx.session() as cleanup, cleanup.begin():
            await cleanup.execute(delete(Attempt).where(Attempt.id.in_([aid for aid, _ in ids])))
