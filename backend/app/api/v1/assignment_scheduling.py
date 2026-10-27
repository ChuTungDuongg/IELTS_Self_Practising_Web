from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.database import get_session
from app.schemas.assignment_scheduling import (
    AssignmentScheduleUpdate,
    CalendarPage,
    ExtensionResponse,
    ExtensionWrite,
    MonitoringPage,
    PolicyHistoryPage,
    ProgressPage,
)
from app.schemas.classroom_assignments import AssignmentResponse
from app.services.assignment_progress import AssignmentProgressService
from app.services.assignment_scheduling import AssignmentSchedulingService

router = APIRouter(prefix="/classrooms/{classroom_id}", tags=["assignment-scheduling"])


@router.patch("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update(
    classroom_id: UUID,
    assignment_id: UUID,
    body: AssignmentScheduleUpdate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await AssignmentSchedulingService(session, actor).update(
        classroom_id, assignment_id, body
    )


@router.get("/assignment-progress", response_model=ProgressPage)
async def progress(
    classroom_id: UUID,
    actor: CurrentUser,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    assignment_ids: list[UUID] | None = Query(default=None, max_length=100),
    session: AsyncSession = Depends(get_session),
):
    return await AssignmentProgressService(session, actor).student(
        classroom_id, limit=limit, offset=offset, assignment_ids=assignment_ids
    )


@router.get("/assignments/{assignment_id}/progress", response_model=ProgressPage)
async def assignment_progress(
    classroom_id: UUID,
    assignment_id: UUID,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await AssignmentProgressService(session, actor).student(
        classroom_id, assignment_id=assignment_id
    )


@router.get("/assignments/{assignment_id}/monitoring", response_model=MonitoringPage)
async def monitoring(
    classroom_id: UUID,
    assignment_id: UUID,
    actor: CurrentUser,
    status: Literal[
        "ALL",
        "NOT_STARTED",
        "IN_PROGRESS",
        "SUBMITTED",
        "SUBMITTED_ON_TIME",
        "SUBMITTED_LATE",
        "SUBMITTED_NOT_ACCEPTED",
        "MISSED",
    ] = "ALL",
    search: str = Query("", max_length=120),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    return await AssignmentProgressService(session, actor).monitor(
        classroom_id, assignment_id, status=status, search=search, limit=limit, offset=offset
    )


@router.get("/assignments/{assignment_id}/extensions", response_model=list[ExtensionResponse])
async def extensions(
    classroom_id: UUID,
    assignment_id: UUID,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await AssignmentSchedulingService(session, actor).extensions(classroom_id, assignment_id)


@router.put(
    "/assignments/{assignment_id}/extensions/{student_id}", response_model=ExtensionResponse
)
async def extension(
    classroom_id: UUID,
    assignment_id: UUID,
    student_id: UUID,
    body: ExtensionWrite,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await AssignmentSchedulingService(session, actor).write_extension(
        classroom_id, assignment_id, student_id, body
    )


@router.delete(
    "/assignments/{assignment_id}/extensions/{student_id}", response_model=ExtensionResponse
)
async def revoke(
    classroom_id: UUID,
    assignment_id: UUID,
    student_id: UUID,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await AssignmentSchedulingService(session, actor).write_extension(
        classroom_id, assignment_id, student_id, None
    )


@router.get("/assignments/{assignment_id}/schedule-history", response_model=PolicyHistoryPage)
async def history(
    classroom_id: UUID,
    assignment_id: UUID,
    actor: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    return {
        "items": await AssignmentSchedulingService(session, actor).history(
            classroom_id, assignment_id, limit=limit, offset=offset
        )
    }


@router.get("/assignment-calendar", response_model=CalendarPage)
async def calendar(
    classroom_id: UUID,
    actor: CurrentUser,
    start: AwareDatetime,
    end: AwareDatetime,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    return await AssignmentProgressService(session, actor).calendar(
        classroom_id, start, end, limit=limit, offset=offset
    )
