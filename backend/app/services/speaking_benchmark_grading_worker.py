"""Separate CPU grading consumer; no HTTP task or diarization runtime required."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.speaking_benchmark import SpeakingBenchmarkSample
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingCheckpoint as Checkpoint
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark import SpeakingBenchmarkService, failure
from app.services.speaking_benchmark_audio import (
    load_approved_input,
    materialize_approved_audio,
    normalized_segment,
)
from app.services.speaking_benchmark_evidence import attempt_evidence, response_evidence
from app.services.speaking_benchmark_ledger import RequestLedger
from app.services.speaking_benchmark_preflight import (
    configuration,
    effective_settings,
    grading_availability,
)
from app.services.speaking_benchmark_providers import LedgerAnalyzer, LedgerSpeakingProvider
from app.services.speaking_benchmark_scoring import score_attempt
from app.services.speaking_hybrid import analyze_response
from app.storage.factory import get_asset_storage

LEASE_SECONDS = 90


class GradingJobRunner:
    def __init__(
        self,
        factory,
        settings,
        *,
        storage=None,
        pa_factory=None,
        lexical_factory=None,
        llm_factory=None,
    ):
        self.factory, self.settings = factory, settings
        self.storage = storage or get_asset_storage(settings)
        self.pa_factory, self.lexical_factory, self.llm_factory = (
            pa_factory,
            lexical_factory,
            llm_factory,
        )

    async def claim(self):
        from uuid import uuid4

        now = datetime.now(UTC)
        async with self.factory() as session, session.begin():
            expired = list(
                await session.scalars(
                    select(Run)
                    .where(Run.status == "RUNNING", Run.lease_expires_at < now)
                    .with_for_update(skip_locked=True)
                )
            )
            for run in expired:
                attempts = list(
                    await session.scalars(
                        select(Checkpoint).where(
                            Checkpoint.run_id == run.id,
                            Checkpoint.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
                        )
                    )
                )
                for attempt in attempts:
                    attempt.status, attempt.error_code = (
                        "INTERRUPTED_BILLING_UNKNOWN",
                        "WORKER_LEASE_EXPIRED",
                    )
                run.status = "INTERRUPTED" if attempts else "PENDING"
                run.error_code = "SPEAKING_BENCHMARK_BILLING_UNKNOWN" if attempts else None
                run.lease_token, run.lease_expires_at = None, None
            await session.flush()
            run = await session.scalar(
                select(Run)
                .join(SpeakingBenchmarkSample)
                .where(
                    Run.status == "PENDING", SpeakingBenchmarkSample.deletion_pending_at.is_(None)
                )
                .order_by(Run.created_at)
                .with_for_update(of=Run, skip_locked=True)
                .limit(1)
            )
            if run is None:
                return None
            run.status, run.stage, run.lease_token = "RUNNING", "validating", uuid4()
            run.heartbeat_at, run.lease_expires_at = now, now + timedelta(seconds=LEASE_SECONDS)
            run.started_at = run.started_at or now
            return run.id, run.lease_token

    async def heartbeat(self, run_id, token):
        async with self.factory() as session, session.begin():
            run = await RequestLedger(self.factory, run_id, token).guard(session)
            run.heartbeat_at = datetime.now(UTC)
            run.lease_expires_at = run.heartbeat_at + timedelta(seconds=LEASE_SECONDS)

    async def finish(self, run_id, token, prediction=None, code=None):
        async with self.factory() as session, session.begin():
            run = await session.get(Run, run_id, with_for_update=True)
            if (
                not run
                or run.status != "RUNNING"
                or run.lease_token != token
                or run.lease_expires_at <= datetime.now(UTC)
            ):
                return False
            attempts = list(
                await session.scalars(
                    select(Checkpoint).where(
                        Checkpoint.run_id == run_id,
                        Checkpoint.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
                    )
                )
            )
            # Reconciled old attempts do not block a successful replacement.
            unresolved = []
            for attempt in attempts:
                replacement = await session.scalar(
                    select(Checkpoint.id)
                    .where(
                        Checkpoint.run_id == run_id,
                        Checkpoint.stage == attempt.stage,
                        Checkpoint.identity == attempt.identity,
                        Checkpoint.attempt > attempt.attempt,
                        Checkpoint.status == "COMPLETED",
                    )
                    .limit(1)
                )
                if replacement is None:
                    unresolved.append(attempt)
            if unresolved:
                for attempt in unresolved:
                    attempt.status = "INTERRUPTED_BILLING_UNKNOWN"
                run.status, run.error_code = "INTERRUPTED", "SPEAKING_BENCHMARK_BILLING_UNKNOWN"
            elif prediction is not None:
                run.status = (
                    "COMPLETED"
                    if all(v["status"] == "COMPLETED" for v in prediction["criteria"].values())
                    else "PARTIAL"
                )
                run.prediction, run.progress = prediction, 100
                run.finished_at = datetime.now(UTC)
            else:
                run.status, run.error_code, run.finished_at = (
                    "FAILED",
                    code or "SPEAKING_BENCHMARK_GRADING_FAILED",
                    datetime.now(UTC),
                )
            run.stage, run.lease_token, run.lease_expires_at = run.status.lower(), None, None
            return True

    async def execute(self, run_id, token):
        from app.providers.speaking_asr.lexical import create_lexical_analyzer
        from app.providers.speaking_llm.configured import create_provider
        from app.providers.speech_analysis.azure import AzureSpeechAnalyzer

        async with self.factory() as session, session.begin():
            run = await RequestLedger(self.factory, run_id, token).guard(session)
            service = SpeakingBenchmarkService(
                session, run.owner_id, settings=self.settings, storage=self.storage
            )
            sample, review, manifest, warnings = await load_approved_input(
                service, run.sample_id, run.review_revision
            )
            lexical = run.configuration["lexical_provider"]
            config = configuration(self.settings, lexical)
            if (
                fingerprint(config) != run.config_fingerprint
                or review.fingerprint != run.manifest_fingerprint
            ):
                raise failure("SPEAKING_BENCHMARK_CONFIGURATION_CHANGED", 409)
            source, key = sample.source_sha256, sample.audio_key
        chosen = effective_settings(self.settings, lexical)
        readiness = grading_availability(self.settings)
        selected = next(p for p in readiness["providers"] if p["provider"] == lexical)
        if not selected["available"]:
            raise failure("SPEAKING_BENCHMARK_GRADING_UNAVAILABLE", 409)
        from app.schemas.speaking_benchmark_grading import Consent
        from app.services.speaking_benchmark_preflight import validate_consent

        validate_consent(
            Consent.model_validate(
                {k: v for k, v in run.consent.items() if k in Consent.model_fields}
            ),
            lexical,
        )
        ledger = RequestLedger(self.factory, run_id, token)
        pa = (self.pa_factory or AzureSpeechAnalyzer)(chosen)
        independent = (
            (self.lexical_factory or create_lexical_analyzer)(chosen)
            if lexical != "azure_pa"
            else None
        )
        rows = []
        async with materialize_approved_audio(self.storage, key, manifest, source, chosen) as (
            root,
            metadata,
            resolved,
        ):
            for index, segment in enumerate(manifest.segments):
                await self.heartbeat(run_id, token)
                audio = await normalized_segment(root, metadata, manifest, segment, index, resolved)
                speech = await analyze_response(
                    audio,
                    chosen,
                    analyzer=LedgerAnalyzer(pa, ledger, f"azure:{segment.id}", config["pa"]),
                )
                words = (
                    await analyze_response(
                        audio,
                        chosen,
                        analyzer=LedgerAnalyzer(
                            independent, ledger, f"lexical:{segment.id}", config["lexical"]
                        ),
                    )
                    if independent
                    else None
                )
                rows.append(await response_evidence(audio, segment, speech, words, chosen))
        evidence = attempt_evidence(rows, chosen)
        provider = LedgerSpeakingProvider(
            (self.llm_factory or create_provider)(chosen), ledger, config["scorer"]
        )
        prediction = await score_attempt(evidence, provider, ledger, config, chosen)
        prediction["limitations"] += warnings
        await self.finish(run_id, token, prediction)

    async def run_once(self):
        if not grading_availability(self.settings)["can_queue"]:
            raise failure("SPEAKING_BENCHMARK_GRADING_UNAVAILABLE", 503)
        claim = await self.claim()
        if not claim:
            return False
        run_id, token = claim
        task = asyncio.create_task(self.execute(run_id, token))

        async def maintain():
            while True:
                await asyncio.sleep(20)
                try:
                    await self.heartbeat(run_id, token)
                except Exception:
                    task.cancel()
                    return

        pulse = asyncio.create_task(maintain())
        try:
            await task
        except BaseException as error:
            await asyncio.shield(
                self.finish(
                    run_id,
                    token,
                    code="WORKER_INTERRUPTED"
                    if isinstance(error, asyncio.CancelledError)
                    else "SPEAKING_BENCHMARK_GRADING_FAILED",
                )
            )
            if isinstance(error, asyncio.CancelledError):
                raise
        finally:
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)
        return True
