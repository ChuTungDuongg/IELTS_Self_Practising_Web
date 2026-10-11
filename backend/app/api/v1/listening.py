from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_content_author
from app.core.database import get_session
from app.schemas.content import (
    BuilderListeningPart,
    BuilderModule,
    BuilderQuestionGroup,
    ListeningModuleAudioWrite,
    ListeningPartUpdate,
    ListeningPartWrite,
    QuestionGroupUpdate,
    QuestionGroupWrite,
)
from app.services.listening import ListeningService

router = APIRouter(dependencies=[Depends(require_content_author)], tags=["listening-builder"])


@router.post(
    "/test-versions/{version_id}/listening/parts",
    response_model=BuilderListeningPart,
    status_code=status.HTTP_201_CREATED,
)
async def create_listening_part(
    version_id: UUID,
    body: ListeningPartWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderListeningPart:
    return await ListeningService(session, actor=user).create_part(version_id, body)


@router.put("/listening/parts/{part_id}", response_model=BuilderListeningPart)
async def update_listening_part(
    part_id: UUID,
    body: ListeningPartUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderListeningPart:
    return await ListeningService(session, actor=user).update_part(part_id, body)


@router.delete("/listening/parts/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listening_part(
    part_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> Response:
    await ListeningService(session, actor=user).delete_part(part_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/listening/modules/{module_id}/audio", response_model=BuilderModule)
async def attach_listening_audio(
    module_id: UUID,
    body: ListeningModuleAudioWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderModule:
    return await ListeningService(session, actor=user).attach_audio(module_id, body)


@router.post(
    "/listening/parts/{part_id}/question-groups",
    response_model=BuilderQuestionGroup,
    status_code=status.HTTP_201_CREATED,
)
async def create_listening_group(
    part_id: UUID,
    body: QuestionGroupWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderQuestionGroup:
    return await ListeningService(session, actor=user).create_group(part_id, body)


@router.put("/listening/question-groups/{group_id}", response_model=BuilderQuestionGroup)
async def update_listening_group(
    group_id: UUID,
    body: QuestionGroupUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderQuestionGroup:
    return await ListeningService(session, actor=user).update_group(group_id, body)
