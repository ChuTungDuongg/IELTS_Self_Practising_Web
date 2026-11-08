"""Separate CPU research consumer. ASR-only never imports the LLM provider."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRObservation as Observation
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperiment as Experiment
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperimentVariant as Variant
from app.schemas.speaking_benchmark_research import ResearchConsent
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark import SpeakingBenchmarkService, failure
from app.services.speaking_benchmark_audio import (
    load_approved_input,
    materialize_approved_audio,
    normalized_segment,
)
from app.services.speaking_benchmark_research import (
    TERMINAL,
    check_consent,
    static_blockers,
    variant_settings,
    variants_for,
)
from app.services.speaking_benchmark_research_ledger import ResearchLedger
from app.storage.factory import get_asset_storage

LEASE_SECONDS = 90


async def update_experiment(session, experiment_id):
    experiment = await session.get(Experiment, experiment_id, with_for_update=True)
    if not experiment or experiment.status in TERMINAL or experiment.status == "DRAFT":
        return
    states = [v.status for v in await variants_for(session, experiment_id)]
    if "INTERRUPTED" in states:
        experiment.status = "INTERRUPTED"
    elif states and all(s in TERMINAL for s in states):
        experiment.status = (
            "COMPLETED"
            if all(s == "COMPLETED" for s in states)
            else "PARTIAL"
            if any(s in {"COMPLETED", "PARTIAL"} for s in states)
            else "FAILED"
        )
        experiment.finished_at = datetime.now(UTC)
    else:
        experiment.status = "RUNNING"


async def cancel_sample_variants(session, sample_id):
    rows = list(
        await session.scalars(
            select(Variant).where(Variant.sample_id == sample_id).with_for_update()
        )
    )
    active = False
    for row in rows:
        unknowns = list(
            await session.scalars(
                select(Observation).where(
                    Observation.variant_id == row.id,
                    Observation.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
                )
            )
        )
        if row.status not in TERMINAL or unknowns:
            active = True
        if row.status not in TERMINAL:
            row.status, row.error_code, row.lease_token, row.lease_expires_at = (
                "CANCELLED",
                "SAMPLE_DELETED",
                None,
                None,
            )
        for observation in unknowns:
            if observation.status == "ATTEMPTED":
                observation.status = "INTERRUPTED_BILLING_UNKNOWN"
    await session.flush()
    for identifier in sorted({r.experiment_id for r in rows}, key=str):
        await update_experiment(session, identifier)
    return active


class ResearchJobRunner:
    def __init__(self, factory, settings, *, storage=None, analyzer_factory=None):
        self.factory, self.settings = factory, settings
        self.storage = storage or get_asset_storage(settings)
        self.analyzer_factory = analyzer_factory

    async def claim(self):
        now = datetime.now(UTC)
        async with self.factory() as session, session.begin():
            expired = list(
                await session.scalars(
                    select(Variant)
                    .where(Variant.status == "RUNNING", Variant.lease_expires_at < now)
                    .with_for_update(skip_locked=True)
                )
            )
            for row in expired:
                unsettled = list(
                    await session.scalars(
                        select(Observation).where(
                            Observation.variant_id == row.id,
                            Observation.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
                        )
                    )
                )
                for observation in unsettled:
                    observation.status, observation.error_code = (
                        "INTERRUPTED_BILLING_UNKNOWN",
                        "WORKER_LEASE_EXPIRED",
                    )
                row.status = (
                    "INTERRUPTED" if unsettled else "WAITING" if row.grading_run_id else "PENDING"
                )
                row.lease_token, row.lease_expires_at = None, None
            await session.flush()
            for identifier in sorted({r.experiment_id for r in expired}, key=str):
                await update_experiment(session, identifier)
            # Nonblocking claims. Sample-level locks are acquired only in guard/admission.
            other = aliased(Variant)
            busy_sample = (
                select(other.id)
                .where(other.sample_id == Variant.sample_id, other.status == "RUNNING")
                .exists()
            )
            grading_busy = (
                select(Run.id)
                .where(
                    Run.sample_id == Variant.sample_id,
                    Run.status.in_(["PENDING", "RUNNING", "INTERRUPTED"]),
                )
                .exists()
            )
            row = await session.scalar(
                select(Variant)
                .join(Experiment)
                .join(Sample, Sample.id == Variant.sample_id)
                .where(
                    (
                        (Variant.status == "PENDING")
                        | (
                            (Variant.status == "WAITING")
                            & (Variant.updated_at < now - timedelta(seconds=5))
                        )
                    ),
                    ~busy_sample,
                    ((Experiment.mode == "PAIRED_GRADING") | ~grading_busy),
                    Experiment.status.in_(["PENDING", "RUNNING"]),
                    Sample.deletion_pending_at.is_(None),
                )
                .order_by(Variant.updated_at, Variant.id)
                .with_for_update(of=(Sample, Variant), skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            row.status, row.lease_token = "RUNNING", uuid4()
            row.started_at = row.started_at or now
            row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            return row.id, row.lease_token

    async def heartbeat(self, variant_id, token):
        async with self.factory() as session, session.begin():
            row, _ = await ResearchLedger(self.factory, variant_id, token).guard(session)
            row.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)

    async def finish(self, variant_id, token, status, code=None):
        async with self.factory() as session, session.begin():
            row = await session.get(Variant, variant_id, with_for_update=True)
            if (
                not row
                or row.status != "RUNNING"
                or row.lease_token != token
                or row.lease_expires_at <= datetime.now(UTC)
            ):
                return
            unsettled = list(
                await session.scalars(
                    select(Observation).where(
                        Observation.variant_id == row.id, Observation.status == "ATTEMPTED"
                    )
                )
            )
            for observation in unsettled:
                observation.status = "INTERRUPTED_BILLING_UNKNOWN"
            row.status, row.error_code = ("INTERRUPTED" if unsettled else status), code
            row.lease_token, row.lease_expires_at = None, None
            row.finished_at = datetime.now(UTC) if row.status in TERMINAL else None
            await session.flush()
            await update_experiment(session, row.experiment_id)

    async def execute(self, variant_id, token):
        async with self.factory() as session, session.begin():
            row, experiment = await ResearchLedger(self.factory, variant_id, token).guard(session)
            check_consent(
                experiment,
                ResearchConsent.model_validate(
                    {
                        k: v
                        for k, v in experiment.consent.items()
                        if k in ResearchConsent.model_fields
                    }
                ),
            )
            service = SpeakingBenchmarkService(
                session, row.owner_id, settings=self.settings, storage=self.storage
            )
            sample, review, manifest, _ = await load_approved_input(
                service, row.sample_id, row.review_revision
            )
            if row.manifest_fingerprint != review.fingerprint:
                raise failure("REPLAY_APPROVED_SOURCE_CHANGED", 409)
            config, mode = row.configuration, experiment.mode
            from app.schemas.speaking_benchmark_research import ProviderVariant
            from app.services.speaking_benchmark_research import provider_configuration

            actual = provider_configuration(
                self.settings,
                ProviderVariant(
                    key=row.provider_key,
                    provider=config["provider"],
                    silence_ms=config["silence_ms"],
                ),
                mode,
            )
            if actual != config or static_blockers(self.settings, config, mode):
                raise failure("SPEAKING_RESEARCH_CONFIGURATION_UNAVAILABLE", 409)
            key, source, windows = sample.audio_key, sample.source_sha256, row.windows
        if mode == "PAIRED_GRADING":
            await self.schedule_grading(variant_id, token)
            return
        chosen = variant_settings(self.settings, config)
        # Per-experiment consent grants research requests only, never production defaults.
        consent = experiment.consent
        seconds = experiment.configuration["provider_audio_ms"] / 1000
        chosen = chosen.model_copy(
            update={
                "speaking_lexical_asr_allow_additional_requests": True,
                "speaking_lexical_asr_allow_gpu": consent["modal_gpu"],
                "speaking_lexical_asr_estimated_cost_usd_per_minute": consent["estimates_usd"][
                    config["provider"]
                ]
                / seconds
                * 60,
                "speaking_lexical_asr_max_estimated_cost_usd_per_response": consent[
                    "max_estimated_cost_usd"
                ],
            }
        )
        from app.evaluation.speaking.asr_comparison import _rss
        from app.evaluation.speaking.replay_audio import pcm_digest
        from app.providers.speaking_asr.lexical import create_lexical_analyzer
        from app.providers.speech_analysis.azure import AzureSpeechAnalyzer
        from app.services.speaking_audio import await_audio_thread

        analyzer = (
            self.analyzer_factory(chosen, config["provider"])
            if self.analyzer_factory
            else AzureSpeechAnalyzer(chosen)
            if config["provider"] == "azure_pa"
            else create_lexical_analyzer(chosen, config["provider"])
        )
        ledger = ResearchLedger(self.factory, variant_id, token)
        partial = False
        async with materialize_approved_audio(self.storage, key, manifest, source, chosen) as (
            root,
            metadata,
            resolved,
        ):
            for index, segment in enumerate(
                s for s in manifest.segments if s.id in {w["id"] for w in windows}
            ):
                await self.heartbeat(variant_id, token)
                audio = await normalized_segment(root, metadata, manifest, segment, index, resolved)
                digest = await await_audio_thread(asyncio.to_thread(pcm_digest, audio))
                identity = fingerprint(
                    [
                        config,
                        source,
                        row.manifest_fingerprint,
                        segment.model_dump(mode="json"),
                        digest,
                    ]
                )
                identifier, cached = await ledger.begin_or_reuse(segment.id, identity)
                if cached is not None:
                    partial |= cached["status"] != "COMPLETE"
                    continue
                start, cpu, rss_before = time.monotonic(), time.process_time(), _rss()
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
                        or result.source.audio_fingerprint != source
                        or result.source.normalized_audio_fingerprint != digest
                        or result.source.duration_ms != audio.duration_ms
                        or result.source.segment_id != str(mapping.segment_id)
                    ):
                        raise failure("SPEAKING_RESEARCH_PROVIDER_EVIDENCE_INVALID", 409)
                    if not result.coverage.stream_completed:
                        await ledger.interrupt(
                            identifier,
                            result=result.model_dump(mode="json"),
                            usage=result.usage.model_dump(mode="json"),
                        )
                        raise failure("SPEAKING_RESEARCH_STREAM_INCOMPLETE", 409)
                    await ledger.complete(
                        identifier,
                        result.model_dump(mode="json"),
                        {
                            **result.usage.model_dump(mode="json"),
                            "wall_latency_ms": round((time.monotonic() - start) * 1000),
                            "host_process_cpu_seconds": time.process_time() - cpu,
                            "host_rss_before_bytes": rss_before,
                            "host_rss_after_bytes": _rss(),
                            "remote_gpu_seconds": None,
                        },
                        local=config["provider"] == "faster_whisper_local",
                    )
                    partial |= result.status != "COMPLETE"
                except BaseException:
                    await asyncio.shield(ledger.interrupt(identifier))
                    raise
        await self.finish(variant_id, token, "PARTIAL" if partial else "COMPLETED")

    async def schedule_grading(self, variant_id, token):
        """Atomic P2 admission, serial per sample; no alternate grading algorithm."""
        async with self.factory() as session, session.begin():
            variant, experiment = await ResearchLedger(self.factory, variant_id, token).guard(
                session
            )
            existing = (
                await session.get(Run, variant.grading_run_id) if variant.grading_run_id else None
            )
            if existing:
                if existing.status in TERMINAL:
                    variant.status, variant.error_code, variant.finished_at = (
                        existing.status,
                        existing.error_code,
                        datetime.now(UTC),
                    )
                elif existing.status == "INTERRUPTED":
                    variant.status, variant.error_code = (
                        "INTERRUPTED",
                        "P2_BILLING_RECONCILIATION_REQUIRED",
                    )
                else:
                    variant.status = "WAITING"
                variant.lease_token, variant.lease_expires_at = None, None
                await session.flush()
                await update_experiment(session, experiment.id)
                return
            if await session.scalar(
                select(Run.id)
                .where(
                    Run.sample_id == variant.sample_id,
                    Run.status.in_(["PENDING", "RUNNING", "INTERRUPTED"]),
                )
                .limit(1)
            ):
                variant.status, variant.lease_token, variant.lease_expires_at = (
                    "WAITING",
                    None,
                    None,
                )
                return
            config = variant.configuration["grading"]
            # Reuse a finalized immutable P2 prediction only on exact admitted inputs.
            existing = await session.scalar(
                select(Run)
                .where(
                    Run.owner_id == variant.owner_id,
                    Run.sample_id == variant.sample_id,
                    Run.review_revision == variant.review_revision,
                    Run.manifest_fingerprint == variant.manifest_fingerprint,
                    Run.config_fingerprint == fingerprint(config),
                    Run.status == "COMPLETED",
                )
                .order_by(Run.created_at.desc())
                .limit(1)
            )
            if existing is None:
                cloud = {"azure_pa", "openai"} | (
                    {config["lexical_provider"]}
                    if config["lexical_provider"] != "azure_pa"
                    else set()
                )
                estimates = {
                    p: max(
                        experiment.consent["estimates_usd"][p]
                        / len(experiment.configuration["cohort"])
                        / len(experiment.configuration["variants"]),
                        1e-9,
                    )
                    for p in cloud
                }
                existing = Run(
                    sample_id=variant.sample_id,
                    owner_id=variant.owner_id,
                    review_revision=variant.review_revision,
                    source_sha256=variant.source_sha256,
                    manifest_fingerprint=variant.manifest_fingerprint,
                    config_fingerprint=fingerprint(config),
                    submission_key=variant.id,
                    configuration=config,
                    consent={
                        "azure_audio": True,
                        "llm_text": True,
                        "independent_provider": config["lexical_provider"] != "azure_pa",
                        "estimates_usd": estimates,
                        "max_estimated_cost_usd": experiment.consent["max_estimated_cost_usd"],
                        "research_experiment": str(experiment.id),
                    },
                    candidate_ms=sum(w["end_ms"] - w["start_ms"] for w in variant.windows),
                    window_count=len(variant.windows),
                )
                session.add(existing)
                await session.flush()
            variant.grading_run_id = existing.id
            variant.status = existing.status if existing.status in TERMINAL else "WAITING"
            variant.lease_token, variant.lease_expires_at = None, None
            await session.flush()
            await update_experiment(session, experiment.id)

    async def run_once(self):
        if not self.settings.speaking_benchmark_research_enabled:
            raise failure("SPEAKING_RESEARCH_DISABLED", 503)
        claim = await self.claim()
        if not claim:
            return False
        identifier, token = claim
        task = asyncio.create_task(self.execute(identifier, token))

        async def maintain():
            while True:
                await asyncio.sleep(20)
                try:
                    await self.heartbeat(identifier, token)
                except Exception:
                    task.cancel()
                    return

        pulse = asyncio.create_task(maintain())
        try:
            await task
        except BaseException as error:
            code = getattr(error, "code", "SPEAKING_RESEARCH_EXECUTION_FAILED")
            interrupted = (
                isinstance(error, asyncio.CancelledError)
                or "BILLING" in code
                or "UNSETTLED" in code
            )
            async with self.factory() as session, session.begin():
                unknown = await session.scalar(
                    select(Observation.id)
                    .where(
                        Observation.variant_id == identifier,
                        Observation.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
                    )
                    .limit(1)
                )
            await asyncio.shield(
                self.finish(
                    identifier, token, "INTERRUPTED" if interrupted or unknown else "FAILED", code
                )
            )
            if isinstance(error, asyncio.CancelledError) and asyncio.current_task().cancelling():
                raise
        finally:
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)
        return True
