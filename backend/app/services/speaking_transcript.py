"""Private transcript identity/authorization and durable run state, independent of scoring."""

from datetime import timedelta

from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import Attempt
from app.models.speaking import SpeakingResponse
from app.models.speaking_transcript import (
    SpeakingTranscript,
    SpeakingTranscriptEvent,
    SpeakingTranscriptRun,
)
from app.providers.speaking_asr import provider_identity
from app.repositories.speaking_transcript import SpeakingTranscriptRepository
from app.schemas.speaking_ai import (
    TranscriptCreated,
    TranscriptEventData,
    TranscriptResponse,
    TranscriptRunData,
    WordTiming,
)
from app.services.speaking_audio import fingerprint, normalization_identity
from app.services.speaking_media import SpeakingMediaService

TERMINAL = {"COMPLETED", "PARTIAL", "FAILED"}


def format_transcript(text: str) -> str:
    """Whitespace formatting only; preserve every candidate word/disfluency."""
    return " ".join(text.split())


def response_cache(source, identity):
    return fingerprint([source, identity])


class SpeakingTranscriptService:
    def __init__(self, session, actor, settings, *, identity=None):
        self.session, self.actor, self.settings = session, actor, settings
        self.injected = identity is not None
        self.identity = {
            "asr": identity or provider_identity(settings),
            "normalizer": normalization_identity(settings),
            "clean_version": "format-v1",
        }
        self.repository = SpeakingTranscriptRepository(session)

    async def authorized(self, aid, *, mutate=False):
        query = select(Attempt).where(Attempt.id == aid)
        attempt = await self.session.scalar(query.with_for_update() if mutate else query)
        if not attempt or attempt.module_type != "SPEAKING":
            raise AppError("SPEAKING_MEDIA_NOT_FOUND", "Speaking resource not found.", 404)
        if mutate and attempt.user_id != self.actor.id:
            raise AppError("SPEAKING_MEDIA_FORBIDDEN", "Transcription access is unavailable.", 403)
        if attempt.status in {"IN_PROGRESS", "PAUSED"}:
            raise AppError(
                "SPEAKING_REVIEW_UNAVAILABLE",
                "Finalize Speaking before generating transcripts.",
                409,
            )
        rows = list(
            await self.session.scalars(
                select(SpeakingResponse)
                .where(SpeakingResponse.attempt_id == aid, SpeakingResponse.locked.is_(True))
                .order_by(SpeakingResponse.id)
            )
        )
        if not rows or len(rows) > 1000:
            raise AppError(
                "SPEAKING_REVIEW_UNAVAILABLE", "Committed responses are unavailable.", 409
            )
        for response in rows:
            await SpeakingMediaService(self.session, self.actor)._read_access(aid, response)
        return rows

    def manifest(self, rows):
        return [
            {"response_id": str(r.id), "audio_fingerprint": r.committed_audio_fingerprint}
            for r in rows
        ]

    async def create(self, aid):
        async with self.session.begin():
            rows = await self.authorized(aid, mutate=True)
            manifest = self.manifest(rows)
            key = fingerprint([manifest, self.identity])
            run = await self.session.scalar(
                select(SpeakingTranscriptRun)
                .where(
                    SpeakingTranscriptRun.attempt_id == aid, SpeakingTranscriptRun.cache_key == key
                )
                .with_for_update()
            )
            if run and run.status == "COMPLETED":
                return TranscriptCreated(run_id=run.id, cache_hit=True, existing_active=False)
            now = TimerService.now()
            if (
                run
                and run.status in {"PENDING", "RUNNING"}
                and (
                    run.heartbeat_at is None
                    or now - run.heartbeat_at
                    <= timedelta(seconds=self.settings.speaking_transcript_stale_seconds)
                )
            ):
                return TranscriptCreated(run_id=run.id, cache_hit=False, existing_active=True)
            if not self.injected and (
                not self.settings.speaking_asr_enabled
                or not self.settings.speaking_asr_model_directory
            ):
                raise AppError(
                    "SPEAKING_ASR_UNAVAILABLE", "Local transcription is not configured.", 503
                )
            if run is None:
                run = SpeakingTranscriptRun(
                    attempt_id=aid,
                    requested_by_user_id=self.actor.id,
                    cache_key=key,
                    status="PENDING",
                    identity_json=self.identity,
                    manifest_json=manifest,
                    responses_json={
                        item["response_id"]: {"status": "WAITING"} for item in manifest
                    },
                )
                self.session.add(run)
                await self.session.flush()
            else:
                run.status = "PENDING"
                run.responses_json = {
                    rid: value if value["status"] == "READY" else {"status": "WAITING"}
                    for rid, value in run.responses_json.items()
                }
            run.lease_token = None
            run.heartbeat_at = now
            await self.repository.append(run, "run.queued")
            return TranscriptCreated(run_id=run.id, cache_hit=False, existing_active=False)

    async def _snapshot(self, aid, run_id, after=0):
        rows = await self.authorized(aid)
        current = {str(r.id): r.committed_audio_fingerprint for r in rows}
        run = await self.repository.run(run_id)
        if not run or run.attempt_id != aid:
            raise AppError("SPEAKING_MEDIA_NOT_FOUND", "Transcript run not found.", 404)
        responses = []
        for item in run.manifest_json:
            rid, source = item["response_id"], item["audio_fingerprint"]
            state = run.responses_json[rid]
            dto = TranscriptResponse(
                response_id=rid,
                source_audio_fingerprint=source,
                status=state["status"],
                error_code=state.get("error_code"),
            )
            if current.get(rid) != source:
                dto.status, dto.error_code = "FAILED", "TRANSCRIPT_SOURCE_CHANGED"
            elif dto.status == "READY":
                transcripts = list(
                    await self.session.scalars(
                        select(SpeakingTranscript).where(
                            SpeakingTranscript.response_id == dto.response_id,
                            SpeakingTranscript.cache_key
                            == response_cache(source, run.identity_json),
                        )
                    )
                )
                by_kind = {t.kind: t for t in transcripts}
                if "VERBATIM" in by_kind and "CLEAN" in by_kind:
                    dto.verbatim, dto.clean, dto.words = (
                        by_kind["VERBATIM"].text,
                        by_kind["CLEAN"].text,
                        [
                            WordTiming.model_validate(w)
                            for w in by_kind["VERBATIM"].word_timing_json
                        ],
                    )
                else:
                    dto.status, dto.error_code = "FAILED", "TRANSCRIPT_GENERATION_FAILED"
            responses.append(dto)
        sequence = (
            await self.session.scalar(
                select(func.max(SpeakingTranscriptEvent.sequence)).where(
                    SpeakingTranscriptEvent.run_id == run.id
                )
            )
            or 0
        )
        events = list(
            await self.session.scalars(
                select(SpeakingTranscriptEvent)
                .where(
                    SpeakingTranscriptEvent.run_id == run.id,
                    SpeakingTranscriptEvent.sequence > after,
                )
                .order_by(SpeakingTranscriptEvent.sequence)
                .limit(100)
            )
        )
        return TranscriptRunData(
            run_id=run.id,
            attempt_id=aid,
            status=run.status,
            cache_key=run.cache_key,
            last_sequence=sequence,
            responses=responses,
            created_at=run.created_at,
        ), [TranscriptEventData.model_validate(e) for e in events]

    async def snapshot(self, aid, run_id, after=0):
        async with self.session.begin():
            return await self._snapshot(aid, run_id, after)

    async def get(self, aid, run_id):
        return (await self.snapshot(aid, run_id))[0]

    async def latest(self, aid):
        async with self.session.begin():
            rows = await self.authorized(aid)
            key = fingerprint([self.manifest(rows), self.identity])
            run_id = await self.session.scalar(
                select(SpeakingTranscriptRun.id).where(
                    SpeakingTranscriptRun.attempt_id == aid, SpeakingTranscriptRun.cache_key == key
                )
            )
            return (await self._snapshot(aid, run_id))[0] if run_id else None
