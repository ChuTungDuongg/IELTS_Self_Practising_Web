"""Disposable PostgreSQL database for DDL/concurrency tests; never drops configured data."""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]


async def migrate(url, *args):
    env = {**os.environ, "DATABASE_URL": url}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        *args,
        cwd=BACKEND_ROOT,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    assert process.returncode == 0, output.decode("utf-8", errors="replace")[-4000:]


@asynccontextmanager
async def disposable_database():
    source = make_url(get_settings().database_url)
    name = "tacs_test_" + uuid4().hex
    admin = create_async_engine(source, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    url = source.set(database=name).render_as_string(hide_password=False)
    engine = create_async_engine(url)
    try:
        await migrate(url, "upgrade", "head")
        yield engine, url
    finally:
        await engine.dispose()
        assert name.startswith("tacs_test_") and len(name) == len("tacs_test_") + 32
        async with admin.connect() as connection:
            await connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.dispose()
