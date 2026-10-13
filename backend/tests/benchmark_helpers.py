"""Isolated real PostgreSQL fixtures; never reset application data."""

import importlib.util
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def migration():
    path = Path(__file__).parents[1] / "alembic/versions/20261013_0035_writing_benchmark_bank.py"
    spec = importlib.util.spec_from_file_location("benchmark_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migrate(connection, direction):
    with Operations.context(MigrationContext.configure(connection)):
        getattr(migration(), direction)()


@asynccontextmanager
async def isolated_bank():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Independent PostgreSQL coverage requires TEST_DATABASE_URL")
    schema = "benchmark_test_" + uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    engine = None
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await connection.run_sync(lambda conn: migrate(conn, "upgrade"))
        engine = create_async_engine(
            url,
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": schema}},
        )
        yield engine, async_sessionmaker(engine, expire_on_commit=False)
    finally:
        if engine is not None:
            await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()
