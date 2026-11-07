from uuid import uuid4

import pytest

from app.services.speaking_benchmark_grading_worker import GradingJobRunner
from app.services.speaking_benchmark_ledger import RequestLedger


async def test_admitted_window_count_bounds_physical_requests(grading_lab):
    factory, settings, storage, owner, sample, run_id = grading_lab
    identifier, token = await GradingJobRunner(factory, settings, storage=storage).claim()
    ledger = RequestLedger(factory, identifier, token)
    for i in range(3):
        attempt = await ledger.begin(f"azure:{i}", "azure", str(i) * 64)
        await ledger.finish(attempt, {"complete": True})
    with pytest.raises(Exception, match="REQUEST_BUDGET"):
        await ledger.begin("azure:fourth", "azure", "d" * 64)


async def test_new_run_cannot_bypass_cancelled_unknown_request(grading_lab):
    from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
    from app.services.speaking_benchmark import SpeakingBenchmarkService
    from app.services.speaking_benchmark_grading import cancel

    factory, settings, storage, owner, sample, run_id = grading_lab
    worker = GradingJobRunner(factory, settings, storage=storage)
    identifier, token = await worker.claim()
    ledger = RequestLedger(factory, identifier, token)
    await ledger.begin("azure:one", "azure", "a" * 64)
    async with factory() as session:
        await cancel(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            sample,
            run_id,
        )
    async with factory() as session, session.begin():
        original = await session.get(Run, run_id)
        replacement = Run(
            sample_id=sample,
            owner_id=owner,
            review_revision=1,
            source_sha256=original.source_sha256,
            manifest_fingerprint=original.manifest_fingerprint,
            config_fingerprint=original.config_fingerprint,
            submission_key=uuid4(),
            configuration=original.configuration,
            consent=original.consent,
            candidate_ms=original.candidate_ms,
            window_count=3,
        )
        session.add(replacement)
    second, token2 = await worker.claim()
    with pytest.raises(Exception, match="BILLING_UNKNOWN"):
        await RequestLedger(factory, second, token2).begin("azure:one", "azure", "a" * 64)


async def test_explicit_cancelled_recovery_creates_new_run_without_mutating_history(grading_lab):
    from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
    from app.schemas.speaking_benchmark_grading import RetryRequest
    from app.services.speaking_benchmark import SpeakingBenchmarkService
    from app.services.speaking_benchmark_grading import cancel, retry_interrupted

    factory, settings, storage, owner, sample, run_id = grading_lab
    worker = GradingJobRunner(factory, settings, storage=storage)
    identifier, token = await worker.claim()
    attempt = await RequestLedger(factory, identifier, token).begin("azure:one", "azure", "a" * 64)
    async with factory() as session:
        await cancel(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            sample,
            run_id,
        )
    async with factory() as session:
        result = await retry_interrupted(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            sample,
            run_id,
            RetryRequest(
                checkpoint_id=attempt,
                reconciliation="Explicit operator review of cancelled request",
                consent={
                    "azure_audio": True,
                    "llm_text": True,
                    "estimates_usd": {"azure_pa": 0.1, "openai": 0.1},
                    "max_estimated_cost_usd": 1,
                },
            ),
        )
        assert result.id != run_id
    async with factory() as session:
        assert (await session.get(Run, run_id)).status == "CANCELLED"
    new_id, new_token = await worker.claim()
    assert new_id == result.id
    await RequestLedger(factory, new_id, new_token).begin("azure:one", "azure", "a" * 64)
