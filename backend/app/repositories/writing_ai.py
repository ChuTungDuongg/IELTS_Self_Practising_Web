from uuid import UUID

from sqlalchemy import func, select
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


class WritingAIRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        statement = select(WritingAIGradingRun).where(WritingAIGradingRun.id == run_id)
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
