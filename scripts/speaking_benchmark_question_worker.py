"""Separate CPU Question Assistant worker; live inference remains explicitly opt-in."""

import argparse
import asyncio
import math
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


async def run(*, once=False, poll_interval=5.0, limit=None):
    from app.core.config import get_settings
    from app.core.database import SessionFactory, engine
    from app.services.speaking_benchmark_questions_worker import QuestionJobRunner
    from app.services.speaking_media import drain_media_cleanup

    runner = QuestionJobRunner(SessionFactory, get_settings())
    processed_count = 0
    try:
        while True:
            processed = await runner.run_once()
            processed_count += int(processed)
            async with SessionFactory() as session:
                await drain_media_cleanup(session, storage=runner.storage)
            if once or (limit is not None and processed_count >= limit):
                return processed
            if not processed:
                await asyncio.sleep(poll_interval)
    finally:
        await engine.dispose()


async def run_until_stopped(*, once=False, poll_interval=5.0, limit=None):
    task = asyncio.create_task(run(once=once, poll_interval=poll_interval, limit=limit))
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
    bounds = parser.add_mutually_exclusive_group()
    bounds.add_argument("--once", action="store_true")
    bounds.add_argument("--limit", type=int)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    args = parser.parse_args()
    if not math.isfinite(args.poll_interval) or args.poll_interval <= 0:
        parser.error("--poll-interval must be finite and positive")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    try:
        asyncio.run(
            run_until_stopped(once=args.once, poll_interval=args.poll_interval, limit=args.limit)
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
