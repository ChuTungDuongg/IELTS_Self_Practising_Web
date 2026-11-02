"""Connection-budget configuration, without connecting to PostgreSQL."""

import runpy
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.core import config
from app.core.config import Settings


@pytest.fixture(autouse=True)
def clean_pool_environment(monkeypatch):
    for name in (
        "DATABASE_POOL_SIZE",
        "DATABASE_MAX_OVERFLOW",
        "DATABASE_POOL_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_pool_settings_preserve_existing_connection_budget():
    settings = Settings(_env_file=None)
    assert settings.database_pool_size == 5
    assert settings.database_max_overflow == 10
    assert settings.database_pool_timeout_seconds == 30


def test_database_credentials_are_not_in_settings_representation():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://fixture:pool-fixture-secret@127.0.0.1/fixture_test",
    )
    assert "pool-fixture-secret" not in repr(settings)


def test_pool_environment_overrides_are_typed(monkeypatch):
    monkeypatch.setenv("DATABASE_POOL_SIZE", "7")
    monkeypatch.setenv("DATABASE_MAX_OVERFLOW", "0")
    monkeypatch.setenv("DATABASE_POOL_TIMEOUT_SECONDS", "1.25")

    settings = Settings(_env_file=None)

    assert settings.database_pool_size == 7
    assert settings.database_max_overflow == 0
    assert settings.database_pool_timeout_seconds == 1.25


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_pool_size": 0},
        {"database_pool_size": -1},
        {"database_max_overflow": -1},
        {"database_pool_timeout_seconds": 0},
        {"database_pool_timeout_seconds": -1},
        {"database_pool_timeout_seconds": float("inf")},
        {"database_pool_timeout_seconds": float("nan")},
    ],
)
def test_pool_configuration_rejects_unbounded_or_invalid_limits(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({}, (5, 10, 30)),
        (
            {
                "database_pool_size": 3,
                "database_max_overflow": 0,
                "database_pool_timeout_seconds": 0.5,
            },
            (3, 0, 0.5),
        ),
    ],
)
async def test_database_engine_applies_pool_budget_without_opening_connections(
    monkeypatch, overrides, expected
):
    settings = Settings(_env_file=None, **overrides)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    # Execute the actual engine module without replacing the application's shared engine.
    namespace = runpy.run_path(str(Path(config.__file__).with_name("database.py")))
    engine = namespace["engine"]
    try:
        pool = engine.pool
        assert isinstance(pool, AsyncAdaptedQueuePool)
        assert (pool.size(), pool._max_overflow, pool.timeout()) == expected
        assert pool.checkedout() == 0
        assert pool._pre_ping is True
    finally:
        await engine.dispose()
