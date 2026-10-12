"""Server-authoritative prompt execution. Audio transport is a separate concern.

All operations serialize on the owning Attempt row, including first progress
creation. Expiry stops recording in FINALIZING; only durable finish acknowledgement
locks/advances, leaving room for the recorder's last pending chunk to be accepted.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import (
    Attempt,
    SpeakingPrompt,
    SpeakingPromptProgress,
    SpeakingResponse,
    SpeakingResponseTake,
)
from app.models.enums import AttemptStatus, FinishedReason, ModuleType
from app.repositories.speaking import SpeakingRepository
from app.schemas.speaking import CurrentSpeakingPrompt, SpeakingState
from app.services.attempts import AttemptService


class SpeakingAttemptService:
    def __init__(self, session: AsyncSession, user_id: UUID | None = None):
        self.session = session
        self.user_id = user_id or session.info.get("current_user_id")
        if not isinstance(self.user_id, UUID):
            raise ValueError("SpeakingAttemptService requires an authenticated user id")
        self.repository = SpeakingRepository(session)

    async def _load(self, attempt_id: UUID):
        attempt = await self.repository.lock_attempt(attempt_id, self.user_id)
        if attempt is None or attempt.module_type != ModuleType.SPEAKING:
            raise AppError("ATTEMPT_NOT_FOUND", "The requested attempt does not exist.", 404)
        prompts = await self.repository.prompts(attempt)
        if not prompts:
            raise AppError("SPEAKING_MODULE_INCOMPLETE", "No Speaking prompts are available.", 409)
        progress = await self.repository.progress(attempt.id)
        if progress is None:
            progress = SpeakingPromptProgress(attempt_id=attempt.id, prompt_id=prompts[0].id)
            self.session.add(progress)
            await self.session.flush()
        return attempt, progress, prompts

    @staticmethod
    def mode(attempt: Attempt) -> str:
        # Full Mock always has exam restrictions, even if mode was set to practice.
        return "EXAM" if attempt.test_session_id is not None else (attempt.speaking_mode or "EXAM")

    @staticmethod
    def _mutable(attempt: Attempt):
        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise AppError("ATTEMPT_FINALIZED", "This attempt no longer accepts changes.", 409)

    @staticmethod
    def _prompt(progress, prompts) -> SpeakingPrompt | None:
        return next((p for p in prompts if p.id == progress.prompt_id), None)

    @staticmethod
    def _set_phase(progress, phase: str, now: datetime, seconds: int):
        progress.phase = phase
        progress.phase_started_at = now
        progress.phase_deadline_at = now + timedelta(seconds=seconds)
        progress.last_confirmed_remaining_ms = seconds * 1000
        progress.last_confirmed_at = now

    async def _synchronize(self, attempt, progress, prompts, now, *, confirm=False):
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return
        prompt = self._prompt(progress, prompts)
        if progress.phase == "RECOVERY_GRACE" and now >= progress.recovery_grace_deadline_at:
            start = progress.recovery_grace_deadline_at
            progress.phase = progress.recovery_phase
            progress.phase_started_at = start
            progress.phase_deadline_at = start + timedelta(
                milliseconds=progress.last_confirmed_remaining_ms
            )
            progress.last_resumed_at = start
            progress.recovery_state = "RESUMED"
            progress.last_confirmed_at = start
        if progress.phase == "PREPARING" and now >= progress.phase_deadline_at:
            self._set_phase(progress, "STARTING", progress.phase_deadline_at, 3)
        if progress.phase == "STARTING" and now >= progress.phase_deadline_at:
            start = progress.phase_deadline_at
            self._set_phase(progress, "RECORDING", start, prompt.response_seconds)
            take = await self.repository.take(progress.response_id, progress.take_number)
            take.started_at = start
        if progress.phase in {"PREPARING", "STARTING", "RECORDING"}:
            remaining = max(0, int((progress.phase_deadline_at - now).total_seconds() * 1000))
            if confirm:
                progress.last_confirmed_remaining_ms = min(
                    progress.last_confirmed_remaining_ms, remaining
                )
                progress.last_confirmed_at = now
            if progress.phase == "RECORDING" and remaining == 0:
                progress.phase = "FINALIZING"
        # Do not touch last_active_at on polling reads: heartbeats represent activity.

    def _state(self, attempt, progress, prompts, now) -> SpeakingState:
        prompt = self._prompt(progress, prompts)
        active = attempt.status == AttemptStatus.IN_PROGRESS
        can_repeat = active and self.mode(attempt) == "PRACTICE" and progress.phase == "RECORDING"
        current = None
        if active and prompt is not None:
            current = CurrentSpeakingPrompt(
                **{
                    name: getattr(prompt, name)
                    for name in (
                        "id",
                        "order_index",
                        "prompt_type",
                        "prompt_text",
                        "preparation_seconds",
                        "response_seconds",
                        "config_json",
                    )
                },
                part_number=prompt.part.part_number,
                part_title=prompt.part.title,
                instructions=prompt.part.instructions,
            )
        return SpeakingState(
            attempt_id=attempt.id,
            mode=self.mode(attempt),
            phase=progress.phase if active else "COMPLETED",
            current_prompt=current,
            response_id=progress.response_id if active else None,
            take_number=progress.take_number if active else None,
            phase_started_at=progress.phase_started_at if active else None,
            phase_deadline_at=progress.phase_deadline_at if active else None,
            remaining_ms=(
                min(
                    progress.last_confirmed_remaining_ms,
                    max(0, int((progress.phase_deadline_at - now).total_seconds() * 1000)),
                )
                if progress.phase in {"PREPARING", "STARTING", "RECORDING"}
                else 0
                if progress.phase == "FINALIZING"
                else progress.last_confirmed_remaining_ms
            )
            if active
            else 0,
            server_time=now,
            can_retry=can_repeat,
            can_replay=can_repeat,
            scratch_notes=progress.scratch_notes if active else "",
            interruption_generation=progress.interruption_generation,
            interruption_count=progress.interruption_count,
            recovery_state=progress.recovery_state,
            recovery_grace_used=progress.recovery_grace_used,
            last_resumed_at=progress.last_resumed_at,
            recovery_grace_deadline_at=progress.recovery_grace_deadline_at,
            recovery_allowed=active and progress.phase in {"INTERRUPTED", "RECOVERY_GRACE"},
            next_segment_index=progress.next_segment_index,
        )

    async def get_state(self, attempt_id: UUID) -> SpeakingState:
        async with self.session.begin():
            attempt, progress, prompts = await self._load(attempt_id)
            now = TimerService.now()
            await self._synchronize(attempt, progress, prompts, now)
            return self._state(attempt, progress, prompts, now)

    async def begin_prompt(self, attempt_id: UUID, prompt_id: UUID) -> SpeakingState:
        async with self.session.begin():
            attempt, progress, prompts = await self._load(attempt_id)
            self._mutable(attempt)
            now = TimerService.now()
            await self._synchronize(attempt, progress, prompts, now)
            await self._require_current(attempt, progress, prompt_id)
            if progress.phase == "QUESTION_ENTER":
                prompt = self._prompt(progress, prompts)
                response = SpeakingResponse(
                    attempt_id=attempt.id, prompt_id=prompt.id, started_at=now
                )
                self.session.add(response)
                await self.session.flush()
                self.session.add(
                    SpeakingResponseTake(response_id=response.id, take_number=1, started_at=now)
                )
                progress.response_id, progress.take_number = response.id, 1
                self._set_phase(
                    progress,
                    "PREPARING" if prompt.preparation_seconds else "RECORDING",
                    now,
                    prompt.preparation_seconds or prompt.response_seconds,
                )
            attempt.last_active_at = now
            return self._state(attempt, progress, prompts, now)

    async def _require_current(self, attempt, progress, prompt_id, take_number=None):
        if progress.prompt_id != prompt_id:
            prior = await self.repository.response(attempt.id, prompt_id)
            if prior is not None and prior.locked:
                raise AppError(
                    "SPEAKING_PREVIOUS_PROMPT_LOCKED", "This previous prompt is locked.", 409
                )
            raise AppError("SPEAKING_RESPONSE_NOT_ACTIVE", "This prompt is not active.", 409)
        if take_number is not None and progress.take_number != take_number:
            raise AppError("SPEAKING_RESPONSE_NOT_ACTIVE", "This response take is not active.", 409)

    async def heartbeat(
        self,
        attempt_id: UUID,
        prompt_id: UUID,
        take_number: int,
        *,
        client_remaining_ms: int | None = None,
    ) -> SpeakingState:
        async with self.session.begin():
            attempt, progress, prompts = await self._load(attempt_id)
            self._mutable(attempt)
            await self._require_current(attempt, progress, prompt_id, take_number)
            now = TimerService.now()
            # Client values are informational only, never authority for quota/deadlines.
            await self._synchronize(attempt, progress, prompts, now, confirm=True)
            attempt.last_active_at = now
            return self._state(attempt, progress, prompts, now)

    async def finish_current_response(
        self, attempt_id: UUID, prompt_id: UUID, take_number: int, completion_reason: str
    ) -> SpeakingState:
        async with self.session.begin():
            attempt, progress, prompts = await self._load(attempt_id)
            now = TimerService.now()
            response = await self.repository.response(attempt.id, prompt_id)
            # Idempotency is tied to the committed prompt/take, never "whatever is current".
            if (
                response is not None
                and response.locked
                and response.active_take_number == take_number
            ):
                await self._synchronize(attempt, progress, prompts, now)
                return self._state(attempt, progress, prompts, now)
            self._mutable(attempt)
            await self._require_current(attempt, progress, prompt_id, take_number)
            await self._synchronize(attempt, progress, prompts, now)
            if response is None or progress.phase not in {"RECORDING", "FINALIZING"}:
                raise AppError(
                    "SPEAKING_RESPONSE_NOT_ACTIVE", "Recording is not ready to finish.", 409
                )
            if completion_reason not in {"USER_DONE", "TIMEOUT"} or (
                completion_reason == "TIMEOUT" and progress.phase != "FINALIZING"
            ):
                raise AppError(
                    "SPEAKING_RESPONSE_NOT_ACTIVE", "The response deadline has not elapsed.", 409
                )
            reason = (
                "INTERRUPTED"
                if progress.recovery_state == "UNAVAILABLE"
                else "TIMEOUT"
                if progress.phase == "FINALIZING"
                else "USER_DONE"
            )
            take = await self.repository.take(response.id, take_number)
            from app.services.speaking_media import committed_fingerprint

            response.committed_audio_fingerprint = await committed_fingerprint(self.session, take)
            end = min(now, progress.phase_deadline_at)
            duration_ms = take.duration_ms + max(
                0, int((end - progress.phase_started_at).total_seconds() * 1000)
            )
            take.status, take.completed_at, take.duration_ms = "COMMITTED", end, duration_ms
            response.status, response.locked = "COMPLETED", True
            response.completed_at, response.duration_ms, response.completion_reason = (
                end,
                duration_ms,
                reason,
            )
            index = next(i for i, p in enumerate(prompts) if p.id == prompt_id)
            progress.prompt_id = prompts[index + 1].id if index + 1 < len(prompts) else None
            progress.response_id = progress.take_number = None
            progress.phase_started_at = progress.phase_deadline_at = None
            progress.last_confirmed_remaining_ms = 0
            progress.scratch_notes = ""
            progress.phase = "QUESTION_ENTER" if progress.prompt_id is not None else "COMPLETED"
            progress.recovery_state = None
            progress.recovery_grace_used = False
            progress.recovery_phase = progress.recovery_grace_deadline_at = (
                progress.interrupted_at
            ) = None
            progress.next_segment_index = 0
            attempt.last_active_at = now
            if progress.phase == "COMPLETED":
                AttemptService._finalize(
                    attempt,
                    status=AttemptStatus.SUBMITTED,
                    reason=FinishedReason.USER_SUBMIT,
                    now=now,
                )
                AttemptService._complete_mock_if_last_module(attempt, now)
            return self._state(attempt, progress, prompts, now)

    async def retry_current_response(
        self, attempt_id: UUID, prompt_id: UUID, take_number: int
    ) -> SpeakingState:
        async with self.session.begin():
            attempt, progress, prompts = await self._load(attempt_id)
            self._mutable(attempt)
            if self.mode(attempt) != "PRACTICE":
                raise AppError(
                    "SPEAKING_RETRY_NOT_ALLOWED", "Retry is available only in practice.", 409
                )
            await self._require_current(attempt, progress, prompt_id)
            now = TimerService.now()
            await self._synchronize(attempt, progress, prompts, now)
            if progress.phase != "RECORDING":
                raise AppError(
                    "SPEAKING_RETRY_NOT_ALLOWED", "Only an active recording may be retried.", 409
                )
            if progress.take_number == take_number + 1:
                return self._state(attempt, progress, prompts, now)
            await self._require_current(attempt, progress, prompt_id, take_number)
            response = await self.repository.response(attempt.id, prompt_id)
            take = await self.repository.take(response.id, take_number)
            take.status, take.completed_at = "SUPERSEDED", now
            take.duration_ms = max(0, int((now - take.started_at).total_seconds() * 1000))
            response.active_take_number += 1
            progress.take_number = response.active_take_number
            self.session.add(
                SpeakingResponseTake(
                    response_id=response.id, take_number=progress.take_number, started_at=now
                )
            )
            self._set_phase(
                progress, "RECORDING", now, self._prompt(progress, prompts).response_seconds
            )
            progress.recovery_state = None
            progress.recovery_grace_used = False
            progress.recovery_phase = progress.recovery_grace_deadline_at = (
                progress.interrupted_at
            ) = None
            progress.next_segment_index = 0
            attempt.last_active_at = now
            return self._state(attempt, progress, prompts, now)

    async def authorize_current_replay(self, attempt_id: UUID, prompt_id: UUID, take_number: int):
        async with self.session.begin():
            attempt, progress, prompts = await self._load(attempt_id)
            self._mutable(attempt)
            await self._require_current(attempt, progress, prompt_id, take_number)
            await self._synchronize(attempt, progress, prompts, TimerService.now())
            if self.mode(attempt) != "PRACTICE" or progress.phase != "RECORDING":
                raise AppError(
                    "SPEAKING_REPLAY_NOT_ALLOWED", "Replay is unavailable for this response.", 409
                )
            return progress.response_id

    async def save_notes(
        self, attempt_id: UUID, prompt_id: UUID, scratch_notes: str
    ) -> SpeakingState:
        async with self.session.begin():
            attempt, progress, prompts = await self._load(attempt_id)
            self._mutable(attempt)
            await self._require_current(attempt, progress, prompt_id)
            now = TimerService.now()
            await self._synchronize(attempt, progress, prompts, now)
            prompt = self._prompt(progress, prompts)
            if prompt.prompt_type != "LONG_TURN" or progress.phase not in {
                "PREPARING",
                "RECORDING",
                "STARTING",
                "INTERRUPTED",
                "RECOVERY_GRACE",
            }:
                raise AppError(
                    "SPEAKING_RESPONSE_NOT_ACTIVE", "Scratch notes are unavailable here.", 409
                )
            if len(scratch_notes) > 20000:
                raise AppError(
                    "SPEAKING_NOTES_TOO_LONG", "Scratch notes exceed the allowed length.", 422
                )
            progress.scratch_notes = scratch_notes
            attempt.last_active_at = now
            return self._state(attempt, progress, prompts, now)

    async def _seal_interrupted_segments(self, progress):
        from app.services.speaking_media import ordered_chunks, ordered_segments

        take = await self.repository.take(progress.response_id, progress.take_number)
        for segment in await ordered_segments(self.session, take.id):
            if segment.chunk_count is None:
                chunks = await ordered_chunks(self.session, segment.id)
                if [c.sequence for c in chunks] != list(range(len(chunks))):
                    raise AppError(
                        "SPEAKING_RECOVERY_NOT_AVAILABLE", "Recording recovery is unavailable.", 409
                    )
                segment.chunk_count, segment.closed_at = len(chunks), TimerService.now()

    async def interrupt(self, attempt_id, prompt_id, take_number, generation):
        unavailable = False
        async with self.session.begin():
            attempt, progress, prompts = await self._load(attempt_id)
            self._mutable(attempt)
            await self._require_current(attempt, progress, prompt_id, take_number)
            now = TimerService.now()
            if progress.recovery_state is not None:
                if generation not in {
                    progress.interruption_generation,
                    progress.interruption_generation - 1,
                }:
                    raise AppError(
                        "SPEAKING_RECOVERY_NOT_AVAILABLE", "Recovery generation is stale.", 409
                    )
                await self._synchronize(attempt, progress, prompts, now)
                if progress.phase in {"RECORDING", "PREPARING", "STARTING"}:
                    await self._seal_interrupted_segments(progress)
                return self._state(attempt, progress, prompts, now)
            if (
                generation != progress.interruption_generation
                or progress.phase not in {"PREPARING", "STARTING", "RECORDING"}
                or progress.phase_deadline_at <= now
                or progress.last_confirmed_at is None
            ):
                raise AppError(
                    "SPEAKING_RECOVERY_NOT_AVAILABLE", "Recording recovery is unavailable.", 409
                )
            await self._seal_interrupted_segments(progress)
            if progress.phase == "RECORDING":
                take = await self.repository.take(progress.response_id, take_number)
                take.duration_ms += max(
                    0,
                    int(
                        (progress.last_confirmed_at - progress.phase_started_at).total_seconds()
                        * 1000
                    ),
                )
            if (
                now - progress.last_confirmed_at
            ).total_seconds() > get_settings().speaking_recovery_window_seconds:
                progress.phase = "FINALIZING"
                progress.phase_started_at = progress.phase_deadline_at = now
                progress.last_confirmed_remaining_ms = 0
                progress.recovery_state = "UNAVAILABLE"
                unavailable = True
            else:
                progress.recovery_phase = progress.phase
                progress.phase = "INTERRUPTED"
                progress.interrupted_at = now
                progress.interruption_generation += 1
                progress.interruption_count += 1
                progress.recovery_state = "AWAITING_MICROPHONE"
            result = self._state(attempt, progress, prompts, now)
        if unavailable:
            raise AppError(
                "SPEAKING_RECOVERY_NOT_AVAILABLE", "The recovery window has expired.", 409
            )
        return result

    async def resume(self, attempt_id, prompt_id, take_number, generation):
        unavailable = False
        async with self.session.begin():
            attempt, progress, prompts = await self._load(attempt_id)
            self._mutable(attempt)
            await self._require_current(attempt, progress, prompt_id, take_number)
            now = TimerService.now()
            if generation != progress.interruption_generation or progress.recovery_state is None:
                raise AppError(
                    "SPEAKING_RECOVERY_NOT_AVAILABLE", "Recovery generation is stale.", 409
                )
            if progress.phase == "INTERRUPTED":
                if (
                    now - progress.interrupted_at
                ).total_seconds() > get_settings().speaking_recovery_window_seconds:
                    progress.phase = "FINALIZING"
                    progress.phase_started_at = progress.phase_deadline_at = now
                    progress.last_confirmed_remaining_ms = 0
                    progress.recovery_state = "UNAVAILABLE"
                    unavailable = True
                else:
                    progress.phase = "RECOVERY_GRACE"
                    progress.recovery_state = "GRACE"
                    progress.recovery_grace_used = True
                    progress.recovery_grace_deadline_at = now + timedelta(seconds=7)
            elif progress.phase not in {"RECOVERY_GRACE", "PREPARING", "STARTING", "RECORDING"}:
                raise AppError(
                    "SPEAKING_RECOVERY_NOT_AVAILABLE", "This response cannot be resumed.", 409
                )
            await self._synchronize(attempt, progress, prompts, now)
            result = self._state(attempt, progress, prompts, now)
        if unavailable:
            raise AppError(
                "SPEAKING_RECOVERY_NOT_AVAILABLE", "The recovery window has expired.", 409
            )
        return result
