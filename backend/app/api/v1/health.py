import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", server_time=TimerService.now())


@router.get("/ready", response_model=HealthResponse)
async def ready(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    try:
        async with asyncio.timeout(3):
            await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, TimeoutError):
        raise AppError("SERVICE_NOT_READY", "The service is not ready.", 503) from None
    return HealthResponse(status="ready", server_time=TimerService.now())
