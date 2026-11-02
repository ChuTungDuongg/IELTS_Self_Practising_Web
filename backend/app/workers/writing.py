"""Run with ``python -m app.workers.writing``; disable consumers on Web replicas.

This process needs the same database, asset storage and provider configuration
as the API. No provider work is coupled to an HTTP/SSE observer.
"""

import asyncio
import signal

from app.core.config import get_settings
from app.core.database import SessionFactory, engine
from app.providers.writing_llm import is_configured
from app.services.writing_ai_worker import WritingAIWorker, stop_writing_ai_workers
from app.storage.factory import initialize_asset_storage


async def main():
    settings = get_settings()
    if not settings.ai_writing_worker_enabled or not is_configured(settings):
        raise RuntimeError("Enable and configure Writing AI and its dedicated consumer")
    await asyncio.to_thread(initialize_asset_storage, settings)
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    handlers = []
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous = signal.getsignal(signum)
        try:
            loop.add_signal_handler(signum, shutdown.set)
            native = True
        except NotImplementedError:
            # Windows' default event loop has no add_signal_handler support.
            signal.signal(signum, lambda *_args: loop.call_soon_threadsafe(shutdown.set))
            native = False
        handlers.append((signum, previous, native))
    try:
        WritingAIWorker(SessionFactory, settings).start()
        await shutdown.wait()
    finally:
        try:
            await stop_writing_ai_workers()
        finally:
            await engine.dispose()
            for signum, previous, native in handlers:
                if native:
                    loop.remove_signal_handler(signum)
                signal.signal(signum, previous)


if __name__ == "__main__":
    asyncio.run(main())
