"""Disposable migrated database for committed, multi-connection staff fixtures."""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@asynccontextmanager
async def isolated_staff_database():
    url = get_settings().database_url
    database = make_url(url).database or ""
    assert os.environ.get("TEST_DATABASE_URL") == url
    assert database.startswith("test_") or database.endswith("_test") or "_test_" in database
    name = "test_classroom_staff_" + uuid4().hex
    test_url = make_url(url).set(database=name).render_as_string(hide_password=False)
    admin = create_async_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    engine = None
    created = False
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "head",
            cwd=Path(__file__).parents[1],
            env={**os.environ, "DATABASE_URL": test_url, "TEST_DATABASE_URL": test_url},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate()
        assert process.returncode == 0, output.decode(errors="replace").replace(
            test_url, "[test database]"
        )
        engine = create_async_engine(test_url, poolclass=NullPool)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        if engine is not None:
            await engine.dispose()
        if created:
            async with admin.connect() as connection:
                # Only this fixture's random database; append-only audit stays enforced.
                await connection.execute(text(f'DROP DATABASE "{name}"'))
        await admin.dispose()
