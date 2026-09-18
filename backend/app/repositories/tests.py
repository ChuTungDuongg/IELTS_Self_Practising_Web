import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import QuestionGroup, ReadingPassage, Test, TestModule, TestVersion


def version_detail_query() -> Select[tuple[TestVersion]]:
    return select(TestVersion).options(
        selectinload(TestVersion.test),
        selectinload(TestVersion.modules).selectinload(TestModule.passages),
        selectinload(TestVersion.modules)
        .selectinload(TestModule.passages)
        .selectinload(ReadingPassage.question_groups)
        .selectinload(QuestionGroup.questions),
        selectinload(TestVersion.modules).selectinload(TestModule.listening_parts),
        selectinload(TestVersion.modules).selectinload(TestModule.writing_tasks),
        selectinload(TestVersion.modules)
        .selectinload(TestModule.question_groups)
        .selectinload(QuestionGroup.questions),
    )


class TestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Test]:
        result = await self.session.scalars(
            select(Test).options(selectinload(Test.versions)).order_by(Test.created_at.desc())
        )
        return list(result.unique())

    async def get(self, test_id: uuid.UUID) -> Test | None:
        result = await self.session.scalar(
            select(Test).where(Test.id == test_id).options(selectinload(Test.versions))
        )
        return result

    async def get_version(self, version_id: uuid.UUID) -> TestVersion | None:
        return await self.session.scalar(version_detail_query().where(TestVersion.id == version_id))

    async def next_version_number(self, test_id: uuid.UUID) -> int:
        highest = await self.session.scalar(
            select(func.max(TestVersion.version_number)).where(TestVersion.test_id == test_id)
        )
        return (highest or 0) + 1
