from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser, CurrentUser
from app.core.database import get_session
from app.schemas.attempts import (
    ActivityRequest,
    AnswerResponse,
    AnswerUpdate,
    AttemptCreate,
    AttemptResponse,
    AttemptReview,
    NavigationRequest,
    WritingResponse,
    WritingResponseUpdate,
    WritingTaskScoreUpdate,
)
from app.schemas.content import (
    AttemptExam,
    FlagResponse,
    FlagUpdate,
    HighlightCreate,
    HighlightResponse,
    ListeningReview,
    ReadingReview,
    WritingAttemptReview,
)
from app.services.attempts import AttemptService

router = APIRouter(prefix="/attempts", tags=["attempts"])


@router.post("", response_model=AttemptResponse, status_code=status.HTTP_201_CREATED)
async def start_attempt(
    body: AttemptCreate, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> AttemptResponse:
    return await AttemptService(session, user.id).start(body)


@router.get("/{attempt_id}", response_model=AttemptResponse)
async def get_attempt(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> AttemptResponse:
    return await AttemptService(session, user.id).get(attempt_id)


@router.delete("/{attempt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attempt(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> Response:
    await AttemptService(session, user.id).delete_attempt(attempt_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{attempt_id}/activity", response_model=AttemptResponse)
async def record_activity(
    attempt_id: UUID,
    _: ActivityRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> AttemptResponse:
    return await AttemptService(session, user.id).record_activity(attempt_id)


@router.post("/{attempt_id}/navigation", response_model=AttemptResponse)
async def record_navigation(
    attempt_id: UUID,
    body: NavigationRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> AttemptResponse:
    return await AttemptService(session, user.id).record_navigation(attempt_id, body)


@router.post("/{attempt_id}/pause", response_model=AttemptResponse)
async def pause_attempt(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> AttemptResponse:
    return await AttemptService(session, user.id).pause(attempt_id)


@router.post("/{attempt_id}/resume", response_model=AttemptResponse)
async def resume_attempt(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> AttemptResponse:
    return await AttemptService(session, user.id).resume(attempt_id)


@router.put("/{attempt_id}/answers/{question_id}", response_model=AnswerResponse)
async def save_answer(
    attempt_id: UUID,
    question_id: UUID,
    body: AnswerUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> AnswerResponse:
    return await AttemptService(session, user.id).save_answer(
        attempt_id, question_id, body.value, body.expected_revision
    )


@router.put(
    "/{attempt_id}/writing/{writing_task_id}",
    response_model=WritingResponse,
)
async def save_writing_response(
    attempt_id: UUID,
    writing_task_id: UUID,
    body: WritingResponseUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> WritingResponse:
    return await AttemptService(session, user.id).save_writing_response(
        attempt_id, writing_task_id, body.content, body.expected_revision
    )


@router.post("/{attempt_id}/submit", response_model=AttemptResponse)
async def submit_attempt(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> AttemptResponse:
    return await AttemptService(session, user.id).submit(attempt_id)


@router.get("/{attempt_id}/review", response_model=AttemptReview)
async def review_attempt(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> AttemptReview:
    return await AttemptService(session, user.id).review(attempt_id)


@router.get("/{attempt_id}/exam", response_model=AttemptExam)
async def get_exam(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> AttemptExam:
    return await AttemptService(session, user.id).exam(attempt_id)


@router.get("/{attempt_id}/reading-review", response_model=ReadingReview)
async def get_reading_review(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> ReadingReview:
    return await AttemptService(session, user.id).reading_review(attempt_id)


@router.get("/{attempt_id}/listening-review", response_model=ListeningReview)
async def get_listening_review(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> ListeningReview:
    return await AttemptService(session, user.id).listening_review(attempt_id)


@router.get("/{attempt_id}/writing-review", response_model=WritingAttemptReview)
async def get_writing_review(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> WritingAttemptReview:
    return await AttemptService(session, user.id).writing_review(attempt_id)


@router.put(
    "/{attempt_id}/writing-scores/{writing_task_id}",
    response_model=WritingAttemptReview,
)
async def save_writing_task_score(
    attempt_id: UUID,
    writing_task_id: UUID,
    body: WritingTaskScoreUpdate,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> WritingAttemptReview:
    return await AttemptService(session, admin.id, allow_any_user=True).grade_writing_task(
        attempt_id, writing_task_id, body
    )


@router.put("/{attempt_id}/flags/{question_id}", response_model=FlagResponse)
async def save_flag(
    attempt_id: UUID,
    question_id: UUID,
    body: FlagUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> FlagResponse:
    return await AttemptService(session, user.id).save_flag(attempt_id, question_id, body.flagged)


@router.post(
    "/{attempt_id}/highlights",
    response_model=HighlightResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_highlight(
    attempt_id: UUID,
    body: HighlightCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> HighlightResponse:
    return await AttemptService(session, user.id).create_highlight(attempt_id, body)


@router.delete("/{attempt_id}/highlights/{highlight_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_highlight(
    attempt_id: UUID,
    highlight_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> Response:
    await AttemptService(session, user.id).delete_highlight(attempt_id, highlight_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{attempt_id}/highlights", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_highlights(
    attempt_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> Response:
    await AttemptService(session, user.id).delete_all_highlights(attempt_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
