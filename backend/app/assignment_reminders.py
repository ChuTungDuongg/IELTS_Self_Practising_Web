"""One-shot assignment reminder runner: python -m app.assignment_reminders --limit 100."""

import argparse
import asyncio
import json

from app.core.database import SessionFactory, engine
from app.services.assignment_reminders import generate_reminders


async def run(limit):
    try:
        async with SessionFactory() as session:
            print(json.dumps(await generate_reminders(session, limit=limit)))
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100, choices=range(1, 1001), metavar="1..1000")
    args = parser.parse_args()
    asyncio.run(run(args.limit))


if __name__ == "__main__":
    main()
