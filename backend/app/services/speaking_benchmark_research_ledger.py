"""ASR-only durable request accounting; no P2/LLM readiness dependency."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRObservation as Observation
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperiment as Experiment
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperimentVariant as Variant
from app.services.speaking_benchmark import failure


async def unresolved_research_requests(session, sample_id):
    pending = []
    for old in await session.scalars(
        select(Observation)
        .join(Variant)
        .where(
            Variant.sample_id == sample_id,
            Observation.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
        )
    ):
        replacement = (
            await session.get(Observation, old.reconciliation["replacement_id"])
            if old.reconciliation and old.reconciliation.get("replacement_id")
            else None
        )
        if replacement is None or replacement.status != "COMPLETED":
            pending.append(old)
    return pending


async def unresolved_grading_requests(session, sample_id):
    from app.models.speaking_benchmark_grading import (
        SpeakingBenchmarkGradingCheckpoint as Checkpoint,
    )
    from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run

    pending = []
    for old in await session.scalars(
        select(Checkpoint)
        .join(Run)
        .where(
            Run.sample_id == sample_id,
            Checkpoint.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
        )
    ):
        replacement = await session.scalar(
            select(Checkpoint.id)
            .join(Run)
            .where(
                Run.sample_id == sample_id,
                Checkpoint.stage == old.stage,
                Checkpoint.identity == old.identity,
                Checkpoint.created_at > old.created_at,
                Checkpoint.status == "COMPLETED",
                Checkpoint.reused_from.is_(None),
            )
            .limit(1)
        )
        if replacement is None:
            pending.append(old)
    return pending


class ResearchLedger:
    def __init__(self, factory, variant_id, token):
        self.factory, self.variant_id, self.token = factory, variant_id, token

    async def guard(self, session):
        sample_id = await session.scalar(
            select(Variant.sample_id).where(Variant.id == self.variant_id)
        )
        sample = await session.get(Sample, sample_id, with_for_update=True) if sample_id else None
        row = await session.get(Variant, self.variant_id, with_for_update=True)
        experiment = await session.get(Experiment, row.experiment_id) if row else None
        if (
            not sample
            or sample.deletion_pending_at
            or not row
            or row.source_sha256 != sample.source_sha256
            or row.owner_id != sample.owner_id
            or row.status != "RUNNING"
            or row.lease_token != self.token
            or row.lease_expires_at <= datetime.now(UTC)
            or not experiment
            or experiment.status not in {"PENDING", "RUNNING"}
        ):
            raise failure("SPEAKING_RESEARCH_LEASE_LOST", 409)
        return row, experiment

    async def begin_or_reuse(self, segment_id, identity):
        async with self.factory() as session, session.begin():
            variant, experiment = await self.guard(session)
            # A single sample lock serializes cache checks and physical admissions,
            # including different experiments on the same source.
            cached = await session.scalar(
                select(Observation)
                .join(Variant)
                .where(
                    Variant.owner_id == variant.owner_id,
                    Variant.sample_id == variant.sample_id,
                    Observation.segment_id == segment_id,
                    Observation.identity == identity,
                    Observation.status == "COMPLETED",
                )
                .order_by(Observation.created_at.desc())
                .limit(1)
            )
            current = await session.scalar(
                select(Observation)
                .where(
                    Observation.variant_id == variant.id,
                    Observation.segment_id == segment_id,
                    Observation.identity == identity,
                    Observation.status == "COMPLETED",
                )
                .limit(1)
            )
            if current:
                return current.id, current.result
            number = (
                await session.scalar(
                    select(func.max(Observation.attempt)).where(
                        Observation.variant_id == variant.id, Observation.segment_id == segment_id
                    )
                )
                or 0
            ) + 1
            if cached:
                receipt = Observation(
                    variant_id=variant.id,
                    segment_id=segment_id,
                    identity=identity,
                    attempt=number,
                    status="COMPLETED",
                    billing_state="CACHE_REUSED",
                    result=cached.result,
                    usage={},
                    reused_from=cached.id,
                    finished_at=datetime.now(UTC),
                )
                session.add(receipt)
                await session.flush()
                return receipt.id, receipt.result
            unknowns = await unresolved_research_requests(session, variant.sample_id)
            permitted = []
            for old in unknowns:
                if old.reconciliation and old.reconciliation.get("replacement_id"):
                    replacement = await session.get(
                        Observation, old.reconciliation["replacement_id"]
                    )
                    if replacement and replacement.status == "COMPLETED":
                        continue
                if (
                    not old.reconciliation
                    or old.reconciliation.get("replacement_id")
                    or old.identity != identity
                    or old.segment_id != segment_id
                    or old.variant_id != variant.id
                ):
                    raise failure("SPEAKING_RESEARCH_BILLING_UNKNOWN", 409)
                permitted.append(old)
            # P2 uncertainty also blocks new ASR requests on this sample.
            if await unresolved_grading_requests(session, variant.sample_id):
                raise failure("SPEAKING_RESEARCH_P2_REQUEST_UNSETTLED", 409)
            from app.services.speaking_benchmark_questions_ledger import (
                unresolved_question_requests,
            )

            if await unresolved_question_requests(session, variant.sample_id):
                raise failure("SPEAKING_RESEARCH_QUESTION_REQUEST_UNSETTLED", 409)
            # Experiment lock serializes global budget across separate samples.
            await session.refresh(experiment, with_for_update=True)
            submitted = await session.scalar(
                select(func.count())
                .select_from(Observation)
                .join(Variant)
                .where(
                    Variant.experiment_id == experiment.id,
                    Observation.billing_state != "CACHE_REUSED",
                )
            )
            extension = sum(
                1
                for o in await session.scalars(
                    select(Observation).join(Variant).where(Variant.experiment_id == experiment.id)
                )
                if o.reconciliation
            )
            if submitted >= experiment.configuration["limits"]["physical_requests"] + extension:
                raise failure("SPEAKING_RESEARCH_REQUEST_LIMIT", 409)
            row = Observation(
                id=uuid4(),
                variant_id=variant.id,
                segment_id=segment_id,
                identity=identity,
                attempt=number,
                status="ATTEMPTED",
                billing_state="UNKNOWN",
            )
            session.add(row)
            for old in permitted:
                old.reconciliation = old.reconciliation | {"replacement_id": str(row.id)}
            await session.flush()
            return row.id, None

    async def complete(self, observation_id, result, usage, *, local=False):
        async with self.factory() as session, session.begin():
            row = await session.get(Observation, observation_id, with_for_update=True)
            # Late response can settle only this exact physical attempt, never a run.
            if (
                row
                and row.variant_id == self.variant_id
                and row.status in {"ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"}
            ):
                row.status, row.billing_state = "COMPLETED", "NOT_BILLABLE" if local else "OBSERVED"
                row.result, row.usage, row.finished_at = result, usage, datetime.now(UTC)

    async def interrupt(self, observation_id, *, result=None, usage=None):
        async with self.factory() as session, session.begin():
            row = await session.get(Observation, observation_id, with_for_update=True)
            if row and row.variant_id == self.variant_id and row.status == "ATTEMPTED":
                row.status, row.error_code, row.finished_at = (
                    "INTERRUPTED_BILLING_UNKNOWN",
                    "ASR_REQUEST_UNCERTAIN",
                    datetime.now(UTC),
                )
                row.result, row.usage = result, usage
