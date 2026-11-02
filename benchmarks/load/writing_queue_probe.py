"""Offline Writing queue component measurement; never calls a real provider.

Run as a module with --directory pointing to a fresh runner init directory.
Requires its private ownership proof, dedicated non-superuser DB and no live server.
All synthetic fixtures created here are removed before this process exits.
"""

# ruff: noqa: E402

import argparse
import asyncio
import json
import platform
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4

from benchmarks.load.runtime import read_run, verify_fresh_probe_database
from benchmarks.load.safety import SafetyError
from benchmarks.load.source_identity import source_identity
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings
from app.evaluation.writing_latency import (
    FakeLatencyProvider,
    load_fixture,
)
from app.models import (
    Attempt,
    AttemptWritingResponse,
    User,
    WritingAIGradingRun,
    WritingTask,
)
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import (
    AttemptStatus,
    ModuleType,
    TimerMode,
    UserRole,
    VersionStatus,
    WritingAIRunStatus,
)
from app.repositories.writing_ai import WritingAIRepository
from app.schemas.writing_ai import CriterionResult, EventPayload
from app.services.writing_ai import CANCELLATION_CODE, WritingAIService
from app.services.writing_ai_worker import (
    WritingAIWorker,
    _tasks,
    stop_writing_ai_workers,
)


class WaitingProvider:
    def __init__(self):
        self.waiting = asyncio.Event()
        self.interrupted = asyncio.Event()

    async def ensure_ready(self):
        self.waiting.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.interrupted.set()
            raise


def latency_summary(values):
    ordered = sorted(round(value, 3) for value in values)
    return {"samples": ordered, "median": median(ordered), "max": max(ordered)}


async def measure(args):
    manifest, private = read_run(args.directory)
    url = private["environment"]["DATABASE_URL"]
    engine = create_async_engine(url, pool_size=5, max_overflow=0, pool_timeout=30)
    try:
        async with engine.connect() as connection:
            await verify_fresh_probe_database(connection, manifest, private)
    except BaseException:
        await engine.dispose()
        raise
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_vllm_base_url="https://fictional.invalid/v1",
        ai_writing_worker_concurrency=args.consumers,
        ai_writing_max_running_runs=args.consumers,
        ai_writing_max_pending_runs=args.runs,
        ai_writing_worker_poll_seconds=0.05,
        ai_writing_lease_seconds=10,
    )
    fixture = load_fixture()
    now = datetime.now(UTC)
    user = User(
        email=f"queue-probe-{uuid4()}@example.test",
        display_name="Fictional probe",
        role=UserRole.USER,
        is_active=True,
        email_verified=True,
    )
    test = DomainTest(title=f"Fictional Writing queue probe {uuid4()}")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED, published_at=now)
    module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
    task = WritingTask(task_number=2, prompt=fixture["task2"]["prompt"], order_index=0)
    test.versions.append(version)
    version.modules.append(module)
    module.writing_tasks.append(task)
    attempts = []
    try:
        async with sessions() as session, session.begin():
            session.add_all([user, test])
            await session.flush()
            attempts = [
                Attempt(
                    user_id=user.id,
                    test_version_id=version.id,
                    module_type=ModuleType.WRITING,
                    status=AttemptStatus.SUBMITTED,
                    timer_mode=TimerMode.COUNT_UP,
                    started_at=now,
                    last_active_at=now,
                    finished_at=now,
                )
                for _ in range(args.runs)
            ]
            session.add_all(attempts)
            await session.flush()
            session.add_all(
                [
                    AttemptWritingResponse(
                        attempt_id=attempt.id,
                        writing_task_id=task.id,
                        content=fixture["task2"]["response"],
                        word_count=30,
                    )
                    for attempt in attempts
                ]
            )

        async def create(attempt, force=False):
            async with sessions() as session:
                return await WritingAIService(session, user.id, settings).create(
                    attempt.id, task.id, force=force
                )

        created = [await create(attempt) for attempt in attempts]
        run_ids = [run.run_id for run in created]
        provider = FakeLatencyProvider(fixture, args.delay_ms / 1000)
        worker = WritingAIWorker(sessions, settings, provider)
        started = perf_counter()
        worker.start()  # Deliberately omit launch: committed rows must be sufficient.
        peak_running = peak_local_jobs = 0
        deadline = started + 90
        while True:
            async with sessions() as session:
                rows = list(
                    await session.scalars(
                        select(WritingAIGradingRun).where(WritingAIGradingRun.id.in_(run_ids))
                    )
                )
            peak_running = max(
                peak_running,
                sum(run.status == WritingAIRunStatus.RUNNING for run in rows),
            )
            peak_local_jobs = max(peak_local_jobs, len(_tasks))
            if all(
                run.status not in {WritingAIRunStatus.PENDING, WritingAIRunStatus.RUNNING}
                for run in rows
            ):
                break
            if perf_counter() > deadline:
                raise RuntimeError("Fake queue did not drain before the local probe timeout")
            await asyncio.sleep(0.02)
        drain_ms = (perf_counter() - started) * 1000
        await stop_writing_ai_workers()
        if any(run.status != WritingAIRunStatus.COMPLETED for run in rows):
            raise RuntimeError("A fake queue run failed; no successful throughput result emitted")
        if peak_running > args.consumers or peak_local_jobs > args.consumers:
            raise RuntimeError("Dispatch exceeded its configured execution bound")

        # Separate, independent-session cancellation while ensure_ready is blocked.
        cancelled = await create(attempts[0], force=True)
        blocked = WaitingProvider()
        runner = WritingAIWorker(sessions, settings, blocked)
        job = asyncio.create_task(runner.execute(cancelled.run_id))
        try:
            await asyncio.wait_for(blocked.waiting.wait(), 5)
            cancel_started = perf_counter()
            async with sessions() as session:
                snapshot = await WritingAIService(session, user.id, settings).cancel(
                    cancelled.run_id
                )
            try:
                await asyncio.wait_for(job, 8)
            except asyncio.CancelledError:
                pass
            cancel_ms = (perf_counter() - cancel_started) * 1000
            if snapshot.error_code != CANCELLATION_CODE or not blocked.interrupted.is_set():
                raise RuntimeError("Cross-session cancellation did not stop blocked fake work")
        finally:
            job.cancel()
            await asyncio.gather(job, return_exceptions=True)

        expired = await create(attempts[0], force=True)
        async with sessions() as session, session.begin():
            run = await WritingAIRepository(session).claim(
                run_id=expired.run_id, lease_seconds=10, max_running=args.consumers
            )
            token = run.lease_token
        partial = CriterionResult(
            score=6,
            feedback="Fictional checkpoint",
            strengths=[],
            improvements=[],
            evidence=[],
        )
        await runner._checkpoint(
            expired.run_id,
            "criterion.completed",
            EventPayload(criterion="ta", result=partial),
            token=token,
        )
        async with sessions() as session, session.begin():
            run = await WritingAIRepository(session).run(expired.run_id, lock=True)
            run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        recovery_started = perf_counter()
        await runner.recover()
        recovery_ms = (perf_counter() - recovery_started) * 1000
        async with sessions() as session:
            recovered = await WritingAIService(session, user.id, settings).get(expired.run_id)
        if recovered.error_code != "RUN_INTERRUPTED" or recovered.progress.get("ta") != partial:
            raise RuntimeError("Expired-lease recovery did not preserve the safe checkpoint")

        return {
            "scope": "local PostgreSQL queue component with deterministic fake provider; no HTTP or GPU throughput claim",
            "measured_at_utc": datetime.now(UTC).isoformat(),
            "source_identity": source_identity(ROOT / "backend"),
            "isolation": "runner ownership proof, non-superuser, fresh empty domain and no live DB peers verified before fixtures",
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "database": "isolated Docker PostgreSQL 17, loopback, 2 CPUs / 1 GiB, tmpfs",
                "database_connections": "independent sessions, bounded pool_size=5/max_overflow=0/pool_timeout=30s",
            },
            "input": {
                "runs": args.runs,
                "fixed_consumers": args.consumers,
                "global_running_cap": args.consumers,
                "per_run_llm_cap": settings.ai_writing_max_concurrent_llm_requests,
                "fake_delay_per_call_ms": args.delay_ms,
                "poll_seconds": settings.ai_writing_worker_poll_seconds,
                "lease_seconds": settings.ai_writing_lease_seconds,
            },
            "queue_wait_ms": latency_summary(
                [(run.started_at - run.created_at).total_seconds() * 1000 for run in rows]
            ),
            "accepted_to_completed_ms": latency_summary(
                [(run.completed_at - run.created_at).total_seconds() * 1000 for run in rows]
            ),
            "drain_ms_after_consumer_start": round(drain_ms, 3),
            "completed": len(rows),
            "failed": 0,
            "observed_peak_running_rows": peak_running,
            "observed_peak_local_run_tasks": peak_local_jobs,
            "observed_peak_fake_llm_calls": provider.peak_active,
            "fake_provider_calls": len(provider.calls),
            "cross_session_blocked_provider_cancel_ms": round(cancel_ms, 3),
            "expired_lease_scan_ms": round(recovery_ms, 3),
            "expired_lease_status": recovered.status.value,
            "expired_lease_error": recovered.error_code,
            "partial_checkpoint_preserved": True,
            "launch_burst_regression": {
                "persisted_queue_hints": 1000,
                "baseline_tasks_created": 1000,
                "candidate_tasks_created": 0,
                "evidence": "test_writing_durable_dispatch.py test_launch_is_a_hint; observed red then green, structural comparison only",
            },
            "limits": [
                "An earlier NullPool probe failed the 90s drain guard; no successful throughput metrics were emitted for that attempt",
                "One local component sample, no production capacity estimate or speedup claim",
                "Fake inference cost and queue drainage are not real provider throughput",
                "No claim of exactly-once provider invocation or billing",
                "Remote cancellation detection uses a heartbeat; already accepted provider work may continue remotely",
            ],
        }
    finally:
        await stop_writing_ai_workers()
        async with sessions() as session, session.begin():
            if attempts:
                await session.execute(
                    delete(Attempt).where(Attempt.id.in_([attempt.id for attempt in attempts]))
                )
            if test.id is not None:
                await session.execute(delete(DomainTest).where(DomainTest.id == test.id))
            if user.id is not None:
                await session.execute(delete(User).where(User.id == user.id))
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--consumers", type=int, default=2)
    parser.add_argument("--delay-ms", type=float, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.runs <= 100 or not 1 <= args.consumers <= 8 or not 0 <= args.delay_ms <= 1000:
        parser.error("Local probe supports 1..100 runs,1..8 consumers,0..1000ms fake delay")
    result = asyncio.run(measure(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "completed": result["completed"],
                "peak_running": result["observed_peak_running_rows"],
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 -- SQL exceptions may include credentials
        code = str(error) if isinstance(error, SafetyError) else type(error).__name__
        print(f"Writing probe stopped: {code}", file=sys.stderr)
        raise SystemExit(1) from None
