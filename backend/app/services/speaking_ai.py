"""Private grading orchestration; advisory results never change official bands."""

from contextlib import nullcontext
from datetime import timedelta

from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models.speaking_ai import SpeakingAIGradingEvent, SpeakingAIGradingRun
from app.repositories.speaking_ai import ACTIVE, TERMINAL, SpeakingAIRepository
from app.schemas.speaking_ai_runs import (
    SpeakingAICreated,
    SpeakingAIEventData,
    SpeakingAIRunData,
    SpeakingCriterionProgress,
)
from app.services.speaking_audio import fingerprint
from app.services.speaking_transcript import SpeakingTranscriptService

TRAITS = ("fc", "lr", "gra", "pr")


class SpeakingAIService:
    def __init__(self, session, actor, settings, *, llm_identity=None, transcript_identity=None):
        self.session, self.actor, self.settings = session, actor, settings
        self.injected = llm_identity is not None
        self.transcripts = SpeakingTranscriptService(
            session, actor, settings, identity=transcript_identity
        )
        if llm_identity is None:
            from app.providers.speaking_llm import config_identity

            llm_identity = config_identity(settings)
        self.identity = {
            "llm": llm_identity,
            "transcript": self.transcripts.identity,
            "prompt_version": settings.speaking_ai_prompt_version,
            "rubric_version": settings.speaking_ai_rubric_version,
            "score_contract": "half-band-v1",
            "feedback_contract": "bounded-feedback-v1",
            "input_limit": settings.speaking_ai_max_input_characters,
        }
        self.repository = SpeakingAIRepository(session)

    async def manifest(self, aid, *, mutate=False):
        return self.transcripts.manifest(await self.transcripts.authorized(aid, mutate=mutate))

    async def create(self, aid):
        async with self.session.begin():
            manifest = await self.manifest(aid, mutate=True)
            key = fingerprint([manifest, self.identity])
            run = await self.session.scalar(
                select(SpeakingAIGradingRun)
                .where(
                    SpeakingAIGradingRun.attempt_id == aid, SpeakingAIGradingRun.cache_key == key
                )
                .with_for_update()
            )
            if run and run.status == "COMPLETED":
                return SpeakingAICreated(run_id=run.id, cache_hit=True, existing_active=False)
            now = TimerService.now()
            if (
                run
                and run.status in ACTIVE
                and (
                    run.heartbeat_at is None
                    or now - run.heartbeat_at
                    <= timedelta(seconds=self.settings.speaking_ai_stale_seconds)
                )
            ):
                return SpeakingAICreated(run_id=run.id, cache_hit=False, existing_active=True)
            if not self.injected:
                from app.providers.speaking_llm import create_provider

                create_provider(self.settings)  # Configuration only, no provider requests here.
            if not run:
                run = SpeakingAIGradingRun(
                    attempt_id=aid,
                    requested_by_user_id=self.actor.id,
                    cache_key=key,
                    identity_json=self.identity,
                    manifest_json=manifest,
                    status="PENDING",
                    stage="PENDING",
                )
                self.session.add(run)
                await self.session.flush()
            else:
                run.status = run.stage = "PENDING"
                run.error_code = run.completed_at = None
                run.raw_mean = run.overall_band = None
            run.lease_token, run.heartbeat_at = None, now
            await self.repository.append(run, "run.queued")
            return SpeakingAICreated(run_id=run.id, cache_hit=False, existing_active=False)

    async def owned_run(self, aid, run_id, *, mutate=False):
        await self.manifest(aid, mutate=mutate)
        run = await self.repository.run(run_id, lock=mutate)
        if not run or run.attempt_id != aid:
            raise AppError("SPEAKING_MEDIA_NOT_FOUND", "Speaking grading run not found.", 404)
        return run

    async def _snapshot(self, aid, run_id, after=0):
        current = await self.manifest(aid)
        # Keep criterion/status data and its event cursor in the same checkpoint.
        # Parallel observers may share this lock; worker writes wait until read ends.
        run = await self.repository.run(run_id, shared=True)
        if not run or run.attempt_id != aid:
            raise AppError("SPEAKING_MEDIA_NOT_FOUND", "Speaking grading run not found.", 404)
        stale = current != run.manifest_json
        criteria = {}
        for trait in TRAITS:
            stored = run.criteria_json.get(trait, {})
            feedback = stored.get("feedback") or {}
            result = SpeakingCriterionProgress(
                status={"SCORE_READY": "SCORED", "FEEDBACK_FAILED": "COMPLETED"}.get(
                    stored.get("status"), stored.get("status", "WAITING")
                ),
                score=stored.get("score"),
                feedback_status={"FAILED": "FALLBACK", "UNAVAILABLE": "FALLBACK"}.get(
                    stored.get("feedback_status"), stored.get("feedback_status", "PENDING")
                ),
                feedback=feedback.get("feedback"),
                strengths=feedback.get("strengths", []),
                improvements=feedback.get("improvements", []),
                error_code=stored.get("error_code"),
                evidence_summary={"response_count": len(run.manifest_json)},
            )
            if stale:
                result = SpeakingCriterionProgress(
                    status="UNAVAILABLE", error_code="SPEAKING_AI_SOURCE_CHANGED"
                )
            criteria[trait] = result
        sequence = (
            await self.session.scalar(
                select(func.max(SpeakingAIGradingEvent.sequence)).where(
                    SpeakingAIGradingEvent.run_id == run_id
                )
            )
            or 0
        )
        events = list(
            await self.session.scalars(
                select(SpeakingAIGradingEvent)
                .where(
                    SpeakingAIGradingEvent.run_id == run_id, SpeakingAIGradingEvent.sequence > after
                )
                .order_by(SpeakingAIGradingEvent.sequence)
                .limit(100)
            )
        )
        snapshot = SpeakingAIRunData(
            run_id=run.id,
            attempt_id=aid,
            status="FAILED" if stale else run.status,
            stage="FAILED" if stale else run.stage,
            cache_key=run.cache_key,
            last_sequence=sequence,
            criteria=criteria,
            summary={"responses": []} if stale else run.summary_json or {"responses": []},
            raw_mean=None if stale or run.raw_mean is None else float(run.raw_mean),
            overall_band=None if stale or run.overall_band is None else float(run.overall_band),
            error_code="SPEAKING_AI_SOURCE_CHANGED" if stale else run.error_code,
            created_at=run.created_at,
        )
        return snapshot, [SpeakingAIEventData.model_validate(e) for e in events]

    async def snapshot(self, aid, run_id, after=0):
        async with self.session.begin():
            return await self._snapshot(aid, run_id, after)

    async def get(self, aid, run_id):
        return (await self.snapshot(aid, run_id))[0]

    async def latest(self, aid):
        async with nullcontext() if self.session.in_transaction() else self.session.begin():
            manifest = await self.manifest(aid)
            run_id = await self.session.scalar(
                select(SpeakingAIGradingRun.id).where(
                    SpeakingAIGradingRun.attempt_id == aid,
                    SpeakingAIGradingRun.cache_key == fingerprint([manifest, self.identity]),
                )
            )
            return (await self._snapshot(aid, run_id))[0] if run_id else None

    async def cancel(self, aid, run_id):
        async with self.session.begin():
            run = await self.owned_run(aid, run_id, mutate=True)
            if run.status not in TERMINAL:
                run.status = run.stage = "CANCELLED"
                run.error_code = "SPEAKING_AI_GRADING_CANCELLED"
                run.completed_at = TimerService.now()
                run.lease_token = None
                await self.repository.append(run, "run.cancelled", {"status": "CANCELLED"})
        return await self.get(aid, run_id)
