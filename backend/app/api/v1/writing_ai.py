import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.config import get_settings
from app.core.database import SessionFactory, get_session
from app.core.exceptions import AppError
from app.models.enums import WritingAIRunStatus
from app.schemas.writing_ai import CreateRunRequest, CreateRunResponse, RunListResponse, RunResponse
from app.services.writing_ai import CANCELLATION_CODE, WritingAIService
from app.services.writing_ai_worker import WritingAIWorker

router = APIRouter(tags=["writing-ai"])


def get_worker() -> WritingAIWorker:
    return WritingAIWorker(SessionFactory, get_settings())


@router.post(
    "/attempts/{attempt_id}/writing/{writing_task_id}/ai-grading-runs",
    response_model=CreateRunResponse,
)
async def create_run(
    attempt_id: UUID,
    writing_task_id: UUID,
    body: CreateRunRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    worker: WritingAIWorker = Depends(get_worker),
) -> CreateRunResponse:
    result = await WritingAIService(session, user.id, get_settings()).create(
        attempt_id, writing_task_id, force=body.force
    )
    if not result.cache_hit and not result.existing_active:
        worker.launch(result.run_id)
    return result


@router.get(
    "/attempts/{attempt_id}/writing/{writing_task_id}/ai-grading-runs",
    response_model=RunListResponse,
)
async def list_runs(
    attempt_id: UUID,
    writing_task_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> RunListResponse:
    return await WritingAIService(session, user.id, get_settings()).list(
        attempt_id, writing_task_id
    )


@router.get("/ai-writing-grading-runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> RunResponse:
    return await WritingAIService(session, user.id, get_settings()).get(run_id)


@router.post("/ai-writing-grading-runs/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    worker: WritingAIWorker = Depends(get_worker),
) -> RunResponse:
    result = await WritingAIService(session, user.id, get_settings()).cancel(run_id)
    # Commit first. Other processes rely on the durable terminal state, while
    # this process can also interrupt an in-flight provider request immediately.
    if result.status == WritingAIRunStatus.FAILED and result.error_code == CANCELLATION_CODE:
        worker.cancel(run_id)
    return result


def replay_cursor(after: int, last_event_id: str | None) -> int:
    try:
        cursor = int(last_event_id) if last_event_id else 0
        if cursor < 0:
            raise ValueError
    except ValueError:
        raise AppError(
            "INVALID_EVENT_CURSOR", "Mốc phát lại tiến trình không hợp lệ.", 422
        ) from None
    return max(after, cursor)


async def event_stream(
    request: Request, run_id: UUID, user_id: UUID, after: int, worker: WritingAIWorker
):
    # New sessions per poll; the request's service session never escapes the route.
    while not await request.is_disconnected():
        async with worker.sessions() as session:
            run, events = await WritingAIService(session, user_id, worker.settings).snapshot(
                run_id, after
            )
        for event in events:
            after = event.sequence
            yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
        if (
            run.status in {WritingAIRunStatus.COMPLETED, WritingAIRunStatus.FAILED}
            and len(events) < 100
        ):
            return
        await asyncio.sleep(1)


@router.get("/ai-writing-grading-runs/{run_id}/events")
async def stream_events(
    run_id: UUID,
    request: Request,
    user: CurrentUser,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    worker: WritingAIWorker = Depends(get_worker),
) -> StreamingResponse:
    await WritingAIService(session, user.id, get_settings()).get(run_id)
    cursor = replay_cursor(after, last_event_id)
    return StreamingResponse(
        event_stream(request, run_id, user.id, cursor, worker),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
