"""CLI contracts run with offline queue/cleanup substitutes, never inference."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from scripts import speaking_benchmark_grading_worker as worker


def test_documented_cli_options_reach_worker(monkeypatch):
    received = []

    async def run(**kwargs):
        received.append(kwargs)

    monkeypatch.setattr(worker, "run_until_stopped", run)
    monkeypatch.setattr("sys.argv", ["worker", "--poll-interval", "0.25", "--limit", "2"])
    worker.main()
    assert received == [{"once": False, "poll_interval": 0.25, "limit": 2}]


@pytest.mark.parametrize(
    "arguments",
    [
        ["--poll-interval", "0"],
        ["--poll-interval", "-1"],
        ["--poll-interval", "nan"],
        ["--poll-interval", "inf"],
        ["--limit", "0"],
        ["--limit", "-1"],
        ["--once", "--limit", "2"],
    ],
)
def test_invalid_cli_bounds_never_start_worker(monkeypatch, arguments):
    async def forbidden(**kwargs):
        pytest.fail("Invalid CLI options must not construct a worker")

    monkeypatch.setattr(worker, "run_until_stopped", forbidden)
    monkeypatch.setattr("sys.argv", ["worker", *arguments])
    with pytest.raises(SystemExit) as error:
        worker.main()
    assert error.value.code == 2


async def test_job_limit_counts_claimed_runs_and_poll_interval_only_applies_when_idle(monkeypatch):
    from app.core import database
    from app.services import speaking_benchmark_grading_worker as runner_module
    from app.services import speaking_media

    queue = iter([False, True, False, True, True])
    claims, sleeps, cleanups = [], [], []
    disposed = asyncio.Event()

    class Queue:
        storage = object()

        async def run_once(self):
            processed = next(queue)
            claims.append(processed)
            return processed

    @asynccontextmanager
    async def session():
        yield object()

    async def cleanup(session, *, storage):
        cleanups.append(storage)

    async def sleep(seconds):
        sleeps.append(seconds)

    async def dispose():
        disposed.set()

    monkeypatch.setattr(runner_module, "GradingJobRunner", lambda *_: Queue())
    monkeypatch.setattr(database, "SessionFactory", session)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    monkeypatch.setattr(speaking_media, "drain_media_cleanup", cleanup)
    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    await worker.run(poll_interval=0.25, limit=2)
    assert claims == [False, True, False, True]
    assert sleeps == [0.25, 0.25]
    assert len(cleanups) == 4
    assert disposed.is_set()
