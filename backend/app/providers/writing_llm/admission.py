"""Bound OpenAI requests across graders sharing one process/event loop."""

import asyncio
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary

from app.providers.writing_llm.base import ProviderFailure


class OpenAIAdmission:
    def __init__(self, limit: int, max_queued: int):
        self.limit, self.max_queued = limit, max_queued
        self.semaphore = asyncio.Semaphore(limit)
        self.waiting = 0

    @asynccontextmanager
    async def slot(self):
        # No await separates admission and registration: a burst cannot allocate
        # an unbounded number of semaphore waiters on this event loop.
        if self.semaphore.locked() and self.waiting >= self.max_queued:
            raise ProviderFailure("AI_PROVIDER_BUSY")
        self.waiting += 1
        try:
            await self.semaphore.acquire()
        finally:
            self.waiting -= 1
        try:
            yield
        finally:
            self.semaphore.release()


# Values disappear after all requests drain, including cancelled requests. This
# avoids retaining event loops across tests/restarts; active callers own the gate.
_gates: WeakValueDictionary = WeakValueDictionary()


def admission(limit: int, max_queued: int) -> OpenAIAdmission:
    loop = asyncio.get_running_loop()
    gate = _gates.get(loop)
    if gate is None:
        gate = _gates[loop] = OpenAIAdmission(limit, max_queued)
    elif (gate.limit, gate.max_queued) != (limit, max_queued):
        # Speaking must inherit the shared account budget, not create another gate.
        raise ProviderFailure("AI_PROVIDER_CONFIGURATION_ERROR")
    return gate
