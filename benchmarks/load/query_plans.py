"""Rollback-only synthetic history query plans in an attested load database.

No HTTP requests, production targets, permanent fixture rows or migrations.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from benchmarks.load.runtime import read_run, verify_database
from benchmarks.load.source_identity import source_identity
from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import Attempt, User

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def plan_summary(value):
    """No SQL, parameters, user IDs or fixture content in published evidence."""
    keep = {
        "Node Type",
        "Relation Name",
        "Index Name",
        "Plan Rows",
        "Actual Rows",
        "Actual Loops",
        "Actual Startup Time",
        "Actual Total Time",
        "Sort Method",
        "Sort Space Used",
        "Sort Space Type",
        "Shared Hit Blocks",
        "Shared Read Blocks",
        "Rows Removed by Filter",
        "Planning Time",
        "Execution Time",
    }
    if isinstance(value, list):
        return [plan_summary(item) for item in value]
    return {
        key: plan_summary(item) if key in {"Plan", "Plans"} else item
        for key, item in value.items()
        if key in keep or key in {"Plan", "Plans"}
    }


async def measure(directory):
    manifest, private = read_run(directory)
    fixture = json.loads((directory / "fixtures.local.json").read_text(encoding="utf-8"))
    engine = create_async_engine(
        private["environment"]["DATABASE_URL"], pool_size=1, max_overflow=0
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await verify_database(connection, manifest, private)
                await connection.execute(text("SET LOCAL statement_timeout='15s'"))
                before = await connection.scalar(select(func.count()).select_from(Attempt))
                now = datetime.now(UTC)
                identities = [uuid4() for _ in range(1000)]
                await connection.execute(
                    insert(User),
                    [
                        {
                            "id": identity,
                            "email": f"plan-{identity}@example.test",
                            "display_name": "Fictional plan learner",
                            "role": "USER",
                            "is_active": False,
                            "email_verified": False,
                        }
                        for identity in identities
                    ],
                )
                rows = [
                    {
                        "id": uuid4(),
                        "user_id": identity,
                        "test_version_id": fixture["version_id"],
                        "module_type": "READING",
                        "timer_mode": "COUNT_UP",
                        "status": "SUBMITTED",
                        "started_at": now - timedelta(days=sequence),
                        "last_active_at": now,
                        "finished_at": now,
                        "elapsed_seconds": 300,
                    }
                    for identity in identities
                    for sequence in range(10)
                ]
                for offset in range(0, len(rows), 1000):
                    await connection.execute(insert(Attempt), rows[offset : offset + 1000])
                # Statistics cover the new synthetic rows; data changes still roll back.
                await connection.execute(text("ANALYZE attempts"))
                statements = {
                    "history_root": select(Attempt)
                    .where(Attempt.user_id == identities[0])
                    .order_by(Attempt.started_at.desc()),
                    "save_attempt_lock": select(Attempt)
                    .where(Attempt.id == rows[0]["id"], Attempt.user_id == identities[0])
                    .with_for_update(),
                }
                plans = {}
                for name, statement in statements.items():
                    query = str(
                        statement.compile(
                            dialect=connection.dialect, compile_kwargs={"literal_binds": True}
                        )
                    )
                    result = await connection.scalar(
                        text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query)
                    )
                    plans[name] = plan_summary(
                        json.loads(result) if isinstance(result, str) else result
                    )
            finally:
                await transaction.rollback()
            after = await connection.scalar(select(func.count()).select_from(Attempt))
            if before != after:
                raise RuntimeError("Rollback row-count mismatch")
        return {
            "scope": "attested rollback-only query component; no API/ORM graph capacity claim",
            "measured_at_utc": datetime.now(UTC).isoformat(),
            "source_identity": await asyncio.to_thread(source_identity, BACKEND),
            "synthetic_users": 1000,
            "synthetic_attempts": 10000,
            "attempts_per_synthetic_user": 10,
            "existing_attempts_before": before,
            "existing_attempts_after_rollback": after,
            "plans": plans,
            "limitations": [
                "One frozen version, no answers/media in added history rows",
                "One local warm-cache sample; EXPLAIN overhead present",
                "Only root history and lock queries, not selectinload graph/HTTP",
                "No new index or before-after SQL optimization is claimed",
            ],
        }
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(measure(args.directory.resolve()))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Synthetic plan evidence saved; rollback confirmed")


if __name__ == "__main__":
    main()
