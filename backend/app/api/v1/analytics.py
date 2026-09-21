from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.enums import ModuleType
from app.schemas.analytics import AnalyticsDashboard, AttemptComparison
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsDashboard)
async def analytics_dashboard(
    skill: ModuleType | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsDashboard:
    return await AnalyticsService(session).dashboard(skill)


@router.get("/compare", response_model=AttemptComparison)
async def compare_attempts(
    left: UUID,
    right: UUID,
    session: AsyncSession = Depends(get_session),
) -> AttemptComparison:
    return await AnalyticsService(session).compare(left, right)
