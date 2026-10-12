"""Fenced durable grading jobs. Observer lifetime does not own processing."""

import asyncio
from contextlib import suppress
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import User
from app.models.speaking import SpeakingPart, SpeakingPrompt, SpeakingResponse
from app.models.speaking_ai import SpeakingAIGradingRun
from app.models.speaking_transcript import SpeakingTranscript
from app.providers.speaking_llm import create_provider
from app.repositories.speaking_ai import SpeakingAIRepository
from app.schemas.speaking_grading import CRITERIA, CriterionResult
from app.services.speaking_ai import SpeakingAIService
from app.services.speaking_scorer import SpeakingScorer, build_attempt_evidence, speaking_overall
from app.services.speaking_transcript import SpeakingTranscriptService, response_cache
from app.services.speaking_transcript_worker import SpeakingTranscriptWorker

_tasks: dict[UUID, asyncio.Task] = {}


class GradingStopped(Exception):
    pass


class SpeakingAIWorker:
    def __init__(
        self,
        sessions,
        settings,
        *,
        scorer=None,
        llm_identity=None,
        transcript_identity=None,
        transcript_worker=None,
    ):
        self.sessions, self.settings = sessions, settings
        self.scorer, self.llm_identity, self.transcript_identity = (
            scorer,
            llm_identity,
            transcript_identity,
        )
        self.transcript_worker = transcript_worker or SpeakingTranscriptWorker(sessions, settings)

    def service(self, session, actor):
        return SpeakingAIService(
            session,
            actor,
            self.settings,
            llm_identity=self.llm_identity,
            transcript_identity=self.transcript_identity,
        )

    def transcript_service(self, session, actor):
        return SpeakingTranscriptService(
            session, actor, self.settings, identity=self.transcript_identity
        )

    def launch(self, run_id, *, restart=False):
        previous = _tasks.get(run_id)
        if previous and not previous.done():
            if not restart and not previous.cancelling():
                return
            if not previous.cancelling():
                previous.cancel()

        async def execute_after_cleanup():
            if previous and not previous.done():
                await asyncio.gather(previous, return_exceptions=True)
            await self.execute(run_id)

        task = asyncio.create_task(execute_after_cleanup(), name=f"speaking-ai-{run_id}")
        _tasks[run_id] = task

        def discard(done):
            if not done.cancelled():
                done.exception()  # Never log exception SQL/provider/input bodies.
            if _tasks.get(run_id) is done:
                _tasks.pop(run_id, None)

        task.add_done_callback(discard)

    async def _locked(self, session, run_id, token):
        run = await SpeakingAIRepository(session).run(run_id, lock=True)
        if not run or run.status != "RUNNING" or run.lease_token != token:
            raise GradingStopped()
        if self.service(session, None).identity != run.identity_json:
            raise AppError(
                "SPEAKING_AI_CONFIGURATION_CHANGED", "Speaking configuration changed.", 409
            )
        rows = await session.scalars(
            select(SpeakingResponse)
            .where(SpeakingResponse.attempt_id == run.attempt_id)
            .order_by(SpeakingResponse.id)
        )
        current = [
            {"response_id": str(r.id), "audio_fingerprint": r.committed_audio_fingerprint}
            for r in rows
            if r.locked
        ]
        if current != run.manifest_json:
            raise AppError("SPEAKING_AI_SOURCE_CHANGED", "Committed recording changed.", 409)
        run.heartbeat_at = TimerService.now()
        return run

    async def _stage(self, run_id, token, stage, criterion=None):
        async with self.sessions() as session, session.begin():
            run = await self._locked(session, run_id, token)
            run.stage = stage
            payload = {"stage": stage}
            if criterion:
                payload["criterion"] = criterion
                previous = run.criteria_json.get(criterion, {})
                if stage == "SCORING" and previous.get("score") is None:
                    run.criteria_json = {
                        **run.criteria_json,
                        criterion: {**previous, "status": "SCORING"},
                    }
            await SpeakingAIRepository(session).append(run, "run.stage", payload)

    async def _persist(self, run_id, token, result):
        result = CriterionResult.model_validate(result)
        async with self.sessions() as session, session.begin():
            run = await self._locked(session, run_id, token)
            run.criteria_json = {
                **run.criteria_json,
                result.criterion: result.model_dump(mode="json"),
            }
            event = "criterion.score" if result.status == "SCORE_READY" else "criterion.feedback"
            await SpeakingAIRepository(session).append(
                run, event, {"criterion": result.criterion, "status": result.status}
            )
            if result.status == "SCORE_READY":
                run.stage = "GENERATING_FEEDBACK"
                await SpeakingAIRepository(session).append(
                    run, "run.stage", {"stage": run.stage, "criterion": result.criterion}
                )

    async def _heartbeat(self, run_id, token, owner):
        while True:
            await asyncio.sleep(5)
            try:
                async with self.sessions() as session, session.begin():
                    await self._locked(session, run_id, token)
            except AppError as error:
                await self._fail(run_id, token, error.code)
                owner.cancel()
                return
            except GradingStopped:
                owner.cancel()
                return

    async def _ensure_transcript(self, aid, actor):
        async with self.sessions() as session:
            created = await self.transcript_service(session, actor).create(aid)
        if not created.cache_hit:
            self.transcript_worker.launch(created.run_id, restart=not created.existing_active)
        deadline = (
            asyncio.get_running_loop().time() + self.settings.speaking_ai_transcript_wait_seconds
        )
        recheck_at = asyncio.get_running_loop().time() + 30
        while True:
            async with self.sessions() as session:
                snapshot = await self.transcript_service(session, actor).get(aid, created.run_id)
            if snapshot.status == "COMPLETED":
                return snapshot
            if snapshot.status in {"FAILED", "PARTIAL"}:
                quality_codes = {
                    "NO_SPEECH",
                    "TOO_SHORT",
                    "AUDIO_CORRUPT",
                    "VERY_LOW_SIGNAL",
                    "SEVERE_CLIPPING",
                    "BACKGROUND_DOMINANT",
                    "ASR_UNUSABLE",
                    "SPEAKING_AUDIO_UNASSESSABLE",
                }
                if any(r.error_code in quality_codes for r in snapshot.responses):
                    raise AppError(
                        "SPEAKING_AUDIO_UNASSESSABLE",
                        "Audio quality does not support assessment.",
                        409,
                    )
                raise AppError(
                    "SPEAKING_AI_TRANSCRIPT_UNAVAILABLE",
                    "Complete response transcripts are unavailable.",
                    409,
                )
            if asyncio.get_running_loop().time() >= deadline:
                raise AppError(
                    "SPEAKING_AI_TRANSCRIPT_TIMEOUT", "Transcript processing is unavailable.", 503
                )
            if asyncio.get_running_loop().time() >= recheck_at:
                # A crashed ASR lease may become stale after startup recovery's scan.
                async with self.sessions() as session:
                    current = await self.transcript_service(session, actor).create(aid)
                if not current.cache_hit:
                    self.transcript_worker.launch(
                        current.run_id, restart=not current.existing_active
                    )
                recheck_at = asyncio.get_running_loop().time() + 30
            await asyncio.sleep(0.25)

    async def _input(self, aid, actor, transcript_run):
        async with self.sessions() as session, session.begin():
            service = self.transcript_service(session, actor)
            responses = await service.authorized(aid)
            current = {r.id: r for r in responses}
            contexts = (
                await session.execute(
                    select(SpeakingResponse.id, SpeakingPrompt, SpeakingPart.part_number)
                    .join(SpeakingPrompt, SpeakingResponse.prompt_id == SpeakingPrompt.id)
                    .join(SpeakingPart, SpeakingPrompt.speaking_part_id == SpeakingPart.id)
                    .where(SpeakingResponse.attempt_id == aid, SpeakingResponse.locked.is_(True))
                    .order_by(
                        SpeakingPart.order_index, SpeakingPrompt.order_index, SpeakingResponse.id
                    )
                )
            ).all()
            data = []
            for rid, prompt, part_number in contexts:
                response = current[rid]
                rows = list(
                    await session.scalars(
                        select(SpeakingTranscript).where(
                            SpeakingTranscript.response_id == rid,
                            SpeakingTranscript.cache_key
                            == response_cache(
                                response.committed_audio_fingerprint, service.identity
                            ),
                        )
                    )
                )
                by_kind = {r.kind: r for r in rows}
                if {"VERBATIM", "CLEAN"} - by_kind.keys():
                    raise AppError(
                        "SPEAKING_AI_TRANSCRIPT_UNAVAILABLE",
                        "Current transcripts are unavailable.",
                        409,
                    )
                verbatim = by_kind["VERBATIM"]
                feature = verbatim.provider_json.get("evidence")
                if (
                    not feature
                    or feature.get("source_audio_fingerprint")
                    != response.committed_audio_fingerprint
                ):
                    raise AppError(
                        "SPEAKING_AUDIO_UNASSESSABLE", "Current audio evidence is unavailable.", 409
                    )
                data.append(
                    {
                        "response_id": rid,
                        "prompt_id": prompt.id,
                        "part_number": part_number,
                        "prompt_type": prompt.prompt_type,
                        "prompt_text": prompt.prompt_text,
                        "cue_points": prompt.config_json.get("cue_points", []),
                        "verbatim": verbatim.text,
                        "clean": by_kind["CLEAN"].text,
                        "words": verbatim.word_timing_json,
                        "features": feature,
                    }
                )
            if (
                sum(len(r["verbatim"]) + len(r["clean"]) + len(r["prompt_text"]) for r in data)
                > self.settings.speaking_ai_max_input_characters
            ):
                raise AppError(
                    "SPEAKING_AI_INPUT_TOO_LONG",
                    "The full Speaking input exceeds the configured budget.",
                    422,
                )
        return build_attempt_evidence(data)

    async def _finish(self, run_id, token):
        async with self.sessions() as session, session.begin():
            run = await self._locked(session, run_id, token)
            mean, band = speaking_overall(
                {trait: run.criteria_json.get(trait, {}).get("score") for trait in CRITERIA}
            )
            run.raw_mean, run.overall_band = mean, band
            run.status = run.stage = "COMPLETED" if band is not None else "FAILED"
            run.error_code = None if band is not None else "SPEAKING_AI_CRITERION_UNAVAILABLE"
            run.completed_at, run.lease_token = TimerService.now(), None
            await SpeakingAIRepository(session).append(
                run, "run.completed" if band is not None else "run.failed", {"status": run.status}
            )

    async def _fail(self, run_id, token, code):
        async with self.sessions() as session, session.begin():
            run = await SpeakingAIRepository(session).run(run_id, lock=True)
            if run and run.status == "RUNNING" and run.lease_token == token:
                run.status = run.stage = "FAILED"
                run.completed_at, run.lease_token = TimerService.now(), None
                run.error_code = code
                if code in {
                    "SPEAKING_AUDIO_UNASSESSABLE",
                    "SPEAKING_AI_TRANSCRIPT_UNAVAILABLE",
                    "SPEAKING_ASR_UNAVAILABLE",
                }:
                    run.criteria_json = {
                        trait: run.criteria_json.get(trait)
                        if run.criteria_json.get(trait, {}).get("score") is not None
                        else {
                            "criterion": trait,
                            "status": "UNAVAILABLE",
                            "score": None,
                            "feedback_status": "UNAVAILABLE",
                            "error_code": code,
                        }
                        for trait in CRITERIA
                    }
                await SpeakingAIRepository(session).append(run, "run.failed", {"error_code": code})

    async def execute(self, run_id):
        token = str(uuid4())
        async with self.sessions() as session, session.begin():
            run = await SpeakingAIRepository(session).run(run_id, lock=True)
            if not run or run.status != "PENDING":
                return
            run.status, run.stage, run.lease_token = "RUNNING", "QUALITY_CHECK", token
            run.started_at = run.started_at or TimerService.now()
            run.heartbeat_at = TimerService.now()
            aid, stored = run.attempt_id, dict(run.criteria_json)
            actor = await session.get(User, run.requested_by_user_id)
            expected = self.service(session, actor).identity
            identity = run.identity_json
            await SpeakingAIRepository(session).append(run, "run.stage", {"stage": run.stage})
        heartbeat = asyncio.create_task(self._heartbeat(run_id, token, asyncio.current_task()))
        try:
            if expected != identity:
                raise AppError(
                    "SPEAKING_AI_CONFIGURATION_CHANGED", "Speaking configuration changed.", 409
                )
            scorer = self.scorer or SpeakingScorer(
                create_provider(self.settings),
                score_max_tokens=self.settings.speaking_ai_score_max_tokens,
                feedback_max_tokens=self.settings.speaking_ai_feedback_max_tokens,
            )
            await self._stage(run_id, token, "TRANSCRIBING")
            transcript = await self._ensure_transcript(aid, actor)
            await self._stage(run_id, token, "ANALYSING_AUDIO")
            evidence = await self._input(aid, actor, transcript)
            if any(
                not r.features.quality.assessable or r.features.quality.state != "AUDIO_OK"
                for r in evidence.responses
            ):
                raise AppError(
                    "SPEAKING_AUDIO_UNASSESSABLE", "Audio quality does not support assessment.", 409
                )
            await self._stage(run_id, token, "BUILDING_EVIDENCE")
            async with self.sessions() as session, session.begin():
                run = await self._locked(session, run_id, token)
                run.summary_json = {
                    "responses": [
                        {
                            "response_id": str(r.response_id),
                            "part_number": r.part_number,
                            "words_per_minute": r.features.fluency.words_per_minute,
                            "part2_sustained_seconds": r.features.fluency.part2_sustained_seconds,
                            "pronunciation_status": r.features.pronunciation.status,
                            "mean_alignment_confidence": r.features.pronunciation.mean_alignment_confidence,
                            "pitch_range_hz": r.features.pronunciation.pitch_range_hz,
                            "limitations": r.features.pronunciation.limitations,
                        }
                        for r in evidence.responses
                    ]
                }
            await scorer.provider.ensure_ready()
            for trait in CRITERIA:
                previous = stored.get(trait)
                if previous and previous["status"] in {"COMPLETED", "FEEDBACK_FAILED"}:
                    continue
                await self._stage(run_id, token, "SCORING", trait)
                if previous and previous.get("score") is not None:
                    await self._stage(run_id, token, "GENERATING_FEEDBACK", trait)
                    result = await scorer.feedback_for_scored(
                        trait, evidence, CriterionResult.model_validate(previous)
                    )
                else:

                    async def checkpoint(result):
                        await self._persist(run_id, token, result)

                    result = await scorer.score_criterion(trait, evidence, checkpoint)
                await self._persist(run_id, token, result)
            await self._finish(run_id, token)
        except GradingStopped:
            pass
        except asyncio.CancelledError:
            async with self.sessions() as session, session.begin():
                run = await SpeakingAIRepository(session).run(run_id, lock=True)
                if run and run.status == "RUNNING" and run.lease_token == token:
                    run.status = run.stage = "PENDING"
                    run.lease_token = None
                    await SpeakingAIRepository(session).append(run, "run.interrupted")
            raise
        except Exception as error:
            safe = {
                "SPEAKING_AI_CONFIGURATION_CHANGED",
                "SPEAKING_AI_SOURCE_CHANGED",
                "SPEAKING_AI_TRANSCRIPT_UNAVAILABLE",
                "SPEAKING_AI_TRANSCRIPT_TIMEOUT",
                "SPEAKING_AI_INPUT_TOO_LONG",
                "SPEAKING_AUDIO_UNASSESSABLE",
                "SPEAKING_ASR_UNAVAILABLE",
                "SPEAKING_AI_NOT_CONFIGURED",
            }
            await self._fail(
                run_id,
                token,
                error.code
                if isinstance(error, AppError) and error.code in safe
                else "SPEAKING_AI_GRADING_FAILED",
            )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def recover(self):
        async with self.sessions() as session, session.begin():
            cutoff = TimerService.now() - timedelta(seconds=self.settings.speaking_ai_stale_seconds)
            runs = list(
                await session.scalars(
                    select(SpeakingAIGradingRun)
                    .where(
                        (SpeakingAIGradingRun.status == "PENDING")
                        | (
                            (SpeakingAIGradingRun.status == "RUNNING")
                            & (SpeakingAIGradingRun.heartbeat_at < cutoff)
                        )
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            ids = []
            for run in runs:
                run.status = run.stage = "PENDING"
                run.lease_token = None
                await SpeakingAIRepository(session).append(run, "run.recovered")
                ids.append(run.id)
        for run_id in ids:
            self.launch(run_id)


def cancel_speaking_ai_worker(run_id):
    task = _tasks.get(run_id)
    if task:
        task.cancel()


async def stop_speaking_ai_workers():
    tasks = list(_tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
