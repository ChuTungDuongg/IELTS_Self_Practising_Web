import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Attempt, AttemptAnswer, AttemptWritingResponse, TestVersion


class AttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, attempt_id: uuid.UUID, *, for_update: bool = False) -> Attempt | None:
        statement = (
            select(Attempt)
            .where(Attempt.id == attempt_id)
            .options(
                selectinload(Attempt.answers).selectinload(AttemptAnswer.question),
                selectinload(Attempt.writing_responses).selectinload(
                    AttemptWritingResponse.writing_task
                ),
                selectinload(Attempt.highlights),
                selectinload(Attempt.flags),
                selectinload(Attempt.test_version).selectinload(TestVersion.test),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_history(self) -> list[Attempt]:
        result = await self.session.scalars(
            select(Attempt)
            .options(selectinload(Attempt.test_version).selectinload(TestVersion.test))
            .order_by(Attempt.started_at.desc())
        )
        return list(result)
