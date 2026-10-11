"""Private candidate media. Authorization always comes from DB provenance."""

import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import Attempt, ClassroomAssignment, TestSession
from app.models.speaking import (
    SpeakingAudioChunk,
    SpeakingAudioSegment,
    SpeakingMediaCleanup,
    SpeakingResponse,
    SpeakingResponseTake,
)
from app.schemas.speaking import (
    SpeakingChunkData,
    SpeakingManifest,
    SpeakingResponseData,
    SpeakingSegmentData,
)
from app.services.access_policy import AccessPolicy
from app.services.speaking_attempts import SpeakingAttemptService
from app.storage.local import LocalAssetStorage

MIMES = {"audio/webm", "audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"}


async def ordered_segments(session, take_id):
    return list(
        await session.scalars(
            select(SpeakingAudioSegment)
            .where(SpeakingAudioSegment.response_take_id == take_id)
            .order_by(SpeakingAudioSegment.segment_index)
        )
    )


async def ordered_chunks(session, segment_id):
    return list(
        await session.scalars(
            select(SpeakingAudioChunk)
            .where(SpeakingAudioChunk.segment_id == segment_id)
            .order_by(SpeakingAudioChunk.sequence)
        )
    )


async def committed_fingerprint(session, take):
    manifest = []
    for segment in await ordered_segments(session, take.id):
        chunks = await ordered_chunks(session, segment.id)
        if segment.chunk_count is None or [c.sequence for c in chunks] != list(
            range(segment.chunk_count)
        ):
            raise AppError(
                "SPEAKING_UPLOAD_INCOMPLETE", "Wait for recording upload acknowledgement.", 409
            )
        manifest.append([segment.segment_index, segment.mime_type, [c.sha256 for c in chunks]])
    return hashlib.sha256(
        json.dumps([str(take.id), take.take_number, manifest], separators=(",", ":")).encode()
    ).hexdigest()


async def queue_media_cleanup(session, attempt_ids):
    keys = list(
        await session.scalars(
            select(SpeakingAudioChunk.storage_key)
            .join(SpeakingAudioSegment, SpeakingAudioChunk.segment_id == SpeakingAudioSegment.id)
            .join(
                SpeakingResponseTake,
                SpeakingAudioSegment.response_take_id == SpeakingResponseTake.id,
            )
            .join(SpeakingResponse, SpeakingResponseTake.response_id == SpeakingResponse.id)
            .where(SpeakingResponse.attempt_id.in_(attempt_ids))
        )
    )
    for key in set(keys):
        await session.execute(
            insert(SpeakingMediaCleanup)
            .values(storage_key=key)
            .on_conflict_do_nothing(index_elements=["storage_key"])
        )


async def drain_media_cleanup(session, *, storage=None):
    storage = storage or LocalAssetStorage(get_settings().resolved_storage_root)
    async with session.begin():
        jobs = list(
            await session.scalars(
                select(SpeakingMediaCleanup).with_for_update(skip_locked=True).limit(100)
            )
        )
        for job in jobs:
            referenced = await session.scalar(
                select(SpeakingAudioChunk.id)
                .where(SpeakingAudioChunk.storage_key == job.storage_key)
                .limit(1)
            )
            if referenced is None:
                storage.delete(job.storage_key)
            await session.delete(job)


async def cleanup_private_media():
    """Startup/deletion hook; failed jobs remain durable for the next invocation."""
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    # Maintenance owns its short-lived connection; never borrow a connection tied
    # to another request/event loop (also supports startup/CLI invocation).
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:
            try:
                await drain_media_cleanup(session)
            except (OSError, AppError, SQLAlchemyError):
                pass  # Safe best effort; failed jobs remain in the outbox.
    finally:
        await engine.dispose()


class SpeakingMediaService:
    def __init__(self, session, actor, *, storage=None):
        self.session, self.actor = session, actor
        settings = get_settings()
        self.storage = storage or LocalAssetStorage(settings.resolved_storage_root)
        self.max_chunk_bytes = settings.speaking_max_chunk_bytes
        self.max_response_bytes = settings.speaking_max_response_bytes
        self.runtime = SpeakingAttemptService(session, actor.id)

    async def create_segment(self, aid, prompt_id, take_number, segment_index, mime_type):
        async with self.session.begin():
            attempt, progress, prompts = await self.runtime._load(aid)
            self.runtime._mutable(attempt)
            await self.runtime._require_current(attempt, progress, prompt_id, take_number)
            await self.runtime._synchronize(attempt, progress, prompts, TimerService.now())
            if (
                progress.phase != "RECORDING"
                or mime_type not in MIMES
                or not 0 <= segment_index <= 1000
            ):
                raise AppError(
                    "SPEAKING_RESPONSE_NOT_ACTIVE", "Recording is unavailable here.", 409
                )
            take = await self.runtime.repository.take(progress.response_id, take_number)
            segments = await ordered_segments(self.session, take.id)
            existing = next((s for s in segments if s.segment_index == segment_index), None)
            if existing:
                if existing.mime_type != mime_type:
                    raise AppError("SPEAKING_SEGMENT_CONFLICT", "Recording segment conflicts.", 409)
                return SpeakingSegmentData.model_validate(existing)
            if segment_index != len(segments):
                raise AppError(
                    "SPEAKING_SEGMENT_CONFLICT", "Recording segment order is invalid.", 409
                )
            segment = SpeakingAudioSegment(
                response_take_id=take.id, segment_index=segment_index, mime_type=mime_type
            )
            self.session.add(segment)
            await self.session.flush()
            progress.next_segment_index = segment_index + 1
            return SpeakingSegmentData.model_validate(segment)

    async def _segment(self, aid, segment_id):
        row = (
            await self.session.execute(
                select(SpeakingAudioSegment, SpeakingResponseTake, SpeakingResponse)
                .join(
                    SpeakingResponseTake,
                    SpeakingAudioSegment.response_take_id == SpeakingResponseTake.id,
                )
                .join(SpeakingResponse, SpeakingResponseTake.response_id == SpeakingResponse.id)
                .where(SpeakingAudioSegment.id == segment_id, SpeakingResponse.attempt_id == aid)
            )
        ).one_or_none()
        if row is None:
            raise AppError("SPEAKING_MEDIA_NOT_FOUND", "Recording not found.", 404)
        return row

    async def upload_chunk(self, aid, segment_id, sequence, content):
        if not 0 <= sequence <= 10000 or not 0 < len(content) <= self.max_chunk_bytes:
            raise AppError(
                "SPEAKING_UPLOAD_INVALID", "Invalid recording chunk size or sequence.", 422
            )
        stored = None
        try:
            async with self.session.begin():
                attempt, progress, prompts = await self.runtime._load(aid)
                segment, take, response = await self._segment(aid, segment_id)
                digest = hashlib.sha256(content).hexdigest()
                existing = await self.session.scalar(
                    select(SpeakingAudioChunk).where(
                        SpeakingAudioChunk.segment_id == segment_id,
                        SpeakingAudioChunk.sequence == sequence,
                    )
                )
                if existing:
                    if existing.sha256 != digest:
                        raise AppError(
                            "SPEAKING_CHUNK_SEQUENCE_CONFLICT",
                            "This chunk sequence has different content.",
                            409,
                        )
                    return SpeakingChunkData.model_validate(existing)
                self.runtime._mutable(attempt)
                await self.runtime._require_current(
                    attempt, progress, response.prompt_id, take.take_number
                )
                await self.runtime._synchronize(
                    attempt, progress, prompts, TimerService.now(), confirm=True
                )
                if (
                    response.locked
                    or take.status != "ACTIVE"
                    or segment.chunk_count is not None
                    or progress.phase not in {"RECORDING", "FINALIZING"}
                ):
                    raise AppError(
                        "SPEAKING_RESPONSE_NOT_ACTIVE", "This recording is no longer active.", 409
                    )
                size = await self.session.scalar(
                    select(func.coalesce(func.sum(SpeakingAudioChunk.byte_size), 0))
                    .join(
                        SpeakingAudioSegment,
                        SpeakingAudioChunk.segment_id == SpeakingAudioSegment.id,
                    )
                    .where(SpeakingAudioSegment.response_take_id == take.id)
                )
                if size + len(content) > self.max_response_bytes:
                    raise AppError("SPEAKING_UPLOAD_INVALID", "Recording size limit exceeded.", 422)
                stored = self.storage.store_private_speaking(
                    content, segment.mime_type, self.max_chunk_bytes
                )
                chunk = SpeakingAudioChunk(
                    segment_id=segment_id,
                    sequence=sequence,
                    storage_key=stored.relative_path,
                    sha256=digest,
                    byte_size=stored.size,
                )
                self.session.add(chunk)
                await self.session.flush()
                result = SpeakingChunkData.model_validate(chunk)
                attempt.last_active_at = TimerService.now()
            return result
        except Exception:
            if stored is not None:
                self.storage.delete(stored.relative_path)
            raise

    async def close_segment(self, aid, segment_id, chunk_count):
        async with self.session.begin():
            attempt, progress, _ = await self.runtime._load(aid)
            segment, take, response = await self._segment(aid, segment_id)
            if segment.chunk_count is not None:
                if segment.chunk_count != chunk_count:
                    raise AppError(
                        "SPEAKING_SEGMENT_CONFLICT", "Recording manifest conflicts.", 409
                    )
                return SpeakingSegmentData.model_validate(segment)
            self.runtime._mutable(attempt)
            await self.runtime._require_current(
                attempt, progress, response.prompt_id, take.take_number
            )
            chunks = await ordered_chunks(self.session, segment_id)
            if [c.sequence for c in chunks] != list(range(chunk_count)):
                raise AppError("SPEAKING_UPLOAD_INCOMPLETE", "Recording chunks are missing.", 409)
            segment.chunk_count, segment.closed_at = chunk_count, TimerService.now()
            return SpeakingSegmentData.model_validate(segment)

    async def _read_access(self, aid, response):
        attempt = await self.session.get(Attempt, aid)
        if attempt is None or attempt.module_type != "SPEAKING":
            raise AppError("SPEAKING_MEDIA_NOT_FOUND", "Recording not found.", 404)
        finalized = attempt.status not in {"IN_PROGRESS", "PAUSED"}
        if attempt.test_session_id:
            parent = await self.session.get(TestSession, attempt.test_session_id)
            finalized = finalized and parent.status != "IN_PROGRESS"
        if attempt.user_id == self.actor.id:
            if response.locked and finalized:
                return
            if not response.locked:
                progress = await self.runtime.repository.progress(aid)
                if (
                    self.runtime.mode(attempt) == "PRACTICE"
                    and progress
                    and progress.response_id == response.id
                    and progress.phase == "RECORDING"
                    and progress.phase_deadline_at > TimerService.now()
                ):
                    return
        elif finalized and response.locked:
            assignment_id = attempt.classroom_assignment_id
            if not assignment_id and attempt.test_session_id:
                assignment_id = parent.classroom_assignment_id
            if assignment_id and self.actor.role in {"TEACHER", "ADMIN"}:
                assignment = await self.session.get(ClassroomAssignment, assignment_id)
                if assignment:
                    await AccessPolicy(self.session, self.actor).require_assignment_view(assignment)
                    return
        raise AppError("SPEAKING_MEDIA_FORBIDDEN", "Recording access is unavailable.", 403)

    async def manifest(self, aid, response_id):
        async with self.session.begin():
            response = await self.session.get(SpeakingResponse, response_id)
            if response is None or response.attempt_id != aid:
                raise AppError("SPEAKING_MEDIA_NOT_FOUND", "Recording not found.", 404)
            playable = True
            try:
                await self._read_access(aid, response)
            except AppError:
                attempt = await self.session.get(Attempt, aid)
                progress = await self.runtime.repository.progress(aid)
                if (
                    attempt is None
                    or attempt.user_id != self.actor.id
                    or response.locked
                    or progress is None
                    or progress.response_id != response.id
                ):
                    raise
                playable = False  # Owner may restore metadata; exam audio stays unavailable.
            take = await self.runtime.repository.take(response.id, response.active_take_number)
            segments = []
            for segment in await ordered_segments(self.session, take.id):
                dto = SpeakingSegmentData.model_validate(segment)
                dto.chunks = [
                    SpeakingChunkData.model_validate(c)
                    for c in await ordered_chunks(self.session, segment.id)
                ]
                dto.content_url = (
                    f"/speaking-attempts/{aid}/segments/{segment.id}/content" if playable else None
                )
                segments.append(dto)
            return SpeakingManifest(
                response=SpeakingResponseData.model_validate(response), segments=segments
            )

    async def playback(self, aid, segment_id):
        async with self.session.begin():
            segment, take, response = await self._segment(aid, segment_id)
            await self._read_access(aid, response)
            if take.take_number != response.active_take_number or take.status == "SUPERSEDED":
                raise AppError("SPEAKING_MEDIA_FORBIDDEN", "Recording access is unavailable.", 403)
            return [
                self.storage.resolve(c.storage_key)
                for c in await ordered_chunks(self.session, segment.id)
            ], segment.mime_type

