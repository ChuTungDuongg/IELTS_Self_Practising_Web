from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TestVersionModeration


class ContentGovernanceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, *, version_id=None, status=None, limit=100, offset=0):
        statement = select(TestVersionModeration).order_by(
            TestVersionModeration.submitted_at.desc(), TestVersionModeration.id
        )
        if version_id is not None:
            statement = statement.where(TestVersionModeration.test_version_id == version_id)
        if status is not None:
            statement = statement.where(TestVersionModeration.status == status)
        return list(await self.session.scalars(statement.limit(limit).offset(offset)))
