"""Speaking authoring queries. Access and mutations belong to the service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Attempt,
    SpeakingPart,
    SpeakingPrompt,
    SpeakingPromptProgress,
    SpeakingResponse,
    SpeakingResponseTake,
    TestModule,
)


class SpeakingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_attempt(self, attempt_id: UUID, user_id: UUID):
        # Every runtime/media/recovery mutation must take this parent lock first.
        # Refresh identity-map state after waiting for a concurrent commit.
        return await self.session.scalar(
            select(Attempt)
            .where(Attempt.id == attempt_id, Attempt.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def prompts(self, attempt: Attempt):
        query = (
            select(SpeakingPrompt)
            .join(SpeakingPart)
            .join(TestModule)
            .where(
                TestModule.test_version_id == attempt.test_version_id,
                TestModule.module_type == "SPEAKING",
            )
            .options(selectinload(SpeakingPrompt.part))
            .order_by(SpeakingPart.part_number, SpeakingPrompt.order_index)
        )
        if attempt.focused_speaking_prompt_id is not None:
            query = query.where(SpeakingPrompt.id == attempt.focused_speaking_prompt_id)
        return list(await self.session.scalars(query))

    async def progress(self, attempt_id: UUID):
        return await self.session.get(SpeakingPromptProgress, attempt_id, populate_existing=True)

    async def response(self, attempt_id: UUID, prompt_id: UUID):
        return await self.session.scalar(
            select(SpeakingResponse)
            .where(
                SpeakingResponse.attempt_id == attempt_id, SpeakingResponse.prompt_id == prompt_id
            )
            .execution_options(populate_existing=True)
        )

    async def take(self, response_id: UUID, take_number: int):
        return await self.session.scalar(
            select(SpeakingResponseTake)
            .where(
                SpeakingResponseTake.response_id == response_id,
                SpeakingResponseTake.take_number == take_number,
            )
            .execution_options(populate_existing=True)
        )

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
