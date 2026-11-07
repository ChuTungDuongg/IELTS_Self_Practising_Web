"""The additive revision is exercised in a throwaway schema, never application tables."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from testsupport.test_database import validate_test_database_url


async def test_additive_migration_upgrade_constraints_downgrade_and_reupgrade():
    url = os.environ.get("P2_TEST_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Explicit disposable TEST_DATABASE_URL required")
    validate_test_database_url(url, get_settings().database_url)
    path = Path(__file__).parents[1] / "alembic/versions/20261107_0045_speaking_benchmark.py"
    spec = importlib.util.spec_from_file_location("speaking_lab_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "20261102_0044"
    schema = "speaking_lab_test_" + uuid4().hex
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await conn.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
            await conn.execute(text("CREATE TABLE legacy_sentinel (value text NOT NULL)"))
            await conn.execute(
                text("INSERT INTO legacy_sentinel VALUES ('preserve historical data')")
            )

            def apply(sync, action):
                with Operations.context(MigrationContext.configure(sync)):
                    getattr(migration, action)()

            await conn.run_sync(lambda sync: apply(sync, "upgrade"))
            names = await conn.run_sync(lambda sync: inspect(sync).get_table_names(schema=schema))
            assert len([name for name in names if name.startswith("speaking_benchmark_")]) == 4
            constraints = await conn.run_sync(
                lambda sync: inspect(sync).get_check_constraints("speaking_benchmark_human_labels")
            )
            assert any("overall_half_band" in constraint["name"] for constraint in constraints)
            owner, sample = uuid4(), uuid4()
            await conn.execute(text("INSERT INTO users VALUES (:id)"), {"id": owner})
            await conn.execute(
                text(
                    "INSERT INTO speaking_benchmark_samples (id,owner_id,code,audio_key,source_sha256,mime_type,byte_size,duration_ms,candidate_id,split,source_note,rights_confirmed,status,revision,review_revision,label_revision) VALUES (:id,:owner,'X','private/key',:sha,'audio/wav',1,1000,'','DEV','fixture',true,'DRAFT',1,0,0)"
                ),
                {"id": sample, "owner": owner, "sha": "a" * 64},
            )
            for score in ("6.25", "10"):
                with pytest.raises(IntegrityError):
                    async with conn.begin_nested():
                        await conn.execute(
                            text(
                                "INSERT INTO speaking_benchmark_human_labels (sample_id,revision,overall,provenance,reference,verified,examiner,notes) VALUES (:id,1,:score,'unverified','',false,'','')"
                            ),
                            {"id": sample, "score": float(score)},
                        )
            await conn.run_sync(lambda sync: apply(sync, "downgrade"))
            assert (
                await conn.scalar(text("SELECT value FROM legacy_sentinel"))
                == "preserve historical data"
            )
            await conn.run_sync(lambda sync: apply(sync, "upgrade"))
            assert await conn.scalar(text("SELECT count(*) FROM speaking_benchmark_samples")) == 0
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
