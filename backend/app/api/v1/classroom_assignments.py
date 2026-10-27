from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.database import get_session
from app.schemas.attempts import WritingTaskScoreUpdate
from app.schemas.classroom_assignments import (
    AssignmentResponse,
    AssignmentStart,
    AssignmentStartResponse,
    TargetedAssignmentCreate,
)
from app.schemas.classroom_results import AssignmentResultDetail, AssignmentResultSummary
from app.schemas.content import WritingAttemptReview
from app.schemas.grading import SpeakingScoreUpdate
from app.schemas.speaking import SpeakingReviewData
from app.services.attempts import AttemptService
from app.services.classroom_assignments import ClassroomAssignmentService
from app.services.classroom_results import ClassroomResultService
from app.services.speaking_final import SpeakingFinalService

router = APIRouter(tags=["classroom-assignments"])


@router.delete("/classrooms/{classroom_id}/assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    classroom_id: UUID,
    assignment_id: UUID,
    user: CurrentUser,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    await ClassroomAssignmentService(session, user).delete(classroom_id, assignment_id)
    from app.services.speaking_media import cleanup_private_media

    background.add_task(cleanup_private_media)


@router.get("/classrooms/{classroom_id}/assignments", response_model=list[AssignmentResponse])
@router.get("/me/classrooms/{classroom_id}/assignments", response_model=list[AssignmentResponse])
async def assignments(
    classroom_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassroomAssignmentService(session, user).list(classroom_id)


@router.post(
    "/classrooms/{classroom_id}/assignments", response_model=AssignmentResponse, status_code=201
)
async def create(
    classroom_id: UUID,
    body: TargetedAssignmentCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomAssignmentService(session, user).create(classroom_id, body)


@router.get(
    "/classrooms/{classroom_id}/assignments/{assignment_id}", response_model=AssignmentResponse
)
async def detail(
    classroom_id: UUID,
    assignment_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomAssignmentService(session, user).get(classroom_id, assignment_id)


@router.post(
    "/classrooms/{classroom_id}/assignments/{assignment_id}/archive",
    response_model=AssignmentResponse,
)
async def archive(
    classroom_id: UUID,
    assignment_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomAssignmentService(session, user).archive(classroom_id, assignment_id)


@router.post(
    "/classrooms/{classroom_id}/assignments/{assignment_id}/restore",
    response_model=AssignmentResponse,
)
async def restore(
    classroom_id: UUID,
    assignment_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomAssignmentService(session, user).restore(classroom_id, assignment_id)


@router.post(
    "/classroom-assignments/{assignment_id}/start",
    response_model=AssignmentStartResponse,
    status_code=201,
)
async def start(
    assignment_id: UUID,
    body: AssignmentStart,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomAssignmentService(session, user).start(assignment_id, body)


@router.get(
    "/classrooms/{classroom_id}/assignments/{assignment_id}/results",
    response_model=list[AssignmentResultSummary],
)
async def results(
    classroom_id: UUID,
    assignment_id: UUID,
    user: CurrentUser,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomResultService(session, user).list(
        classroom_id, assignment_id, limit=limit, offset=offset
    )


@router.get(
    "/classrooms/{classroom_id}/assignments/{assignment_id}/students/{student_id}/attempts",
    response_model=list[AssignmentResultSummary],
)
async def student_results(
    classroom_id: UUID,
    assignment_id: UUID,
    student_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomResultService(session, user).list(
        classroom_id, assignment_id, student_id=student_id
    )


@router.get(
    "/classrooms/{classroom_id}/assignments/{assignment_id}/attempts/{attempt_id}",
    response_model=AssignmentResultDetail,
)
async def result_detail(
    classroom_id: UUID,
    assignment_id: UUID,
    attempt_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassroomResultService(session, user).detail(
        classroom_id, assignment_id, attempt_id
    )


@router.put(
    "/classrooms/{classroom_id}/assignments/{assignment_id}/attempts/{attempt_id}/writing-scores/{writing_task_id}",
    response_model=WritingAttemptReview,
)
async def grade_writing(
    classroom_id: UUID,
    assignment_id: UUID,
    attempt_id: UUID,
    writing_task_id: UUID,
    body: WritingTaskScoreUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await AttemptService(
        session, user.id, grading_actor=user, grading_scope=(classroom_id, assignment_id)
    ).grade_writing_task(attempt_id, writing_task_id, body)


@router.put(
    "/classrooms/{classroom_id}/assignments/{assignment_id}/attempts/{attempt_id}/speaking-score",
    response_model=SpeakingReviewData,
)
async def grade_speaking(
    classroom_id: UUID,
    assignment_id: UUID,
    attempt_id: UUID,
    body: SpeakingScoreUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingFinalService(session, user).save(
        attempt_id, body, assignment_scope=(classroom_id, assignment_id)
    )
