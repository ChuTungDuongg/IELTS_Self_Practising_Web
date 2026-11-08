import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingCheckpoint as Checkpoint
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.services.speaking_benchmark_ledger import RequestLedger


async def test_atomic_claim_and_unknown_billing_recovery(grading_lab):
    from app.services.speaking_benchmark_grading_worker import GradingJobRunner

    factory, settings, storage, owner, sample, run_id = grading_lab
    worker = GradingJobRunner(factory, settings, storage=storage)
    claims = await asyncio.gather(worker.claim(), worker.claim())
    assert sum(c is not None for c in claims) == 1
    identifier, token = next(c for c in claims if c)
    ledger = RequestLedger(factory, identifier, token)
    attempt = await ledger.begin("azure:segment-1", "azure", "e" * 64)
    async with factory() as session, session.begin():
        assert (await session.get(Checkpoint, attempt)).status == "ATTEMPTED"
        row = await session.get(Run, run_id)
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await worker.claim() is None
    async with factory() as session:
        assert (await session.get(Run, run_id)).status == "INTERRUPTED"
        assert (await session.get(Checkpoint, attempt)).status == "INTERRUPTED_BILLING_UNKNOWN"
    with pytest.raises(Exception, match="LEASE_LOST"):
        await ledger.begin("azure:next", "azure", "d" * 64)


async def test_completed_results_are_reused_and_finalized_predictions_frozen(grading_lab):
    from sqlalchemy.exc import DBAPIError

    from app.services.speaking_benchmark_grading_worker import GradingJobRunner

    factory, settings, storage, owner, sample, run_id = grading_lab
    identifier, token = await GradingJobRunner(factory, settings, storage=storage).claim()
    ledger = RequestLedger(factory, identifier, token)
    checkpoint = await ledger.begin("azure:one", "azure", "a" * 64)
    await ledger.finish(checkpoint, {"normalized": True})
    assert await ledger.cached("azure:one", "a" * 64) == {"normalized": True}
    async with factory() as session, session.begin():
        row = await session.get(Run, run_id)
        row.status = "COMPLETED"
        row.prediction = {"bands": {"fc": 6, "overall": None}}
    with pytest.raises(DBAPIError):
        async with factory() as session, session.begin():
            row = await session.get(Run, run_id)
            row.prediction = {"bands": {"fc": 9}}


async def test_cross_run_cache_hit_persists_one_nonbillable_receipt(grading_lab):
    from uuid import uuid4

    from sqlalchemy import select

    from app.services.speaking_benchmark_grading_worker import GradingJobRunner

    factory, settings, storage, _, _, run_id = grading_lab
    worker = GradingJobRunner(factory, settings, storage=storage)
    identifier, token = await worker.claim()
    first = RequestLedger(factory, identifier, token)
    origin = await first.begin("azure:one", "azure-speech", "a" * 64)
    await first.finish(origin, {"normalized": True}, usage={"submitted_audio_ms": 1000})
    async with factory() as session, session.begin():
        old = await session.get(Run, run_id)
        old.status = "COMPLETED"
        successor = Run(
            submission_key=uuid4(),
            **{
                key: getattr(old, key)
                for key in (
                    "sample_id",
                    "owner_id",
                    "review_revision",
                    "source_sha256",
                    "manifest_fingerprint",
                    "config_fingerprint",
                    "configuration",
                    "consent",
                    "candidate_ms",
                    "window_count",
                )
            },
        )
        session.add(successor)
        await session.flush()
        successor_id = successor.id
    identifier, token = await worker.claim()
    assert identifier == successor_id
    second = RequestLedger(factory, identifier, token)
    for _ in range(2):
        assert await second.cached("azure:one", "a" * 64) == {"normalized": True}
    async with factory() as session:
        receipts = list(
            await session.scalars(select(Checkpoint).where(Checkpoint.run_id == identifier))
        )
        assert len(receipts) == 1
        receipt = receipts[0]
        assert receipt.reused_from == origin
        assert receipt.identity == "a" * 64 and receipt.stage == "azure:one"
        assert receipt.status == "COMPLETED" and receipt.billing_state == "NOT_BILLABLE"
        assert receipt.usage == {}, "Cache reuse must not duplicate physical provider usage"


async def test_cache_receipt_cannot_resolve_unknown_physical_request(grading_lab):
    from app.services.speaking_benchmark_grading_worker import GradingJobRunner
    from app.services.speaking_benchmark_research_ledger import unresolved_grading_requests

    factory, settings, storage, _, sample_id, _ = grading_lab
    worker = GradingJobRunner(factory, settings, storage=storage)
    run_id, token = await worker.claim()
    ledger = RequestLedger(factory, run_id, token)
    origin = await ledger.begin("azure:one", "azure-speech", "a" * 64)
    await ledger.finish(origin, {"evidence": "synthetic"})
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        unknown = Checkpoint(
            run_id=run_id,
            stage="azure:one",
            provider="azure-speech",
            identity="a" * 64,
            attempt=2,
            status="INTERRUPTED_BILLING_UNKNOWN",
            billing_state="UNKNOWN",
            created_at=now,
        )
        session.add(unknown)
        session.add(
            Checkpoint(
                run_id=run_id,
                stage="azure:one",
                provider="azure-speech",
                identity="a" * 64,
                attempt=3,
                status="COMPLETED",
                billing_state="NOT_BILLABLE",
                result={"evidence": "synthetic"},
                usage={},
                reused_from=origin,
                created_at=now + timedelta(seconds=1),
            )
        )
    async with factory() as session:
        assert len(await unresolved_grading_requests(session, sample_id)) == 1
    with pytest.raises(Exception, match="BILLING_UNKNOWN"):
        await ledger.begin("azure:next", "azure-speech", "b" * 64)
    await worker.finish(run_id, token)
    async with factory() as session:
        assert (await session.get(Run, run_id)).status == "INTERRUPTED"


async def test_cancel_then_delete_preserves_uncertain_attempt_until_cleanup(grading_lab):
    from app.models.speaking_benchmark import SpeakingBenchmarkSample
    from app.services.speaking_benchmark import SpeakingBenchmarkService
    from app.services.speaking_benchmark_grading import cancel
    from app.services.speaking_benchmark_grading_worker import GradingJobRunner

    factory, settings, storage, owner, sample, run_id = grading_lab
    identifier, token = await GradingJobRunner(factory, settings, storage=storage).claim()
    ledger = RequestLedger(factory, identifier, token)
    attempt = await ledger.begin("azure:one", "azure", "a" * 64)
    async with factory() as session:
        await cancel(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            sample,
            run_id,
        )
    async with factory() as session:
        await SpeakingBenchmarkService(session, owner, settings=settings, storage=storage).delete(
            sample, 1
        )
    async with factory() as session:
        tombstone = await session.get(SpeakingBenchmarkSample, sample)
        assert tombstone is not None and tombstone.deletion_pending_at is not None
        assert await session.get(Checkpoint, attempt) is not None
    with pytest.raises(Exception, match="LEASE_LOST"):
        await ledger.begin("azure:next", "azure", "b" * 64)


async def test_inference_configuration_cannot_change_after_admission(grading_lab):
    from sqlalchemy.exc import DBAPIError

    factory, settings, storage, owner, sample, run_id = grading_lab
    with pytest.raises(DBAPIError):
        async with factory() as session, session.begin():
            row = await session.get(Run, run_id)
            row.configuration = {"lexical_provider": "azure_stt"}


async def test_exact_interrupted_attempt_requires_renewed_consent_and_preserves_history(
    grading_lab,
):
    from app.schemas.speaking_benchmark_grading import RetryRequest
    from app.services.speaking_benchmark import SpeakingBenchmarkService
    from app.services.speaking_benchmark_grading import retry_interrupted
    from app.services.speaking_benchmark_grading_worker import GradingJobRunner

    factory, settings, storage, owner, sample, run_id = grading_lab
    worker = GradingJobRunner(factory, settings, storage=storage)
    identifier, token = await worker.claim()
    ledger = RequestLedger(factory, identifier, token)
    attempt = await ledger.begin("azure:one", "azure", "a" * 64)
    await ledger.interrupt(attempt, "TIMEOUT")
    await worker.finish(identifier, token)
    assert await worker.claim() is None
    async with factory() as session:
        body = RetryRequest(
            checkpoint_id=attempt,
            reconciliation="Operator reconciled the uncertain fictional request",
            consent={
                "azure_audio": True,
                "llm_text": True,
                "estimates_usd": {"azure_pa": 0.1, "openai": 0.1},
                "max_estimated_cost_usd": 1,
            },
        )
        await retry_interrupted(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            sample,
            run_id,
            body,
        )
    identifier, token = await worker.claim()
    ledger = RequestLedger(factory, identifier, token)
    with pytest.raises(Exception, match="STAGE_MISMATCH"):
        await ledger.begin("azure:different", "azure", "b" * 64)
    replacement = await ledger.begin("azure:one", "azure", "a" * 64)
    await ledger.finish(replacement, {"evidence": "synthetic"})
    next_attempt = await ledger.begin("azure:two", "azure", "b" * 64)
    assert next_attempt != replacement != attempt
    async with factory() as session:
        assert (await session.get(Checkpoint, attempt)).status == "INTERRUPTED_BILLING_UNKNOWN"
        assert (await session.get(Checkpoint, replacement)).attempt == 2


async def test_expired_worker_cannot_finalize_even_before_reclaim(grading_lab):
    from app.services.speaking_benchmark_grading_worker import GradingJobRunner

    factory, settings, storage, owner, sample, run_id = grading_lab
    worker = GradingJobRunner(factory, settings, storage=storage)
    identifier, token = await worker.claim()
    async with factory() as session, session.begin():
        (await session.get(Run, run_id)).lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await worker.finish(identifier, token, code="LATE_WORKER") is False


async def test_admin_cancellation_keeps_worker_alive_for_next_run(grading_lab, monkeypatch):
    from uuid import uuid4

    from app.services import speaking_benchmark_grading_worker as module
    from app.services.speaking_benchmark import SpeakingBenchmarkService
    from app.services.speaking_benchmark_grading import cancel

    factory, settings, storage, owner, sample, run_id = grading_lab
    worker = module.GradingJobRunner(factory, settings, storage=storage)
    started, cancelled = asyncio.Event(), asyncio.Event()
    attempts, executed = [], []
    original_sleep = asyncio.sleep

    async def wait_for_cancellation(seconds):
        if seconds == 20:
            await cancelled.wait()
        else:
            await original_sleep(seconds)

    async def execute(identifier, token):
        executed.append(identifier)
        if identifier == run_id:
            attempts.append(
                await RequestLedger(factory, identifier, token).begin(
                    "azure:one", "azure", "a" * 64
                )
            )
            started.set()
            await asyncio.Future()
        else:
            await worker.finish(identifier, token, code="OFFLINE_TEST_FINISHED")

    monkeypatch.setattr(module, "grading_availability", lambda _: {"can_queue": True})
    monkeypatch.setattr(module.asyncio, "sleep", wait_for_cancellation)
    monkeypatch.setattr(worker, "execute", execute)
    task = asyncio.create_task(worker.run_once())
    try:
        await asyncio.wait_for(started.wait(), 5)
        async with factory() as session:
            await cancel(
                SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
                sample,
                run_id,
            )
        cancelled.set()
        assert await asyncio.wait_for(task, 5) is True

        next_id = uuid4()
        async with factory() as session, session.begin():
            previous = await session.get(Run, run_id)
            values = {
                name: getattr(previous, name)
                for name in (
                    "sample_id",
                    "owner_id",
                    "review_revision",
                    "source_sha256",
                    "manifest_fingerprint",
                    "config_fingerprint",
                    "configuration",
                    "consent",
                    "candidate_ms",
                    "window_count",
                )
            }
            session.add(Run(id=next_id, submission_key=uuid4(), **values))
        assert await worker.run_once() is True
        assert executed == [run_id, next_id]
        async with factory() as session:
            assert (await session.get(Run, run_id)).status == "CANCELLED"
            assert (
                await session.get(Checkpoint, attempts[0])
            ).status == "INTERRUPTED_BILLING_UNKNOWN"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_process_shutdown_propagates_cancellation_and_preserves_uncertain_billing(
    grading_lab, monkeypatch
):
    from app.services import speaking_benchmark_grading_worker as module

    factory, settings, storage, owner, sample, run_id = grading_lab
    worker = module.GradingJobRunner(factory, settings, storage=storage)
    started = asyncio.Event()
    attempts = []

    async def execute(identifier, token):
        attempts.append(
            await RequestLedger(factory, identifier, token).begin("azure:one", "azure", "a" * 64)
        )
        started.set()
        await asyncio.Future()

    monkeypatch.setattr(module, "grading_availability", lambda _: {"can_queue": True})
    monkeypatch.setattr(worker, "execute", execute)
    task = asyncio.create_task(worker.run_once())
    try:
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        async with factory() as session:
            assert (await session.get(Run, run_id)).status == "INTERRUPTED"
            assert (
                await session.get(Checkpoint, attempts[0])
            ).status == "INTERRUPTED_BILLING_UNKNOWN"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
