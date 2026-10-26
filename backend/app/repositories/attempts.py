import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptWritingResponse,
    AttemptWritingScore,
    Question,
    QuestionGroup,
    TestModule,
    TestSession,
    TestVersion,
    WritingTask,
)


class AttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        attempt_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        for_update: bool = False,
    ) -> Attempt | None:
        if for_update:
            # Session transitions and Speaking use parent -> attempt. Acquiring
            # the child first deadlocks when finalization updates its parent.
            parent = (
                select(TestSession.id)
                .join(Attempt, Attempt.test_session_id == TestSession.id)
                .where(Attempt.id == attempt_id)
                .with_for_update(of=TestSession)
            )
            if user_id is not None:
                parent = parent.where(Attempt.user_id == user_id)
            await self.session.scalar(parent)
            # Refresh only the locked attempt first. Propagating populate_existing
            # through the entire graph expires unrelated immutable content that
            # callers may already have loaded on this session.
            locked = select(Attempt).where(Attempt.id == attempt_id).with_for_update()
            if user_id is not None:
                locked = locked.where(Attempt.user_id == user_id)
            if await self.session.scalar(locked.execution_options(populate_existing=True)) is None:
                return None
        statement = (
            select(Attempt)
            .where(Attempt.id == attempt_id)
            .options(
                selectinload(Attempt.focused_reading_passage),
                selectinload(Attempt.focused_listening_part),
                selectinload(Attempt.focused_writing_task),
                selectinload(Attempt.focused_speaking_prompt),
                selectinload(Attempt.focused_speaking_part),
                selectinload(Attempt.answers)
                .selectinload(AttemptAnswer.question)
                .selectinload(Question.question_group)
                .selectinload(QuestionGroup.passage),
                selectinload(Attempt.writing_responses).selectinload(
                    AttemptWritingResponse.writing_task
                ),
                selectinload(Attempt.writing_scores).selectinload(AttemptWritingScore.writing_task),
                selectinload(Attempt.highlights),
                selectinload(Attempt.flags),
                selectinload(Attempt.test_version).selectinload(TestVersion.test),
                selectinload(Attempt.test_session),
                selectinload(Attempt.test_version)
                .selectinload(TestVersion.modules)
                .selectinload(TestModule.writing_tasks)
                .selectinload(WritingTask.image_asset),
            )
        )
        if user_id is not None:
            statement = statement.where(Attempt.user_id == user_id)
        return await self.session.scalar(statement)

    async def list_history(self, user_id: uuid.UUID) -> list[Attempt]:
        result = await self.session.scalars(
            select(Attempt)
            .where(Attempt.user_id == user_id)
            .options(selectinload(Attempt.test_version).selectinload(TestVersion.test))
            .options(selectinload(Attempt.test_session))
            .options(selectinload(Attempt.writing_scores))
            .options(
                selectinload(Attempt.focused_reading_passage),
                selectinload(Attempt.focused_listening_part),
                selectinload(Attempt.focused_writing_task),
                selectinload(Attempt.focused_speaking_prompt),
                selectinload(Attempt.focused_speaking_part),
            )
            .order_by(Attempt.started_at.desc())
        )
        return list(result)
