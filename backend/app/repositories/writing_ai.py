from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Attempt,
    AttemptWritingResponse,
    TestModule,
    WritingAIGradingEvent,
    WritingAIGradingRun,
    WritingTask,
)
from app.models.enums import ModuleType, WritingAIRunStatus
from app.schemas.writing_ai import EventPayload, EventType

ACTIVE = (WritingAIRunStatus.PENDING, WritingAIRunStatus.RUNNING)
# Shared only by short Writing queue admission/claim transactions, never inference.
DISPATCH_LOCK = 217538663175


class WritingAIRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dispatch_lock(self) -> None:
        await self.session.execute(select(func.pg_advisory_xact_lock(DISPATCH_LOCK)))

    async def count_status(self, status: WritingAIRunStatus) -> int:
        return await self.session.scalar(
            select(func.count())
            .select_from(WritingAIGradingRun)
            .where(WritingAIGradingRun.status == status)
        )

    async def claim(self, *, lease_seconds: int, max_running: int, run_id: UUID | None = None):
        # Admission and claim use the same DB lock across all replicas. The
        # provider is always called after this short transaction commits.
        await self.dispatch_lock()
        if await self.count_status(WritingAIRunStatus.RUNNING) >= max_running:
            return None
        query = select(WritingAIGradingRun).where(
            WritingAIGradingRun.status == WritingAIRunStatus.PENDING
        )
        if run_id is not None:
            query = query.where(WritingAIGradingRun.id == run_id)
        run = await self.session.scalar(
            query.order_by(WritingAIGradingRun.created_at, WritingAIGradingRun.id)
            .with_for_update(skip_locked=True)
            .limit(1)
            .execution_options(populate_existing=True)
        )
        if run is not None:
            now = await self.session.scalar(select(func.clock_timestamp()))
            run.status = WritingAIRunStatus.RUNNING
            run.lease_token = uuid4()
            run.lease_expires_at = now + timedelta(seconds=lease_seconds)
            run.started_at = run.updated_at = now
        return run

    async def owned(self, run_id: UUID, token: UUID):
        run = await self.run(run_id, lock=True)
        now = await self.session.scalar(select(func.clock_timestamp()))
        if (
            run is None
            or run.status != WritingAIRunStatus.RUNNING
            or token is None
            or run.lease_token != token
            or run.lease_expires_at is None
            or run.lease_expires_at <= now
        ):
            return None
        return run

    async def expired(self, *, legacy_stale_seconds: int, limit: int):
        return list(
            await self.session.scalars(
                select(WritingAIGradingRun)
                .where(
                    WritingAIGradingRun.status == WritingAIRunStatus.RUNNING,
                    or_(
                        WritingAIGradingRun.lease_expires_at <= func.clock_timestamp(),
                        (WritingAIGradingRun.lease_expires_at.is_(None))
                        & (
                            WritingAIGradingRun.updated_at
                            < func.clock_timestamp() - timedelta(seconds=legacy_stale_seconds)
                        ),
                    ),
                )
                .order_by(WritingAIGradingRun.created_at, WritingAIGradingRun.id)
                .with_for_update(skip_locked=True)
                .limit(limit)
                .execution_options(populate_existing=True)
            )
        )

    async def attempt(
        self, attempt_id: UUID, user_id: UUID, *, lock: bool = False
    ) -> Attempt | None:
        statement = select(Attempt).where(Attempt.id == attempt_id, Attempt.user_id == user_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def task(self, task_id: UUID, version_id: UUID) -> WritingTask | None:
        return await self.session.scalar(
            select(WritingTask)
            .join(TestModule)
            .where(
                WritingTask.id == task_id,
                TestModule.test_version_id == version_id,
                TestModule.module_type == ModuleType.WRITING,
            )
        )

    async def essay(self, attempt_id: UUID, task_id: UUID) -> str:
        return (
            await self.session.scalar(
                select(AttemptWritingResponse.content).where(
                    AttemptWritingResponse.attempt_id == attempt_id,
                    AttemptWritingResponse.writing_task_id == task_id,
                )
            )
            or ""
        )

    async def run(
        self, run_id: UUID, *, user_id: UUID | None = None, lock: bool = False
    ) -> WritingAIGradingRun | None:
        statement = (
            select(WritingAIGradingRun)
            .where(WritingAIGradingRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        if user_id is not None:
            statement = statement.join(Attempt).where(
                Attempt.user_id == user_id, WritingAIGradingRun.requested_by_user_id == user_id
            )
        if lock:
            statement = statement.with_for_update(of=WritingAIGradingRun)
        return await self.session.scalar(statement)

    async def runs(
        self, attempt_id: UUID, task_id: UUID, *, lock: bool = False, limit: int | None = 20
    ) -> list[WritingAIGradingRun]:
        statement = (
            select(WritingAIGradingRun)
            .where(
                WritingAIGradingRun.attempt_id == attempt_id,
                WritingAIGradingRun.writing_task_id == task_id,
            )
            .order_by(WritingAIGradingRun.created_at.desc(), WritingAIGradingRun.id.desc())
        )
        if lock:
            statement = statement.with_for_update()
        if limit is not None:
            statement = statement.limit(limit)
        return list(await self.session.scalars(statement))

    async def equivalent(
        self,
        attempt_id: UUID,
        task_id: UUID,
        fingerprint: str,
        statuses: tuple[WritingAIRunStatus, ...],
    ) -> WritingAIGradingRun | None:
        return await self.session.scalar(
            select(WritingAIGradingRun)
            .where(
                WritingAIGradingRun.attempt_id == attempt_id,
                WritingAIGradingRun.writing_task_id == task_id,
                WritingAIGradingRun.input_fingerprint == fingerprint,
                WritingAIGradingRun.status.in_(statuses),
            )
            .order_by(WritingAIGradingRun.created_at.desc())
            .limit(1)
        )

    async def append_event(
        self, run: WritingAIGradingRun, event_type: EventType, payload: EventPayload
    ) -> None:
        # All callers hold the run row lock, serializing both the sequence and state.
        sequence = await self.session.scalar(
            select(func.coalesce(func.max(WritingAIGradingEvent.sequence), 0)).where(
                WritingAIGradingEvent.run_id == run.id
            )
        )
        self.session.add(
            WritingAIGradingEvent(
                run_id=run.id,
                sequence=sequence + 1,
                event_type=event_type,
                payload=payload.model_dump(mode="json", exclude_none=True),
            )
        )
        await self.session.flush()

    async def events(self, run_id: UUID, after: int) -> list[WritingAIGradingEvent]:
        return list(
            await self.session.scalars(
                select(WritingAIGradingEvent)
                .where(
                    WritingAIGradingEvent.run_id == run_id,
                    WritingAIGradingEvent.sequence > after,
                )
                .order_by(WritingAIGradingEvent.sequence)
                .limit(100)
            )
        )
