"""Detached workers with durable checkpoints and fenced DB leases. No scoring."""

import asyncio
from contextlib import suppress
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models.speaking import SpeakingPart, SpeakingPrompt, SpeakingResponse
from app.models.speaking_transcript import SpeakingTranscript, SpeakingTranscriptRun
from app.providers.speaking_asr import create_provider
from app.repositories.speaking_transcript import SpeakingTranscriptRepository
from app.schemas.speaking_ai import ASRResult
from app.services.speaking_audio import (
    execute_ffmpeg,
    normalization_identity,
    normalize_committed_take,
)
from app.services.speaking_features import build_feature_bundle, feature_identity
from app.services.speaking_quality import (
    assess_audio_quality,
    persist_quality_result,
    quality_identity,
)
from app.services.speaking_transcript import format_transcript, response_cache

_tasks: dict[UUID, asyncio.Task] = {}


class SpeakingTranscriptWorker:
    def __init__(self, sessions, settings, *, provider=None, storage=None, executor=execute_ffmpeg):
        self.sessions, self.settings = sessions, settings
        self.provider, self.storage, self.executor = provider, storage, executor

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

        task = asyncio.create_task(execute_after_cleanup(), name=f"speaking-transcript-{run_id}")
        _tasks[run_id] = task

        def discard(done):
            if not done.cancelled():
                done.exception()  # Consume failure without logging private exception/SQL bodies.
            if _tasks.get(run_id) is done:
                _tasks.pop(run_id, None)

        task.add_done_callback(discard)

    async def _checkpoint(
        self, run_id, token, rid=None, result=None, error=None, *, complete=False, evidence=None
    ):
        async with self.sessions() as session, session.begin():
            repository = SpeakingTranscriptRepository(session)
            run = await repository.run(run_id, lock=True)
            if not run or run.status != "RUNNING" or run.lease_token != token:
                return False
            run.heartbeat_at = TimerService.now()
            if rid:
                states = dict(run.responses_json)
                states[rid] = {"status": "READY" if result else "FAILED" if error else "PROCESSING"}
                if error:
                    states[rid]["error_code"] = error
                run.responses_json = states
                if result:
                    source = next(
                        m["audio_fingerprint"] for m in run.manifest_json if m["response_id"] == rid
                    )
                    for kind, text in [
                        ("VERBATIM", result.text),
                        ("CLEAN", format_transcript(result.text)),
                    ]:
                        await session.execute(
                            insert(SpeakingTranscript)
                            .values(
                                response_id=UUID(rid),
                                run_id=run.id,
                                cache_key=response_cache(source, run.identity_json),
                                source_audio_fingerprint=source,
                                kind=kind,
                                text=text,
                                word_timing_json=[w.model_dump() for w in result.words],
                                provider_json={
                                    "provider": result.provider,
                                    "model": result.model,
                                    "version": result.version,
                                    "language": result.language,
                                    "mean_confidence": result.mean_confidence,
                                    "evidence": evidence,
                                },
                            )
                            .on_conflict_do_nothing(
                                index_elements=["response_id", "cache_key", "kind"]
                            )
                        )
                await repository.append(
                    run, "response.updated", {"response_id": rid, **states[rid]}
                )
            if complete:
                ready = sum(s["status"] == "READY" for s in run.responses_json.values())
                run.status = (
                    "COMPLETED"
                    if ready == len(run.manifest_json)
                    else "PARTIAL"
                    if ready
                    else "FAILED"
                )
                run.lease_token = None
                await repository.append(run, "run.completed", {"status": run.status})
            return True

    async def _heartbeat(self, run_id, token):
        while True:
            await asyncio.sleep(5)
            if not await self._checkpoint(run_id, token):
                return

    async def execute(self, run_id):
        token, heartbeat = str(uuid4()), None
        async with self.sessions() as session, session.begin():
            repository = SpeakingTranscriptRepository(session)
            run = await repository.run(run_id, lock=True)
            if not run or run.status != "PENDING":
                return
            run.status, run.lease_token, run.heartbeat_at = "RUNNING", token, TimerService.now()
            await repository.append(run, "run.started")
            manifest, identity = run.manifest_json, run.identity_json
            ready = {rid for rid, value in run.responses_json.items() if value["status"] == "READY"}
        heartbeat = asyncio.create_task(self._heartbeat(run_id, token))
        try:
            provider = self.provider
            for item in manifest:
                rid = item["response_id"]
                if rid in ready:
                    continue
                if not await self._checkpoint(run_id, token, rid):
                    return
                audio, quality, asr_succeeded = None, None, False
                try:
                    provider = provider or create_provider(self.settings)
                    if (
                        provider.identity != identity["asr"]
                        or normalization_identity(self.settings) != identity["normalizer"]
                        or quality_identity(self.settings) != identity.get("quality")
                        or feature_identity(self.settings) != identity.get("features")
                    ):
                        raise AppError(
                            "TRANSCRIPT_CONFIGURATION_CHANGED",
                            "Transcription settings changed.",
                            409,
                        )
                    async with self.sessions() as session:
                        audio = await normalize_committed_take(
                            session,
                            UUID(rid),
                            self.settings,
                            storage=self.storage,
                            executor=self.executor,
                        )
                        async with session.begin():
                            prompt_context = (
                                await session.execute(
                                    select(SpeakingPart.part_number, SpeakingPrompt.prompt_type)
                                    .join(
                                        SpeakingPrompt,
                                        SpeakingPrompt.speaking_part_id == SpeakingPart.id,
                                    )
                                    .join(
                                        SpeakingResponse,
                                        SpeakingResponse.prompt_id == SpeakingPrompt.id,
                                    )
                                    .where(SpeakingResponse.id == UUID(rid))
                                )
                            ).one()
                            part_number = (
                                prompt_context[0] if prompt_context[1] == "LONG_TURN" else None
                            )
                    if audio.source_audio_fingerprint != item["audio_fingerprint"]:
                        raise AppError("TRANSCRIPT_SOURCE_CHANGED", "Recording changed.", 409)
                    quality = await asyncio.to_thread(
                        assess_audio_quality, audio, self.settings.speaking_quality
                    )
                    async with self.sessions() as session:
                        await persist_quality_result(session, audio, quality)
                    if not quality.assessable:
                        raise AppError(quality.state, "Recording quality is unavailable.", 409)
                    result = ASRResult.model_validate(
                        await asyncio.wait_for(
                            provider.transcribe(audio),
                            self.settings.speaking_processing_timeout_seconds,
                        )
                    )
                    if any(w.end > audio.duration_ms / 1000 for w in result.words):
                        raise ValueError("Word timing exceeds audio")
                    asr_succeeded = True
                    quality = await asyncio.to_thread(
                        assess_audio_quality, audio, self.settings.speaking_quality, asr_usable=True
                    )
                    async with self.sessions() as session:
                        await persist_quality_result(session, audio, quality)
                    bundle = await build_feature_bundle(
                        audio, result, self.settings, part_number=part_number
                    )
                    await self._checkpoint(
                        run_id, token, rid, result, evidence=bundle.model_dump(mode="json")
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    if audio and quality and quality.assessable and not asr_succeeded:
                        unusable = await asyncio.to_thread(
                            assess_audio_quality,
                            audio,
                            self.settings.speaking_quality,
                            asr_usable=False,
                        )
                        async with self.sessions() as session:
                            await persist_quality_result(session, audio, unusable)
                    # Allowlisted codes only: no transcript/input/exception body in events or logs.
                    code = (
                        error.code
                        if isinstance(error, AppError)
                        and error.code
                        in {
                            "SPEAKING_ASR_UNAVAILABLE",
                            "SPEAKING_AUDIO_UNASSESSABLE",
                            "TRANSCRIPT_SOURCE_CHANGED",
                            "TRANSCRIPT_CONFIGURATION_CHANGED",
                            "NO_SPEECH",
                            "TOO_SHORT",
                            "AUDIO_CORRUPT",
                            "VERY_LOW_SIGNAL",
                            "SEVERE_CLIPPING",
                            "BACKGROUND_DOMINANT",
                            "ASR_UNUSABLE",
                        }
                        else "TRANSCRIPT_GENERATION_FAILED"
                    )
                    await self._checkpoint(run_id, token, rid, error=code)
            await self._checkpoint(run_id, token, complete=True)
        except asyncio.CancelledError:
            # Preserve READY responses; leave unfinished work pending for startup recovery.
            async with self.sessions() as session, session.begin():
                run = await SpeakingTranscriptRepository(session).run(run_id, lock=True)
                if run and run.lease_token == token and run.status == "RUNNING":
                    run.status, run.lease_token = "PENDING", None
                    await SpeakingTranscriptRepository(session).append(run, "run.interrupted")
            raise
        finally:
            if heartbeat:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat

    async def recover(self):
        async with self.sessions() as session, session.begin():
            cutoff = TimerService.now() - timedelta(
                seconds=self.settings.speaking_transcript_stale_seconds
            )
            rows = list(
                await session.scalars(
                    select(SpeakingTranscriptRun)
                    .where(
                        (SpeakingTranscriptRun.status == "PENDING")
                        | (
                            (SpeakingTranscriptRun.status == "RUNNING")
                            & (SpeakingTranscriptRun.heartbeat_at < cutoff)
                        )
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            ids = []
            for run in rows:
                run.status, run.lease_token = "PENDING", None
                await SpeakingTranscriptRepository(session).append(run, "run.recovered")
                ids.append(run.id)
        for run_id in ids:
            self.launch(run_id)


def cancel_speaking_transcript_worker(run_id):
    task = _tasks.get(run_id)
    if task and not task.done():
        task.cancel()


async def stop_speaking_transcript_workers():
    tasks = list(_tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _tasks.clear()
