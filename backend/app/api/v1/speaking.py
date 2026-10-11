"""Speaking Builder routes only. Runtime Speaking is a later phase."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_content_author
from app.core.database import get_session
from app.schemas.speaking import (
    BuilderSpeakingPart,
    SpeakingPartOrderWrite,
    SpeakingPartUpdate,
    SpeakingPartWrite,
    SpeakingPromptCreate,
    SpeakingPromptOrderWrite,
)
from app.services.speaking_builder import SpeakingBuilderService

router = APIRouter(dependencies=[Depends(require_content_author)], tags=["speaking-builder"])


@router.post(
    "/speaking/modules/{module_id}/parts",
    response_model=BuilderSpeakingPart,
    status_code=status.HTTP_201_CREATED,
)
async def create_part(
    module_id: UUID,
    body: SpeakingPartWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).create_part(module_id, body)


@router.put("/speaking/modules/{module_id}/parts/order", response_model=list[BuilderSpeakingPart])
async def reorder_parts(
    module_id: UUID,
    body: SpeakingPartOrderWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).reorder_parts(module_id, body)


@router.put("/speaking/parts/{part_id}", response_model=BuilderSpeakingPart)
async def update_part(
    part_id: UUID,
    body: SpeakingPartUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).update_part(part_id, body)


@router.delete("/speaking/parts/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_part(
    part_id: UUID,
    user: CurrentUser,
    expected_revision: int = Query(ge=1),
    session: AsyncSession = Depends(get_session),
):
    await SpeakingBuilderService(session, actor=user).delete_part(
        part_id, expected_revision=expected_revision
    )


@router.post(
    "/speaking/parts/{part_id}/prompts",
    response_model=BuilderSpeakingPart,
    status_code=status.HTTP_201_CREATED,
)
async def create_prompt(
    part_id: UUID,
    body: SpeakingPromptCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).create_prompt(part_id, body)


@router.put("/speaking/parts/{part_id}/prompts/order", response_model=BuilderSpeakingPart)
async def reorder_prompts(
    part_id: UUID,
    body: SpeakingPromptOrderWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).reorder_prompts(part_id, body)


@router.delete("/speaking/parts/{part_id}/prompts/{prompt_id}", response_model=BuilderSpeakingPart)
async def delete_prompt(
    part_id: UUID,
    prompt_id: UUID,
    user: CurrentUser,
    expected_revision: int = Query(ge=1),
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).delete_prompt(
        part_id, prompt_id, expected_revision=expected_revision
    )


@router.put("/speaking/parts/{part_id}/prompts/{prompt_id}", response_model=BuilderSpeakingPart)
async def update_prompt(
    part_id: UUID,
    prompt_id: UUID,
    body: SpeakingPromptCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).update_prompt(part_id, prompt_id, body)
