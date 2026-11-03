"""Idle SSE observation stays live without starting or changing a grading job."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from app.api.v1 import writing_ai as routes


async def test_idle_writing_sse_sends_comment_heartbeats_without_business_events(monkeypatch):
    clock = 0
    polls = 0
    original_sleep = asyncio.sleep

    async def sleep(_seconds):
        nonlocal clock
        clock += 1
        await original_sleep(0)

    @asynccontextmanager
    async def sessions():
        yield None

    class Service:
        async def snapshot(self, _run_id, after):
            nonlocal polls
            polls += 1
            assert after == 23
            return SimpleNamespace(status="RUNNING"), []

    async def connected():
        return False

    monkeypatch.setattr(routes, "WritingAIService", lambda *_args: Service())
    monkeypatch.setattr(routes, "monotonic", lambda: clock, raising=False)
    monkeypatch.setattr(routes.asyncio, "sleep", sleep)
    stream = routes.event_stream(
        SimpleNamespace(is_disconnected=connected),
        uuid4(),
        uuid4(),
        23,
        SimpleNamespace(sessions=sessions, settings=None),
    )
    try:
        assert await asyncio.wait_for(anext(stream), 0.1) == ": heartbeat\n\n"
        assert clock == 15 and polls == 16
        assert await asyncio.wait_for(anext(stream), 0.1) == ": heartbeat\n\n"
        assert clock == 30 and polls == 31
    finally:
        await stream.aclose()
