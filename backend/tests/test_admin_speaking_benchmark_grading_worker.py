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
