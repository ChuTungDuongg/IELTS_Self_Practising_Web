"""Question-only CPU consumer reusing lexical ASR; no scorer or second ASR pipeline."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_questions import SpeakingBenchmarkQuestionJob as Job
from app.models.speaking_benchmark_questions import SpeakingBenchmarkQuestionRequest as Request
from app.schemas.speaking_benchmark_questions import QuestionConsent
from app.services.speaking_audio import await_audio_thread, fingerprint
from app.services.speaking_benchmark import SpeakingBenchmarkService, failure
from app.services.speaking_benchmark_questions import (
    TERMINAL,
    bound_input,
    build_proposals,
    check_consent,
    question_configuration,
    static_blockers,
)
from app.services.speaking_benchmark_questions_audio import materialize_source
from app.services.speaking_benchmark_questions_ledger import QuestionLedger
from app.services.speaking_benchmark_research import variant_settings
from app.storage.factory import get_asset_storage

LEASE_SECONDS = 90


class QuestionJobRunner:
    def __init__(self, factory, settings, *, storage=None, analyzer_factory=None):
        self.factory, self.settings = factory, settings
        self.storage = storage or get_asset_storage(settings)
        self.analyzer_factory = analyzer_factory

    def ledger(self, job_id, token):
        return QuestionLedger(
            self.factory, job_id, token, settings=self.settings, storage=self.storage
        )

    async def claim(self):
        now = datetime.now(UTC)
        async with self.factory() as session, session.begin():
            expired = list(
                await session.scalars(
                    select(Job)
                    .where(Job.status == "RUNNING", Job.lease_expires_at < now)
                    .with_for_update(skip_locked=True)
                )
            )
            for job in expired:
                unsettled = list(
                    await session.scalars(
                        select(Request).where(
                            Request.job_id == job.id,
                            Request.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
                        )
                    )
                )
                for request in unsettled:
                    if request.status == "ATTEMPTED":
                        request.status, request.error_code = (
                            "INTERRUPTED_BILLING_UNKNOWN",
                            "WORKER_LEASE_EXPIRED",
                        )
                job.status = "INTERRUPTED" if unsettled else "PENDING"
                job.lease_token, job.lease_expires_at = None, None
            await session.flush()
            other = aliased(Job)
            busy = (
                select(other.id)
                .where(other.sample_id == Job.sample_id, other.status == "RUNNING")
                .exists()
            )
            job = await session.scalar(
                select(Job)
                .join(Sample, Sample.id == Job.sample_id)
                .where(
                    Job.status == "PENDING",
                    ~busy,
                    Sample.deletion_pending_at.is_(None),
                )
                .order_by(Job.created_at, Job.id)
                .with_for_update(of=(Sample, Job), skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.status, job.lease_token = "RUNNING", uuid4()
            job.started_at = job.started_at or now
            job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            return job.id, job.lease_token

    async def heartbeat(self, job_id, token):
        async with self.factory() as session, session.begin():
            job = await self.ledger(job_id, token).guard(session)
            job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)

    async def finish(self, job_id, token, status, code=None):
        async with self.factory() as session, session.begin():
            sample_id = await session.scalar(select(Job.sample_id).where(Job.id == job_id))
            if sample_id:
                await session.get(Sample, sample_id, with_for_update=True)
            job = await session.get(Job, job_id, with_for_update=True)
            if (
                not job
                or job.status != "RUNNING"
                or job.lease_token != token
                or job.lease_expires_at <= datetime.now(UTC)
            ):
                return
            unsettled = list(
                await session.scalars(
                    select(Request).where(Request.job_id == job.id, Request.status == "ATTEMPTED")
                )
            )
            for request in unsettled:
                request.status = "INTERRUPTED_BILLING_UNKNOWN"
            if unsettled:
                status = "INTERRUPTED"
            if status in {"COMPLETED", "PARTIAL"}:
                # Guard source, review and lease before making proposals actionable.
                job = await self.ledger(job_id, token).guard(session)
                service = SpeakingBenchmarkService(
                    session, job.owner_id, settings=self.settings, storage=self.storage
                )
                _, _, _, draft = await bound_input(service, job)
                results = {
                    r.window_id: r.result
                    for r in await session.scalars(
                        select(Request)
                        .where(Request.job_id == job.id, Request.status == "COMPLETED")
                        .order_by(Request.created_at, Request.id)
                    )
                }
                job.proposals = build_proposals(job, draft, results)
            job.status, job.error_code = status, code
            job.lease_token, job.lease_expires_at = None, None
            job.finished_at = datetime.now(UTC) if status in TERMINAL else None

    async def execute(self, job_id, token):
        async with self.factory() as session, session.begin():
            job = await self.ledger(job_id, token).guard(session)
            consent = QuestionConsent.model_validate(
                {k: v for k, v in job.consent.items() if k in QuestionConsent.model_fields}
            )
            check_consent(job, consent)
            config = job.configuration["provider"]
            if question_configuration(
                self.settings, config["provider"]
            ) != config or static_blockers(self.settings, config):
                raise failure("SPEAKING_QUESTIONS_CONFIGURATION_UNAVAILABLE", 409)
            service = SpeakingBenchmarkService(
                session, job.owner_id, settings=self.settings, storage=self.storage
            )
            sample, _, result, _ = await bound_input(service, job)
            key, sha, duration, source_name = (
                sample.audio_key,
                sample.source_sha256,
                sample.duration_ms,
                result.source,
            )
            windows = job.windows
            seconds = job.configuration["provider_audio_ms"] / 1000
            job_fingerprint, draft_fingerprint = job.fingerprint, job.draft_fingerprint
        chosen = variant_settings(self.settings, config).model_copy(
            update={
                "speaking_lexical_asr_allow_additional_requests": True,
                "speaking_lexical_asr_allow_gpu": consent.modal_gpu,
                "speaking_lexical_asr_estimated_cost_usd_per_minute": consent.estimates_usd[
                    config["provider"]
                ]
                / seconds
                * 60,
                "speaking_lexical_asr_max_estimated_cost_usd_per_response": consent.max_estimated_cost_usd,
            }
        )
        from app.evaluation.speaking.replay_audio import normalize_window, pcm_digest
        from app.providers.speaking_asr.lexical import create_lexical_analyzer

        # Construction is delayed until a worker has a durable explicitly consented job.
        analyzer = (
            self.analyzer_factory(chosen, config["provider"])
            if self.analyzer_factory
            else create_lexical_analyzer(chosen, config["provider"])
        )
        ledger, partial = self.ledger(job_id, token), False
        async with materialize_source(self.storage, key, source_name, sha, duration, chosen) as (
            root,
            metadata,
            resolved,
        ):
            for index, window in enumerate(windows):
                await self.heartbeat(job_id, token)
                audio = await await_audio_thread(
                    asyncio.to_thread(
                        normalize_window,
                        root,
                        source_name,
                        metadata,
                        SimpleNamespace(**window),
                        root / f"examiner-{index}.wav",
                        resolved,
                    )
                )
                digest = await await_audio_thread(asyncio.to_thread(pcm_digest, audio))
                identity = fingerprint(
                    [QUESTION_PROTOCOL_ID, config, sha, draft_fingerprint, window, digest]
                )
                request_id, cached = await ledger.begin_or_reuse(window["id"], identity)
                if cached is not None:
                    partial |= cached["status"] != "COMPLETE"
                    continue
                started = time.monotonic()
                try:
                    mapping = audio.timeline[0]
                    result = await analyzer.analyze(
                        audio,
                        response_id=str(mapping.response_id),
                        take_number=mapping.take_number,
                        segment_id=str(mapping.segment_id),
                    )
                    if (
                        result.provider.model_dump(mode="json") != config["identity"]
                        or result.source.audio_fingerprint != sha
                        or result.source.normalized_audio_fingerprint != digest
                        or result.source.duration_ms != audio.duration_ms
                        or result.source.segment_id != str(mapping.segment_id)
                    ):
                        raise failure("SPEAKING_QUESTIONS_PROVIDER_EVIDENCE_INVALID", 409)
                    usage = result.usage.model_dump(mode="json") | {
                        "wall_latency_ms": round((time.monotonic() - started) * 1000)
                    }
                    if not result.coverage.stream_completed:
                        await ledger.interrupt(
                            request_id, result=result.model_dump(mode="json"), usage=usage
                        )
                        raise failure("SPEAKING_QUESTIONS_STREAM_INCOMPLETE", 409)
                    await ledger.complete(
                        request_id,
                        result.model_dump(mode="json"),
                        usage,
                        local=config["provider"] == "faster_whisper_local",
                    )
                    partial |= result.status != "COMPLETE"
                except BaseException:
                    await asyncio.shield(ledger.interrupt(request_id))
                    raise
        # The original job identity is also checked indirectly by guard + immutable config.
        if not job_fingerprint:
            raise failure("SPEAKING_QUESTIONS_SOURCE_CHANGED", 409)
        await self.finish(job_id, token, "PARTIAL" if partial else "COMPLETED")

    async def run_once(self):
        if not getattr(self.settings, "speaking_benchmark_questions_enabled", False) or not getattr(
            self.settings, "speaking_benchmark_questions_allow_live", False
        ):
            raise failure("SPEAKING_QUESTIONS_DISABLED", 503)
        claim = await self.claim()
        if claim is None:
            return False
        job_id, token = claim
        task = asyncio.create_task(self.execute(job_id, token))

        async def maintain():
            while True:
                await asyncio.sleep(20)
                try:
                    await self.heartbeat(job_id, token)
                except Exception:
                    task.cancel()
                    return

        pulse = asyncio.create_task(maintain())
        try:
            await task
        except BaseException as error:
            code = getattr(error, "code", "SPEAKING_QUESTIONS_EXECUTION_FAILED")
            async with self.factory() as session, session.begin():
                unknown = await session.scalar(
                    select(Request.id)
                    .where(
                        Request.job_id == job_id,
                        Request.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
                    )
                    .limit(1)
                )
            await asyncio.shield(
                self.finish(job_id, token, "INTERRUPTED" if unknown else "FAILED", code)
            )
            if isinstance(error, asyncio.CancelledError) and asyncio.current_task().cancelling():
                raise
        finally:
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)
        return True


QUESTION_PROTOCOL_ID = "speaking-question-assistant-v1"
