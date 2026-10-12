from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.speaking import SpeakingRuntimeRoute
from app.core.config import get_settings
from app.core.database import SessionFactory, get_session
from app.core.exceptions import AppError
from app.repositories.speaking_ai import TERMINAL
from app.schemas.speaking_ai_runs import SpeakingAICreated, SpeakingAIRunData, SpeakingAIRunList
from app.services.speaking_ai import SpeakingAIService
from app.services.speaking_ai_worker import SpeakingAIWorker, cancel_speaking_ai_worker

router = APIRouter(
    prefix="/speaking-attempts", tags=["speaking-ai"], route_class=SpeakingRuntimeRoute
)


def get_speaking_ai_worker():
    return SpeakingAIWorker(SessionFactory, get_settings())


@router.post("/{attempt_id}/ai-runs", response_model=SpeakingAICreated)
async def create_run(
    attempt_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    worker: SpeakingAIWorker = Depends(get_speaking_ai_worker),
):
    created = await worker.service(session, user).create(attempt_id)
    if not created.cache_hit:
        worker.launch(created.run_id, restart=not created.existing_active)
    return created


@router.get("/{attempt_id}/ai-runs", response_model=SpeakingAIRunList)
async def latest_run(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return SpeakingAIRunList(
        run=await SpeakingAIService(session, user, get_settings()).latest(attempt_id)
    )


@router.get("/{attempt_id}/ai-runs/{run_id}", response_model=SpeakingAIRunData)
async def get_run(
    attempt_id: UUID, run_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await SpeakingAIService(session, user, get_settings()).get(attempt_id, run_id)


@router.post("/{attempt_id}/ai-runs/{run_id}/cancel", response_model=SpeakingAIRunData)
async def cancel_run(
    attempt_id: UUID, run_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    result = await SpeakingAIService(session, user, get_settings()).cancel(attempt_id, run_id)
    if result.status == "CANCELLED":
        cancel_speaking_ai_worker(run_id)
    return result


async def event_stream(request, aid, run_id, actor, worker, cursor):
    import asyncio

    while not await request.is_disconnected():
        async with worker.sessions() as session:
            run, events = await worker.service(session, actor).snapshot(aid, run_id, cursor)
        for event in events:
            cursor = event.sequence
            yield f"id: {cursor}\nevent: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
        if run.status in TERMINAL and len(events) < 100:
            return
        if not events:
            yield ": heartbeat\n\n"
        await asyncio.sleep(1)


@router.get("/{attempt_id}/ai-runs/{run_id}/events")
async def events(
    attempt_id: UUID,
    run_id: UUID,
    request: Request,
    user: CurrentUser,
    after: int = Query(default=0, ge=0, le=2147483647),
    last_event_id: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    worker: SpeakingAIWorker = Depends(get_speaking_ai_worker),
):
    await worker.service(session, user).get(attempt_id, run_id)
    try:
        header = int(last_event_id or 0)
        if not 0 <= header <= 2147483647:
            raise ValueError
        cursor = max(after, header)
    except ValueError:
        raise AppError(
            "INVALID_EVENT_CURSOR", "The grading event cursor is invalid.", 422
        ) from None
    return StreamingResponse(
        event_stream(request, attempt_id, run_id, user, worker, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )
