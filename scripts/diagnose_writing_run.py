"""Read-only local operator tool; prints allowlisted persisted run metadata."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.evaluation.task1.diagnostics import run_diagnostics  # noqa: E402
from app.models import WritingAIGradingRun  # noqa: E402


async def read_run(run_id):
    settings = Settings(_env_file=ROOT / "backend" / ".env")
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            run = await session.scalar(
                select(WritingAIGradingRun).where(WritingAIGradingRun.id == run_id)
            )
            return run_diagnostics(run) if run else None
    finally:
        await engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=UUID, required=True)
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(read_run(args.run_id))
    except Exception:
        print("WRITING_DIAGNOSTIC_READ_FAILED", file=sys.stderr)
        return 2
    if report is None:
        print("WRITING_DIAGNOSTIC_RUN_NOT_FOUND", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
