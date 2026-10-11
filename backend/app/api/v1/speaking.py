"""Speaking authoring and separately authorized private runtime routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_content_author
from app.core.config import get_settings
from app.core.database import get_session
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
    SpeakingSegmentClose,
    SpeakingSegmentCreate,
    SpeakingSegmentData,
    SpeakingState,
)
from app.services.speaking_attempts import SpeakingAttemptService
from app.services.speaking_builder import SpeakingBuilderService
from app.services.speaking_media import SpeakingMediaService

router = APIRouter(dependencies=[Depends(require_content_author)], tags=["speaking-builder"])
runtime_router = APIRouter(prefix="/speaking-attempts", tags=["speaking-runtime"])


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
