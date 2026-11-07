"""Owner scoping shared by HTTP and worker orchestration. No inference imports."""

from sqlalchemy import select

from app.models.speaking_benchmark import SpeakingBenchmarkSample
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun
from app.services.speaking_benchmark import failure


async def owned_run(session, owner_id, sample_id, run_id, lock=False):
    query = (
        select(SpeakingBenchmarkGradingRun)
        .join(
            SpeakingBenchmarkSample,
            SpeakingBenchmarkSample.id == SpeakingBenchmarkGradingRun.sample_id,
        )
        .where(
            SpeakingBenchmarkGradingRun.id == run_id,
            SpeakingBenchmarkGradingRun.sample_id == sample_id,
            SpeakingBenchmarkGradingRun.owner_id == owner_id,
            SpeakingBenchmarkSample.owner_id == owner_id,
            SpeakingBenchmarkSample.deletion_pending_at.is_(None),
        )
    )
    row = await session.scalar(
        query.with_for_update(of=SpeakingBenchmarkGradingRun) if lock else query
    )
    if row is None:
        raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
    return row
