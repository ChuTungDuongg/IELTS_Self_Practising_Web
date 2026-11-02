"""Unavailable persistence must route the consumer through its retry wait."""

import asyncio
from contextlib import asynccontextmanager, suppress

from app.core.config import Settings
from app.services.writing_ai_worker import WritingAIWorker


async def test_unclaimed_database_failure_waits_before_retrying():
    entries = 0

    @asynccontextmanager
    async def unavailable():
        nonlocal entries
        entries += 1
        raise ConnectionError("fictional local database unavailable")
        yield  # pragma: no cover

    class ObservedWait:
        def __init__(self):
            self.entered = asyncio.Event()

        def clear(self):
            pass

        async def wait(self):
            self.entered.set()
            await asyncio.Event().wait()

    worker = WritingAIWorker(unavailable, Settings(_env_file=None))
    worker.wakeup = ObservedWait()
    consumer = asyncio.create_task(worker._consume())
    try:
        await asyncio.wait_for(worker.wakeup.entered.wait(), 0.5)
        assert entries == 1
    finally:
        consumer.cancel()
        with suppress(asyncio.CancelledError):
            await consumer


async def test_claim_commit_failure_is_not_reported_as_executed(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.repositories.writing_ai import WritingAIRepository

    @asynccontextmanager
    async def failed_commit():
        yield
        raise ConnectionError("fictional commit acknowledgement failure")

    @asynccontextmanager
    async def sessions():
        yield SimpleNamespace(begin=failed_commit)

    run = SimpleNamespace(id=uuid4(), lease_token=uuid4())

    async def claim(*_args, **_kwargs):
        return run

    async def append(*_args, **_kwargs):
        pass

    monkeypatch.setattr(WritingAIRepository, "claim", claim)
    monkeypatch.setattr(WritingAIRepository, "append_event", append)
    monkeypatch.setattr("app.services.writing_ai_worker.persist_activity", lambda *_args: None)
    assert await WritingAIWorker(sessions, Settings(_env_file=None)).execute(None) is False
