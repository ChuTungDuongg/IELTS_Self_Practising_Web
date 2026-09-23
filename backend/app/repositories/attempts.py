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
        statement = (
            select(Attempt)
            .where(Attempt.id == attempt_id)
            .options(
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
                selectinload(Attempt.test_session).selectinload(TestSession.attempts),
                selectinload(Attempt.test_version)
                .selectinload(TestVersion.modules)
                .selectinload(TestModule.writing_tasks)
                .selectinload(WritingTask.image_asset),
            )
        )
        if user_id is not None:
            statement = statement.where(Attempt.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_history(self, user_id: uuid.UUID) -> list[Attempt]:
        result = await self.session.scalars(
            select(Attempt)
            .where(Attempt.user_id == user_id)
            .options(selectinload(Attempt.test_version).selectinload(TestVersion.test))
            .options(selectinload(Attempt.test_session))
            .order_by(Attempt.started_at.desc())
        )
        return list(result)
