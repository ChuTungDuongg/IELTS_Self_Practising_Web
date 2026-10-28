"""HTTP date validation stays offline and never opens an application database."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.v1.analytics import router
from app.core.database import get_session
from app.core.exceptions import AppError, app_error_handler
from app.services.analytics import AnalyticsService


@pytest.fixture
def analytics_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(AppError, app_error_handler)
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = []
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.state.analytics_session = session
    return app


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-10-01T00:00:00"},
        {"end": "2026-11-01T00:00:00"},
        {"start": "2026-11-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
        {"start": "2026-10-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
        {"start": "2010-01-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
    ],
)
async def test_analytics_rejects_invalid_date_ranges(analytics_app: FastAPI, params):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=analytics_app), base_url="http://test"
    ) as client:
        response = await client.get("/analytics", params=params)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"start": "2026-10-01T00:00:00Z"},
        {"end": "2026-11-01T00:00:00Z"},
        {"start": "2026-10-01T07:00:00+07:00", "end": "2026-11-01T00:00:00Z"},
        {
            "start": "2026-10-01T00:00:00Z",
            "end": (datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=3660)).isoformat(),
        },
    ],
)
async def test_analytics_accepts_aware_optional_date_ranges(analytics_app: FastAPI, params):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=analytics_app), base_url="http://test"
    ) as client:
        response = await client.get("/analytics", params=params)
    assert response.status_code == 200
    assert response.json()["total_finalized_attempts"] == 0


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 10, 1), None),
        (None, datetime(2026, 10, 1)),
        (datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)),
    ],
)
async def test_service_rejects_invalid_range_before_querying(start, end):
    session = AsyncMock(spec=AsyncSession)
    with pytest.raises(AppError) as caught:
        await AnalyticsService(session, uuid4()).dashboard(start=start, end=end)
    assert caught.value.status_code == 422
    session.scalars.assert_not_awaited()


async def test_http_scope_reaches_both_owned_database_queries(analytics_app: FastAPI):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=analytics_app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/analytics",
            params={"start": "2026-10-01T07:00:00+07:00", "end": "2026-10-08T00:00:00Z"},
        )
    assert response.status_code == 200
    queries = analytics_app.state.analytics_session.scalars.await_args_list
    assert len(queries) == 2
    for query, table in zip(queries, ("attempts", "test_sessions"), strict=True):
        compiled = query.args[0].compile(dialect=postgresql.dialect())
        sql = str(compiled)
        assert f"{table}.user_id =" in sql
        assert ">=" in sql
        assert " < " in sql
        assert datetime(2026, 10, 1, tzinfo=UTC) in compiled.params.values()
        assert datetime(2026, 10, 8, tzinfo=UTC) in compiled.params.values()
