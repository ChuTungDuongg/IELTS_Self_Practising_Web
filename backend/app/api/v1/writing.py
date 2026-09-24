from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.core.database import get_session
from app.schemas.content import BuilderWritingTask, WritingTaskUpdate
from app.services.writing import WritingService

router = APIRouter(tags=["writing-builder"], dependencies=[Depends(require_admin)])


@router.put("/writing/tasks/{task_id}", response_model=BuilderWritingTask)
async def update_writing_task(
    task_id: UUID,
    body: WritingTaskUpdate,
    session: AsyncSession = Depends(get_session),
) -> BuilderWritingTask:
    return await WritingService(session).update_task(task_id, body)
