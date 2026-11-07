"""Separate CPU grading worker; disabled by default, never loads diarization models."""

import argparse
import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


async def run(*, once=False):
    from app.core.config import get_settings
    from app.core.database import SessionFactory, engine
    from app.services.speaking_benchmark_grading_worker import GradingJobRunner
    from app.services.speaking_media import drain_media_cleanup

    runner = GradingJobRunner(SessionFactory, get_settings())
    try:
        while True:
            processed = await runner.run_once()
            async with SessionFactory() as session:
                await drain_media_cleanup(session, storage=runner.storage)
            if once:
                return processed
            if not processed:
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


async def run_until_stopped(*, once=False):
    task = asyncio.create_task(run(once=once))
    loop = asyncio.get_running_loop()
    previous = signal.getsignal(signal.SIGTERM)
    stopping = False

    def terminate(*_):
        nonlocal stopping
        if not stopping:
            stopping = True
            loop.call_soon_threadsafe(task.cancel)

    signal.signal(signal.SIGTERM, terminate)
    try:
        return await task
    except asyncio.CancelledError:
        if not stopping:
            raise
    finally:
        signal.signal(signal.SIGTERM, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run_until_stopped(once=args.once))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
