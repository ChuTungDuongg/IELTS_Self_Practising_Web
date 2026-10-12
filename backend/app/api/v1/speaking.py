"""Speaking authoring and separately authorized private runtime routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_content_author
from app.core.config import get_settings
from app.core.database import SessionFactory, get_session
from app.core.exceptions import AppError
from app.schemas.speaking import (
    BuilderSpeakingPart,
    SpeakingBegin,
    SpeakingChunkData,
    SpeakingCurrentTake,
    SpeakingFinish,
    SpeakingHeartbeat,
    SpeakingManifest,
    SpeakingNotes,
    SpeakingPartOrderWrite,
    SpeakingPartUpdate,
    SpeakingPartWrite,
    SpeakingPromptCreate,
    SpeakingPromptOrderWrite,
    SpeakingRecovery,
    SpeakingReviewData,
    SpeakingSegmentClose,
    SpeakingSegmentCreate,
    SpeakingSegmentData,
    SpeakingState,
)
from app.schemas.speaking_ai import TranscriptCreated, TranscriptRunData, TranscriptRunList
from app.services.speaking_attempts import SpeakingAttemptService
from app.services.speaking_builder import SpeakingBuilderService
from app.services.speaking_media import SpeakingMediaService
from app.services.speaking_transcript import TERMINAL, SpeakingTranscriptService
from app.services.speaking_transcript_worker import SpeakingTranscriptWorker


class SpeakingRuntimeRoute(APIRoute):
    """Sensitive runtime errors must never echo request inputs or DB parameters."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={
                        "code": "SPEAKING_REQUEST_INVALID",
                        "message": "The Speaking request is invalid.",
                    },
                )
            except (SQLAlchemyError, OSError):
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": "SPEAKING_STORAGE_UNAVAILABLE",
                        "message": "Speaking persistence is unavailable. Try again.",
                    },
                )

        return safe_handler


router = APIRouter(dependencies=[Depends(require_content_author)], tags=["speaking-builder"])
runtime_router = APIRouter(
    prefix="/speaking-attempts", tags=["speaking-runtime"], route_class=SpeakingRuntimeRoute
)


def get_transcript_worker():
    return SpeakingTranscriptWorker(SessionFactory, get_settings())


@runtime_router.post("/{attempt_id}/transcript-runs", response_model=TranscriptCreated)
async def create_transcript_run(
    attempt_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    worker: SpeakingTranscriptWorker = Depends(get_transcript_worker),
):
    result = await SpeakingTranscriptService(session, user, get_settings()).create(attempt_id)
    if not result.cache_hit:
        worker.launch(result.run_id, restart=not result.existing_active)
    return result


@runtime_router.get("/{attempt_id}/transcript-runs", response_model=TranscriptRunList)
async def latest_transcript_run(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return TranscriptRunList(
        run=await SpeakingTranscriptService(session, user, get_settings()).latest(attempt_id)
    )


@runtime_router.get("/{attempt_id}/transcript-runs/{run_id}", response_model=TranscriptRunData)
async def transcript_run(
    attempt_id: UUID, run_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await SpeakingTranscriptService(session, user, get_settings()).get(attempt_id, run_id)


async def transcript_event_stream(request, aid, run_id, actor, worker, cursor):
    import asyncio

    while not await request.is_disconnected():
        async with worker.sessions() as session:
            run, events = await SpeakingTranscriptService(session, actor, worker.settings).snapshot(
                aid, run_id, cursor
            )
        for event in events:
            cursor = event.sequence
            yield f"id: {cursor}\nevent: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
        if run.status in TERMINAL and len(events) < 100:
            return
        await asyncio.sleep(1)


@runtime_router.get("/{attempt_id}/transcript-runs/{run_id}/events")
async def transcript_events(
    attempt_id: UUID,
    run_id: UUID,
    request: Request,
    user: CurrentUser,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    worker: SpeakingTranscriptWorker = Depends(get_transcript_worker),
):
    await SpeakingTranscriptService(session, user, get_settings()).get(attempt_id, run_id)
    try:
        cursor = max(after, int(last_event_id or 0))
        if int(last_event_id or 0) < 0:
            raise ValueError
    except ValueError:
        raise AppError(
            "INVALID_EVENT_CURSOR", "The transcript event cursor is invalid.", 422
        ) from None
    return StreamingResponse(
        transcript_event_stream(request, attempt_id, run_id, user, worker, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )


@runtime_router.get("/{attempt_id}/review", response_model=SpeakingReviewData)
async def speaking_review(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await SpeakingMediaService(session, user).review(attempt_id)


@runtime_router.post("/{attempt_id}/interrupt", response_model=SpeakingState)
async def interrupt_recording(
    attempt_id: UUID,
    body: SpeakingRecovery,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingAttemptService(session, user.id).interrupt(
        attempt_id, body.prompt_id, body.take_number, body.interruption_generation
    )


@runtime_router.post("/{attempt_id}/resume", response_model=SpeakingState)
async def resume_recording(
    attempt_id: UUID,
    body: SpeakingRecovery,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingAttemptService(session, user.id).resume(
        attempt_id, body.prompt_id, body.take_number, body.interruption_generation
    )


@runtime_router.post("/{attempt_id}/segments", response_model=SpeakingSegmentData)
async def create_segment(
    attempt_id: UUID,
    body: SpeakingSegmentCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingMediaService(session, user).create_segment(
        attempt_id, body.prompt_id, body.take_number, body.segment_index, body.mime_type
    )


@runtime_router.put(
    "/{attempt_id}/segments/{segment_id}/chunks/{sequence}", response_model=SpeakingChunkData
)
async def upload_chunk(
    attempt_id: UUID,
    segment_id: UUID,
    sequence: int,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    maximum = get_settings().speaking_max_chunk_bytes
    data = bytearray()
    async for block in request.stream():
        if len(data) + len(block) > maximum:
            raise AppError("SPEAKING_UPLOAD_INVALID", "Recording chunk size exceeded.", 422)
        data.extend(block)
    return await SpeakingMediaService(session, user).upload_chunk(
        attempt_id, segment_id, sequence, bytes(data)
    )


@runtime_router.post(
    "/{attempt_id}/segments/{segment_id}/close", response_model=SpeakingSegmentData
)
async def close_segment(
    attempt_id: UUID,
    segment_id: UUID,
    body: SpeakingSegmentClose,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingMediaService(session, user).close_segment(
        attempt_id, segment_id, body.chunk_count
    )


@runtime_router.get(
    "/{attempt_id}/responses/{response_id}/manifest", response_model=SpeakingManifest
)
async def get_manifest(
    attempt_id: UUID,
    response_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingMediaService(session, user).manifest(attempt_id, response_id)


@runtime_router.get("/{attempt_id}/segments/{segment_id}/content")
async def get_recording(
    attempt_id: UUID,
    segment_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    paths, mime = await SpeakingMediaService(session, user).playback(attempt_id, segment_id)

    def content():
        for path in paths:
            with path.open("rb") as audio:
                while block := audio.read(64 * 1024):
                    yield block

    return StreamingResponse(
        content(),
        media_type=mime,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@runtime_router.get("/{attempt_id}/state", response_model=SpeakingState)
async def get_state(
    attempt_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await SpeakingAttemptService(session, user_id=user.id).get_state(attempt_id)


@runtime_router.post("/{attempt_id}/begin", response_model=SpeakingState)
async def begin_prompt(
    attempt_id: UUID,
    body: SpeakingBegin,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingAttemptService(session, user_id=user.id).begin_prompt(
        attempt_id, body.prompt_id
    )


@runtime_router.post("/{attempt_id}/heartbeat", response_model=SpeakingState)
async def heartbeat(
    attempt_id: UUID,
    body: SpeakingHeartbeat,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingAttemptService(session, user_id=user.id).heartbeat(
        attempt_id, body.prompt_id, body.take_number, client_remaining_ms=body.client_remaining_ms
    )


@runtime_router.post("/{attempt_id}/finish", response_model=SpeakingState)
async def finish_response(
    attempt_id: UUID,
    body: SpeakingFinish,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingAttemptService(session, user_id=user.id).finish_current_response(
        attempt_id, body.prompt_id, body.take_number, body.completion_reason
    )


@runtime_router.post("/{attempt_id}/retry", response_model=SpeakingState)
async def retry_response(
    attempt_id: UUID,
    body: SpeakingCurrentTake,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingAttemptService(session, user_id=user.id).retry_current_response(
        attempt_id, body.prompt_id, body.take_number
    )


@runtime_router.put("/{attempt_id}/notes", response_model=SpeakingState)
async def save_notes(
    attempt_id: UUID,
    body: SpeakingNotes,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingAttemptService(session, user_id=user.id).save_notes(
        attempt_id, body.prompt_id, body.scratch_notes
    )


@router.post(
    "/speaking/modules/{module_id}/parts",
    response_model=BuilderSpeakingPart,
    status_code=status.HTTP_201_CREATED,
)
async def create_part(
    module_id: UUID,
    body: SpeakingPartWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).create_part(module_id, body)


@router.put("/speaking/modules/{module_id}/parts/order", response_model=list[BuilderSpeakingPart])
async def reorder_parts(
    module_id: UUID,
    body: SpeakingPartOrderWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).reorder_parts(module_id, body)


@router.put("/speaking/parts/{part_id}", response_model=BuilderSpeakingPart)
async def update_part(
    part_id: UUID,
    body: SpeakingPartUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).update_part(part_id, body)


@router.delete("/speaking/parts/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_part(
    part_id: UUID,
    user: CurrentUser,
    expected_revision: int = Query(ge=1),
    session: AsyncSession = Depends(get_session),
):
    await SpeakingBuilderService(session, actor=user).delete_part(
        part_id, expected_revision=expected_revision
    )


@router.post(
    "/speaking/parts/{part_id}/prompts",
    response_model=BuilderSpeakingPart,
    status_code=status.HTTP_201_CREATED,
)
async def create_prompt(
    part_id: UUID,
    body: SpeakingPromptCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).create_prompt(part_id, body)


@router.put("/speaking/parts/{part_id}/prompts/order", response_model=BuilderSpeakingPart)
async def reorder_prompts(
    part_id: UUID,
    body: SpeakingPromptOrderWrite,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).reorder_prompts(part_id, body)


@router.delete("/speaking/parts/{part_id}/prompts/{prompt_id}", response_model=BuilderSpeakingPart)
async def delete_prompt(
    part_id: UUID,
    prompt_id: UUID,
    user: CurrentUser,
    expected_revision: int = Query(ge=1),
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).delete_prompt(
        part_id, prompt_id, expected_revision=expected_revision
    )


@router.put("/speaking/parts/{part_id}/prompts/{prompt_id}", response_model=BuilderSpeakingPart)
async def update_prompt(
    part_id: UUID,
    prompt_id: UUID,
    body: SpeakingPromptCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await SpeakingBuilderService(session, actor=user).update_prompt(part_id, prompt_id, body)
