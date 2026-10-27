"""Database-free query diagnostics: comparisons must not load a user's full history."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.services.analytics import AnalyticsService


async def test_comparison_query_is_bounded_to_two_owned_finalized_attempts():
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = []
    user_id, left_id, right_id = uuid4(), uuid4(), uuid4()
    with pytest.raises(AppError) as caught:
        await AnalyticsService(session, user_id).compare(left_id, right_id)
    assert caught.value.code == "ANALYTICS_ATTEMPT_NOT_FOUND"
    statement = session.scalars.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "attempts.user_id =" in sql
    assert "attempts.scope =" in sql
    assert "attempts.id IN" in sql
    assert "attempts.status NOT IN" in sql
    assert user_id in compiled.params.values()
    assert not any("Attempt.events" in str(option.path) for option in statement._with_options)
    assert any(
        set(value) == {left_id, right_id}
        for value in compiled.params.values()
        if isinstance(value, list)
    )
    session.scalars.assert_awaited_once()
