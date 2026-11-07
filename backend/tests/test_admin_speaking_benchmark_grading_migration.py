"""Frozen additive migration in a throwaway schema, preserving Phase 1 rows."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from testsupport.test_database import validate_test_database_url


async def test_grading_upgrade_downgrade_preserves_phase1_and_legacy_rows():
    url = os.environ.get("P2_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Explicit disposable P2_TEST_DATABASE_URL required")
    validate_test_database_url(url, get_settings().database_url)
    modules = []
    for filename in (
        "20261107_0045_speaking_benchmark.py",
        "20261108_0046_speaking_benchmark_grading.py",
    ):
        spec = importlib.util.spec_from_file_location(
            filename, Path(__file__).parents[1] / "alembic/versions" / filename
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    assert modules[1].down_revision == modules[0].revision
    schema = "speaking_evaluation_test_" + uuid4().hex
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await conn.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
            await conn.execute(text("CREATE TABLE legacy_sentinel (value text)"))
            await conn.execute(text("INSERT INTO legacy_sentinel VALUES ('keep historical data')"))

            def apply(sync, module, action):
                with Operations.context(MigrationContext.configure(sync)):
                    getattr(module, action)()

            await conn.run_sync(lambda sync: apply(sync, modules[0], "upgrade"))
            await conn.run_sync(lambda sync: apply(sync, modules[1], "upgrade"))
            names = await conn.run_sync(lambda sync: inspect(sync).get_table_names(schema=schema))
            assert "speaking_benchmark_grading_checkpoints" in names
            await conn.run_sync(lambda sync: apply(sync, modules[1], "downgrade"))
            assert (
                await conn.scalar(text("SELECT value FROM legacy_sentinel"))
                == "keep historical data"
            )
            assert await conn.scalar(text("SELECT count(*) FROM speaking_benchmark_samples")) == 0
            await conn.run_sync(lambda sync: apply(sync, modules[1], "upgrade"))
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
