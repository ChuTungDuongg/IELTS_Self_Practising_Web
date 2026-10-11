from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_content_author
from app.core.database import get_session
from app.schemas.content import BuilderWritingTask, WritingTaskUpdate
from app.services.writing import WritingService

router = APIRouter(dependencies=[Depends(require_content_author)], tags=["writing-builder"])


@router.put("/writing/tasks/{task_id}", response_model=BuilderWritingTask)
async def update_writing_task(
    task_id: UUID,
    body: WritingTaskUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> BuilderWritingTask:
    return await WritingService(session, actor=user).update_task(task_id, body)
