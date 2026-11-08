"""SIGTERM must await the worker task's cancellation cleanup, without native inference."""

import asyncio
import signal

import pytest
from scripts import speaking_benchmark_grading_worker, speaking_benchmark_worker

pytestmark = pytest.mark.parametrize(
    "worker", [speaking_benchmark_worker, speaking_benchmark_grading_worker]
)


async def test_sigterm_cancels_once_and_waits_for_worker_cleanup(monkeypatch, worker):
    started, cleanup_started, release_cleanup = (asyncio.Event() for _ in range(3))
    observed = []

    async def fake_run(**kwargs):
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            observed.append("cancelled")
            cleanup_started.set()
            await release_cleanup.wait()
            observed.append("cleaned")
            raise

    monkeypatch.setattr(worker, "run", fake_run)
    previous = signal.getsignal(signal.SIGTERM)
    assert hasattr(worker, "run_until_stopped"), "Worker needs a graceful SIGTERM boundary"
    task = asyncio.create_task(worker.run_until_stopped(once=True))
    try:
        await asyncio.wait_for(started.wait(), 1)
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)
        await asyncio.wait_for(cleanup_started.wait(), 1)
        handler(signal.SIGTERM, None)
        await asyncio.sleep(0)
        assert not task.done() and observed == ["cancelled"]
        release_cleanup.set()
        await asyncio.wait_for(task, 1)
        assert observed == ["cancelled", "cleaned"]
        assert signal.getsignal(signal.SIGTERM) == previous
    finally:
        release_cleanup.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_non_shutdown_worker_failure_is_not_hidden(monkeypatch, worker):
    async def failed_run(**kwargs):
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(worker, "run", failed_run)
    assert hasattr(worker, "run_until_stopped"), "Worker needs a graceful SIGTERM boundary"
    with pytest.raises(RuntimeError, match="fixture failure"):
        await worker.run_until_stopped(once=True)
