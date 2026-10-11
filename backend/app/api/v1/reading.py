from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_content_author
from app.core.database import get_session
from app.schemas.content import (
    BuilderModule,
    BuilderPassage,
    BuilderQuestionGroup,
    BuilderVersion,
    ModuleCreate,
    ModuleUpdate,
    PassageUpdate,
    PassageWrite,
    QuestionGroupOrderWrite,
    QuestionGroupUpdate,
    QuestionGroupWrite,
)
from app.services.reading import ReadingService

router = APIRouter(dependencies=[Depends(require_content_author)], tags=["builder"])


@router.get("/test-versions/{version_id}/builder", response_model=BuilderVersion)
async def get_builder_version(
    version_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> BuilderVersion:
    return await ReadingService(session, actor=user).builder_version(version_id)


@router.post(
    "/test-versions/{version_id}/modules",
    response_model=BuilderModule,
    status_code=status.HTTP_201_CREATED,
)
async def create_module(
    version_id: UUID,
    body: ModuleCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderModule:
    return await ReadingService(session, actor=user).create_module(version_id, body)


@router.patch("/test-modules/{module_id}", response_model=BuilderModule)
async def update_module(
    module_id: UUID,
    body: ModuleUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderModule:
    return await ReadingService(session, actor=user).update_module(module_id, body)


@router.post(
    "/test-versions/{version_id}/reading/passages",
    response_model=BuilderPassage,
    status_code=status.HTTP_201_CREATED,
)
async def create_passage(
    version_id: UUID,
    body: PassageWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderPassage:
    return await ReadingService(session, actor=user).create_passage(version_id, body)


@router.put("/reading/passages/{passage_id}", response_model=BuilderPassage)
async def update_passage(
    passage_id: UUID,
    body: PassageUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderPassage:
    return await ReadingService(session, actor=user).update_passage(passage_id, body)


@router.delete("/reading/passages/{passage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_passage(
    passage_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> Response:
    await ReadingService(session, actor=user).delete_passage(passage_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reading/passages/{passage_id}/question-groups",
    response_model=BuilderQuestionGroup,
    status_code=status.HTTP_201_CREATED,
)
async def create_question_group(
    passage_id: UUID,
    body: QuestionGroupWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderQuestionGroup:
    return await ReadingService(session, actor=user).create_group(passage_id, body)


@router.put("/question-groups/{group_id}", response_model=BuilderQuestionGroup)
async def update_question_group(
    group_id: UUID,
    body: QuestionGroupUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderQuestionGroup:
    return await ReadingService(session, actor=user).update_group(group_id, body)


@router.delete("/question-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question_group(
    group_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> Response:
    await ReadingService(session, actor=user).delete_group(group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/test-modules/{module_id}/question-groups/order", response_model=BuilderModule)
async def reorder_question_groups(
    module_id: UUID,
    body: QuestionGroupOrderWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderModule:
    return await ReadingService(session, actor=user).reorder_groups(module_id, body)
