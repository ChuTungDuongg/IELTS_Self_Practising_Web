"""Short transactions around physical submissions; uncertainty fails closed."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models.speaking_benchmark import SpeakingBenchmarkSample
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingCheckpoint as Checkpoint
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.services.speaking_benchmark import failure


class RequestLedger:
    def __init__(self, factory, run_id, token):
        self.factory, self.run_id, self.token = factory, run_id, token

    async def guard(self, session):
        # Sample lock precedes run lock, matching cancellation/deletion ordering.
        sample_id = await session.scalar(select(Run.sample_id).where(Run.id == self.run_id))
        sample = (
            await session.get(SpeakingBenchmarkSample, sample_id, with_for_update=True)
            if sample_id
            else None
        )
        run = await session.get(Run, self.run_id, with_for_update=True)
        if (
            sample is None
            or sample.deletion_pending_at
            or run is None
            or run.owner_id != sample.owner_id
            or run.source_sha256 != sample.source_sha256
            or run.status != "RUNNING"
            or run.lease_token != self.token
            or run.lease_expires_at <= datetime.now(UTC)
        ):
            raise failure("SPEAKING_BENCHMARK_LEASE_LOST", 409)
        return run

    async def cached(self, stage, identity):
        async with self.factory() as session, session.begin():
            run = await self.guard(session)
            found = await session.scalar(
                select(Checkpoint)
                .join(Run, Run.id == Checkpoint.run_id)
                .where(
                    Run.owner_id == run.owner_id,
                    Run.sample_id == run.sample_id,
                    Checkpoint.stage == stage,
                    Checkpoint.identity == identity,
                    Checkpoint.status == "COMPLETED",
                )
                .order_by(
                    (Checkpoint.run_id == run.id).desc(),
                    Checkpoint.created_at.desc(),
                    Checkpoint.id,
                )
                .limit(1)
            )
            if found and found.run_id != run.id:
                # Record the exact consumed artifact before returning it. Reports
                # must not guess provenance from whichever historical result is newest.
                # guard() holds the sample/run locks, so concurrent hits deduplicate.
                number = (
                    await session.scalar(
                        select(func.max(Checkpoint.attempt)).where(
                            Checkpoint.run_id == run.id,
                            Checkpoint.stage == stage,
                            Checkpoint.identity == identity,
                        )
                    )
                    or 0
                ) + 1
                session.add(
                    Checkpoint(
                        run_id=run.id,
                        stage=stage,
                        provider=found.provider,
                        identity=identity,
                        attempt=number,
                        status="COMPLETED",
                        billing_state="NOT_BILLABLE",
                        result=found.result,
                        usage={},
                        reused_from=found.reused_from or found.id,
                        finished_at=datetime.now(UTC),
                    )
                )
            return found.result if found else None

    async def begin(self, stage, provider, identity):
        async with self.factory() as session, session.begin():
            run = await self.guard(session)
            from app.services.speaking_benchmark_research_ledger import unresolved_research_requests

            if await unresolved_research_requests(session, run.sample_id):
                raise failure("SPEAKING_BENCHMARK_RESEARCH_REQUEST_UNSETTLED", 409)
            # A prior unknown physical call blocks all subsequent requests until
            # the exact attempt is reconciled, even if another body/config is supplied.
            unresolved = list(
                await session.scalars(
                    select(Checkpoint)
                    .join(Run, Run.id == Checkpoint.run_id)
                    .where(
                        Run.owner_id == run.owner_id,
                        Run.sample_id == run.sample_id,
                        Checkpoint.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
                    )
                )
            )
            allowed = {r["checkpoint_id"] for r in run.consent.get("reconciliations", [])}
            pending = []
            for old in unresolved:
                replacement = await session.scalar(
                    select(Checkpoint.id)
                    .join(Run, Run.id == Checkpoint.run_id)
                    .where(
                        Run.owner_id == run.owner_id,
                        Run.sample_id == run.sample_id,
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
            unresolved = pending
            if any(str(c.id) not in allowed for c in unresolved):
                raise failure("SPEAKING_BENCHMARK_BILLING_UNKNOWN", 409)
            # Renewed permission applies only to the exact reconciled stage/identity.
            for old in unresolved:
                if old.stage != stage or old.identity != identity:
                    raise failure("SPEAKING_BENCHMARK_RETRY_STAGE_MISMATCH", 409)
            group = (
                "openai"
                if stage.startswith("openai:")
                else "azure_pa"
                if stage.startswith("azure:")
                else run.configuration["lexical_provider"]
            )
            prefix = (
                "openai:" if group == "openai" else "azure:" if group == "azure_pa" else "lexical:"
            )
            maximum = (
                run.configuration["max_llm_physical_requests"]
                if group == "openai"
                else run.window_count
            )
            maximum += sum(
                r["stage"].startswith(prefix) for r in run.consent.get("reconciliations", [])
            )
            submitted = await session.scalar(
                select(func.count())
                .select_from(Checkpoint)
                .where(
                    Checkpoint.run_id == run.id,
                    Checkpoint.provider != "cpu",
                    Checkpoint.reused_from.is_(None),
                    Checkpoint.stage.startswith(prefix),
                )
            )
            if submitted >= maximum:
                raise failure("SPEAKING_BENCHMARK_REQUEST_BUDGET_EXCEEDED", 409)
            number = (
                await session.scalar(
                    select(func.max(Checkpoint.attempt)).where(
                        Checkpoint.run_id == run.id,
                        Checkpoint.stage == stage,
                        Checkpoint.identity == identity,
                    )
                )
                or 0
            ) + 1
            row = Checkpoint(
                run_id=run.id, stage=stage, provider=provider, identity=identity, attempt=number
            )
            session.add(row)
            run.stage = stage
            await session.flush()
            return row.id

    async def finish(self, identifier, result, *, usage=None, billable=True):
        async with self.factory() as session, session.begin():
            # A late response can settle accounting after cancellation, but cannot
            # mutate a prediction or authorize another call.
            row = await session.get(Checkpoint, identifier, with_for_update=True)
            if (
                row is None
                or row.run_id != self.run_id
                or row.status not in {"ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"}
            ):
                raise failure("SPEAKING_BENCHMARK_CHECKPOINT_CONFLICT", 409)
            row.result, row.usage = result, usage or {}
            row.status, row.billing_state = "COMPLETED", "OBSERVED" if billable else "NOT_BILLABLE"
            row.finished_at = datetime.now(UTC)

    async def interrupt(self, identifier, code):
        async with self.factory() as session, session.begin():
            row = await session.get(Checkpoint, identifier, with_for_update=True)
            if row and row.run_id == self.run_id and row.status == "ATTEMPTED":
                row.status, row.error_code = "INTERRUPTED_BILLING_UNKNOWN", code
                row.finished_at = datetime.now(UTC)

    async def save_cpu(self, stage, identity, result):
        cached = await self.cached(stage, identity)
        if cached is not None:
            return cached
        async with self.factory() as session, session.begin():
            run = await self.guard(session)
            existing = await session.scalar(
                select(Checkpoint).where(
                    Checkpoint.run_id == run.id,
                    Checkpoint.stage == stage,
                    Checkpoint.identity == identity,
                    Checkpoint.status == "COMPLETED",
                )
            )
            if existing:
                return existing.result
            session.add(
                Checkpoint(
                    run_id=run.id,
                    stage=stage,
                    provider="cpu",
                    identity=identity,
                    attempt=1,
                    status="COMPLETED",
                    billing_state="NOT_BILLABLE",
                    result=result,
                    usage={},
                    finished_at=datetime.now(UTC),
                )
            )
        return result
