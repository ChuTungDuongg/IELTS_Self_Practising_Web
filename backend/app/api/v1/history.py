from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.attempts import AttemptList
from app.services.attempts import AttemptService

router = APIRouter(tags=["history"])


@router.get("/history", response_model=AttemptList)
async def history(session: AsyncSession = Depends(get_session)) -> AttemptList:
    return await AttemptService(session).history()
