from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.database import get_session
from app.schemas.attempts import AttemptList
from app.services.attempts import AttemptService

router = APIRouter(tags=["history"])


@router.get("/history", response_model=AttemptList)
async def history(user: CurrentUser, session: AsyncSession = Depends(get_session)) -> AttemptList:
    return await AttemptService(session, user.id).history()


@router.delete(
    "/history/test-versions/{test_version_id}/standalone-attempts",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_standalone_history(
    test_version_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> Response:
    await AttemptService(session, user.id).delete_standalone_history(test_version_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
