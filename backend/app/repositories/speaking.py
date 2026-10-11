"""Speaking authoring queries. Access and mutations belong to the service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import SpeakingPart, TestModule


class SpeakingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def module_version_id(self, module_id: UUID):
        return await self.session.scalar(
            select(TestModule.test_version_id).where(TestModule.id == module_id)
        )

    async def part_module_id(self, part_id: UUID):
        return await self.session.scalar(
            select(SpeakingPart.module_id).where(SpeakingPart.id == part_id)
        )

    async def module(self, module_id: UUID, *, lock: bool = False):
        query = (
            select(TestModule)
            .where(TestModule.id == module_id)
            .options(
                selectinload(TestModule.speaking_parts).selectinload(SpeakingPart.prompts),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)
