"""Short transaction ledger: commit ATTEMPTED before each physical lexical ASR call."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_questions import SpeakingBenchmarkQuestionJob as Job
from app.models.speaking_benchmark_questions import SpeakingBenchmarkQuestionRequest as Request
from app.services.speaking_benchmark import SpeakingBenchmarkService, failure
from app.services.speaking_benchmark_questions import bound_input
from app.services.speaking_benchmark_research_ledger import (
    unresolved_grading_requests,
    unresolved_research_requests,
)


async def unresolved_question_requests(session, sample_id):
    pending = []
    for old in await session.scalars(
        select(Request)
        .join(Job)
        .where(
            Job.sample_id == sample_id,
            Request.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
        )
    ):
        replacement = (
            await session.get(Request, old.reconciliation["replacement_id"])
            if (old.reconciliation and old.reconciliation.get("replacement_id"))
            else None
        )
        if replacement is None or replacement.status != "COMPLETED":
            pending.append(old)
    return pending


class QuestionLedger:
    def __init__(self, factory, job_id, token, *, settings=None, storage=None):
        self.factory, self.job_id, self.token = factory, job_id, token
        self.settings, self.storage = settings, storage

    async def guard(self, session):
        sample_id = await session.scalar(select(Job.sample_id).where(Job.id == self.job_id))
        sample = await session.get(Sample, sample_id, with_for_update=True) if sample_id else None
        job = await session.get(Job, self.job_id, with_for_update=True)
        if (
            not sample
            or sample.deletion_pending_at
            or not job
            or job.owner_id != sample.owner_id
            or job.source_sha256 != sample.source_sha256
            or job.status != "RUNNING"
            or job.lease_token != self.token
            or job.lease_expires_at <= datetime.now(UTC)
            or sample.review_revision != job.review_revision
        ):
            raise failure("SPEAKING_QUESTIONS_LEASE_LOST", 409)
        service = SpeakingBenchmarkService(
            session, job.owner_id, settings=self.settings, storage=self.storage
        )
        await bound_input(service, job)
        return job

    async def begin_or_reuse(self, window_id, identity):
        async with self.factory() as session, session.begin():
            job = await self.guard(session)
            if window_id not in {w["id"] for w in job.windows}:
                raise failure("SPEAKING_QUESTIONS_WINDOW_MISMATCH", 409)
            current = await session.scalar(
                select(Request)
                .where(
                    Request.job_id == job.id,
                    Request.window_id == window_id,
                    Request.identity == identity,
                    Request.status == "COMPLETED",
                )
                .limit(1)
            )
            if current:
                return current.id, current.result
            # A receipt is source/review/model/PCM bound by the exact request identity.
            cached = await session.scalar(
                select(Request)
                .join(Job)
                .where(
                    Job.sample_id == job.sample_id,
                    Job.owner_id == job.owner_id,
                    Request.window_id == window_id,
                    Request.identity == identity,
                    Request.status == "COMPLETED",
                )
                .order_by(Request.created_at.desc())
                .limit(1)
            )
            number = (
                await session.scalar(
                    select(func.max(Request.attempt)).where(
                        Request.job_id == job.id, Request.window_id == window_id
                    )
                )
                or 0
            ) + 1
            if cached:
                row = Request(
                    job_id=job.id,
                    window_id=window_id,
                    identity=identity,
                    attempt=number,
                    status="COMPLETED",
                    billing_state="CACHE_REUSED",
                    result=cached.result,
                    usage={},
                    reused_from=cached.id,
                    finished_at=datetime.now(UTC),
                )
                session.add(row)
                await session.flush()
                return row.id, row.result
            permitted = []
            for old in await unresolved_question_requests(session, job.sample_id):
                if (
                    old.job_id != job.id
                    or old.window_id != window_id
                    or old.identity != identity
                    or not old.reconciliation
                    or old.reconciliation.get("replacement_id")
                ):
                    raise failure("SPEAKING_QUESTIONS_BILLING_UNKNOWN", 409)
                permitted.append(old)
            if await unresolved_research_requests(
                session, job.sample_id
            ) or await unresolved_grading_requests(session, job.sample_id):
                raise failure("SPEAKING_QUESTIONS_OTHER_REQUEST_UNSETTLED", 409)
            requests = list(await session.scalars(select(Request).where(Request.job_id == job.id)))
            physical = [r for r in requests if r.reused_from is None]
            retries = [r for r in requests if r.reconciliation]
            # Renewed consent admits exactly one replacement for each reconciled attempt.
            maximum = min(job.configuration["limits"]["physical_requests"], len(job.windows)) + len(
                retries
            )
            if len(physical) >= maximum:
                raise failure("SPEAKING_QUESTIONS_REQUEST_LIMIT", 409)
            row = Request(
                id=uuid4(),
                job_id=job.id,
                window_id=window_id,
                identity=identity,
                attempt=number,
                status="ATTEMPTED",
                billing_state="UNKNOWN",
            )
            session.add(row)
            await session.flush()
            for old in permitted:
                old.reconciliation = old.reconciliation | {"replacement_id": str(row.id)}
            await session.flush()
            return row.id, None

    async def complete(self, request_id, result, usage, *, local=False):
        async with self.factory() as session, session.begin():
            row = await session.get(Request, request_id, with_for_update=True)
            # A late result settles only its exact attempt. Cancellation remains fenced.
            if (
                row
                and row.job_id == self.job_id
                and row.status in {"ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"}
            ):
                row.status, row.billing_state = "COMPLETED", "NOT_BILLABLE" if local else "OBSERVED"
                row.result, row.usage, row.finished_at = result, usage, datetime.now(UTC)

    async def interrupt(self, request_id, *, result=None, usage=None):
        async with self.factory() as session, session.begin():
            row = await session.get(Request, request_id, with_for_update=True)
            if row and row.job_id == self.job_id and row.status == "ATTEMPTED":
                row.status, row.error_code, row.finished_at = (
                    "INTERRUPTED_BILLING_UNKNOWN",
                    "ASR_REQUEST_UNCERTAIN",
                    datetime.now(UTC),
                )
                row.result, row.usage = result, usage
