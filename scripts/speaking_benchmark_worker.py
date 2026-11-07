"""Separate CPU worker. Run with backend dependencies; native inference stays isolated."""

import argparse
import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


async def run(*, once=False, idle_seconds=5):
    from app.core.config import get_settings
    from app.core.database import SessionFactory, engine
    from app.services.speaking_benchmark_jobs import DiarizationJobRunner, availability
    from app.services.speaking_media import drain_media_cleanup

    settings = get_settings()
    ready = availability(settings)
    if not ready.can_queue:
        raise RuntimeError(ready.reason)
    runner = DiarizationJobRunner(SessionFactory, settings)
    try:
        while True:
            processed = await runner.run_once()
            # A failed delete remains in the transactional outbox for the next sweep.
            try:
                async with SessionFactory() as session:
                    await drain_media_cleanup(session, storage=runner.storage)
            except Exception:
                print("SPEAKING_BENCHMARK_CLEANUP_PENDING", flush=True)
            if once:
                return processed
            if not processed:
                await asyncio.sleep(idle_seconds)
    finally:
        await engine.dispose()


async def run_until_stopped(*, once=False):
    """Cancel once on SIGTERM, then await native subprocess and temporary-file cleanup."""
    task = asyncio.create_task(run(once=once))
    loop = asyncio.get_running_loop()
    previous = signal.getsignal(signal.SIGTERM)
    terminating = False

    def terminate(_signum, _frame):
        nonlocal terminating
        if not terminating:
            terminating = True
            loop.call_soon_threadsafe(task.cancel)

    signal.signal(signal.SIGTERM, terminate)
    try:
        return await task
    except asyncio.CancelledError:
        if not terminating:
            raise
    finally:
        signal.signal(signal.SIGTERM, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Claim at most one job, then exit.")
    args = parser.parse_args()
    try:
        asyncio.run(run_until_stopped(once=args.once))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
