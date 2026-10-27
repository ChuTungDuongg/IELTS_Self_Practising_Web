from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ListeningPart,
    QuestionGroup,
    ReadingPassage,
    SpeakingPart,
    Test,
    TestModule,
    TestVersion,
    WritingTask,
)


def version_detail_query() -> Select[tuple[TestVersion]]:
    return select(TestVersion).options(
        selectinload(TestVersion.test),
        selectinload(TestVersion.modules).selectinload(TestModule.passages),
        selectinload(TestVersion.modules)
        .selectinload(TestModule.speaking_parts)
        .selectinload(SpeakingPart.prompts),
        selectinload(TestVersion.modules)
        .selectinload(TestModule.passages)
        .selectinload(ReadingPassage.question_groups)
        .selectinload(QuestionGroup.questions),
        selectinload(TestVersion.modules).selectinload(TestModule.listening_parts),
        selectinload(TestVersion.modules).selectinload(TestModule.audio_asset),
        selectinload(TestVersion.modules)
        .selectinload(TestModule.listening_parts)
        .selectinload(ListeningPart.question_groups)
        .selectinload(QuestionGroup.questions),
        selectinload(TestVersion.modules)
        .selectinload(TestModule.writing_tasks)
        .selectinload(WritingTask.image_asset),
        selectinload(TestVersion.modules)
        .selectinload(TestModule.question_groups)
        .selectinload(QuestionGroup.questions),
        selectinload(TestVersion.modules)
        .selectinload(TestModule.question_groups)
        .selectinload(QuestionGroup.image_asset),
        selectinload(TestVersion.assets),
    )


class TestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, archived: bool = False) -> list[Test]:
        archive_filter = Test.archived_at.is_not(None) if archived else Test.archived_at.is_(None)
        result = await self.session.scalars(
            select(Test)
            .where(archive_filter)
            .options(selectinload(Test.versions), selectinload(Test.owner))
            .order_by(Test.created_at.desc())
        )
        return list(result.unique())

    async def get(self, test_id: uuid.UUID) -> Test | None:
        result = await self.session.scalar(
            select(Test).where(Test.id == test_id).options(selectinload(Test.versions))
        )
        return result

    async def get_version(self, version_id: uuid.UUID) -> TestVersion | None:
        return await self.session.scalar(version_detail_query().where(TestVersion.id == version_id))

    async def get_versions(self, version_ids: list[uuid.UUID]) -> list[TestVersion]:
        versions = []
        # Bound IN parameters and relationship loader work for large catalogs.
        for start in range(0, len(version_ids), 100):
            rows = await self.session.scalars(
                version_detail_query().where(TestVersion.id.in_(version_ids[start : start + 100]))
            )
            versions.extend(rows)
        return versions

    async def next_version_number(self, test_id: uuid.UUID) -> int:
        highest = await self.session.scalar(
            select(func.max(TestVersion.version_number)).where(TestVersion.test_id == test_id)
        )
        return (highest or 0) + 1
