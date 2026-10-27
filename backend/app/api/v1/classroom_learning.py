from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.database import get_session
from app.schemas.classroom_learning import (
    LearningDashboard,
    LearningGoals,
    PlanPage,
    PlanResponse,
    PlanWrite,
    Recommendation,
)
from app.services.classroom_learning import ClassroomLearningService
from app.services.classroom_learning_plans import LearningPlanService
from app.services.learning_goals import LearningGoalService

router = APIRouter(tags=["classroom-learning"])
Session = Annotated[AsyncSession, Depends(get_session)]


class LearningRange:
    def __init__(
        self,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
        completion_offset: int = Query(0, ge=0),
    ):
        self.values = dict(start=start, end=end, completion_offset=completion_offset)


@router.get("/me/learning-goals", response_model=LearningGoals)
async def learning_goals(user: CurrentUser, session: Session):
    return await LearningGoalService(session, user).get()


@router.put("/me/learning-goals", response_model=LearningGoals)
async def save_learning_goals(body: LearningGoals, user: CurrentUser, session: Session):
    return await LearningGoalService(session, user).save(body)


@router.get("/classrooms/{classroom_id}/analytics", response_model=LearningDashboard)
async def analytics(
    classroom_id: UUID,
    user: CurrentUser,
    session: Session,
    period: Annotated[LearningRange, Depends()],
):
    return await ClassroomLearningService(session, user).dashboard(classroom_id, **period.values)


@router.get(
    "/classrooms/{classroom_id}/students/{student_id}/analytics", response_model=LearningDashboard
)
async def student_analytics(
    classroom_id: UUID,
    student_id: UUID,
    user: CurrentUser,
    session: Session,
    period: Annotated[LearningRange, Depends()],
):
    return await ClassroomLearningService(session, user).dashboard(
        classroom_id, student_id=student_id, **period.values
    )


@router.get("/classrooms/{classroom_id}/my-progress", response_model=LearningDashboard)
async def my_progress(
    classroom_id: UUID,
    user: CurrentUser,
    session: Session,
    period: Annotated[LearningRange, Depends()],
):
    return await ClassroomLearningService(session, user).dashboard(
        classroom_id, own=True, **period.values
    )


@router.get("/classrooms/{classroom_id}/my-recommendations", response_model=list[Recommendation])
async def my_recommendations(classroom_id: UUID, user: CurrentUser, session: Session):
    return (
        await ClassroomLearningService(session, user).dashboard(classroom_id, own=True)
    ).recommendations


@router.get("/classrooms/{classroom_id}/learning-plans", response_model=PlanPage)
async def learning_plans(
    classroom_id: UUID,
    user: CurrentUser,
    session: Session,
    student_id: UUID | None = None,
    limit: int = Query(30, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    return await LearningPlanService(session, user).list(
        classroom_id, student_id=student_id, limit=limit, offset=offset
    )


@router.post(
    "/classrooms/{classroom_id}/students/{student_id}/learning-plans",
    response_model=PlanResponse,
    status_code=201,
)
async def create_plan(
    classroom_id: UUID, student_id: UUID, body: PlanWrite, user: CurrentUser, session: Session
):
    return await LearningPlanService(session, user).write(classroom_id, student_id, body)


@router.put(
    "/classrooms/{classroom_id}/students/{student_id}/learning-plans/{plan_id}",
    response_model=PlanResponse,
)
async def update_plan(
    classroom_id: UUID,
    student_id: UUID,
    plan_id: UUID,
    body: PlanWrite,
    user: CurrentUser,
    session: Session,
):
    return await LearningPlanService(session, user).write(
        classroom_id, student_id, body, plan_id=plan_id
    )


@router.post(
    "/classrooms/{classroom_id}/learning-plans/{plan_id}/items/{item_id}/complete-resource",
    response_model=PlanResponse,
)
async def complete_resource(
    classroom_id: UUID, plan_id: UUID, item_id: UUID, user: CurrentUser, session: Session
):
    return await LearningPlanService(session, user).complete_resource(
        classroom_id, plan_id, item_id
    )
