from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Test,
    TestModule,
    TestVersion,
    WritingAnchorSet,
    WritingHumanAnchor,
    WritingTask,
)
from app.models.enums import ModuleType, VersionStatus


def task_query():
    return (
        select(WritingTask, TestVersion, Test)
        .join(TestModule, WritingTask.module_id == TestModule.id)
        .join(TestVersion, TestModule.test_version_id == TestVersion.id)
        .join(Test, TestVersion.test_id == Test.id)
        .where(TestModule.module_type == ModuleType.WRITING, WritingTask.task_number.in_([1, 2]))
    )


def frozen_condition():
    return or_(
        TestVersion.status == VersionStatus.PUBLISHED,
        and_(TestVersion.status == VersionStatus.ARCHIVED, TestVersion.published_at.is_not(None)),
    )


def anchor_query():
    return (
        select(WritingHumanAnchor, WritingTask, TestVersion, Test)
        .join(WritingTask, WritingHumanAnchor.writing_task_id == WritingTask.id)
        .join(TestModule, WritingTask.module_id == TestModule.id)
        .join(TestVersion, TestModule.test_version_id == TestVersion.id)
        .join(Test, TestVersion.test_id == Test.id)
    )


class WritingAnchorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lifecycle_lock(self):
        await self.session.execute(text("SELECT pg_advisory_xact_lock(202610080021)"))

    async def set(self, set_id: UUID, *, lock: bool = False):
        statement = select(WritingAnchorSet).where(WritingAnchorSet.id == set_id)
        return await self.session.scalar(statement.with_for_update() if lock else statement)

    async def active(self):
        return await self.session.scalar(
            select(WritingAnchorSet).where(WritingAnchorSet.status == "ACTIVE")
        )

    async def sets(self):
        return list(
            await self.session.scalars(
                select(WritingAnchorSet).order_by(WritingAnchorSet.version.desc())
            )
        )

    async def next_version(self):
        return (await self.session.scalar(select(func.max(WritingAnchorSet.version))) or 0) + 1

    async def anchor(self, anchor_id: UUID):
        return (
            await self.session.execute(anchor_query().where(WritingHumanAnchor.id == anchor_id))
        ).first()

    async def rows(self, set_id: UUID):
        return (
            await self.session.execute(
                anchor_query()
                .where(WritingHumanAnchor.anchor_set_id == set_id)
                .order_by(WritingHumanAnchor.id)
            )
        ).all()
