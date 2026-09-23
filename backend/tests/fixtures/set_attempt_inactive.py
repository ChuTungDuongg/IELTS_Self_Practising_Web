"""Local Playwright fixture: move only one active attempt beyond the AFK threshold."""

import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.core.database import SessionFactory
from app.models.entities import Attempt
from app.models.enums import AttemptStatus


async def main(attempt_id: uuid.UUID) -> None:
    async with SessionFactory() as session, session.begin():
        result = await session.execute(
            update(Attempt)
            .where(Attempt.id == attempt_id, Attempt.status == AttemptStatus.IN_PROGRESS)
            .values(last_active_at=datetime.now(UTC) - timedelta(minutes=6))
        )
        if result.rowcount != 1:
            raise RuntimeError("Expected exactly one active fixture attempt")


if __name__ == "__main__":
    asyncio.run(main(uuid.UUID(sys.argv[1])))
