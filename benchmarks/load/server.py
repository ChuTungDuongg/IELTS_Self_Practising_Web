"""Attested ASGI wrapper; importable only with a runner-generated private directory."""

import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

from benchmarks.load.runtime import read_run, verify_database
from benchmarks.load.safety import SafetyError
from benchmarks.load.source_identity import source_identity
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine

manifest, private = read_run(os.environ["LOAD_RUN_DIRECTORY"])
if manifest.get("source_identity") != source_identity(
    Path(private["environment"]["LOAD_APPLICATION_SOURCE_ROOT"])
):
    raise SafetyError("APPLICATION_SOURCE_CHANGED_SINCE_INIT")
for name, value in private["environment"].items():
    # Set before importing any app module; settings never see developer defaults.
    os.environ[name] = value

from benchmarks.load.telemetry import LoadTelemetry  # noqa: E402

from app.core.database import (  # noqa: E402 -- isolation before Settings import
    engine as application_engine,
)
from app.main import app as domain_app  # noqa: E402

monitor = LoadTelemetry(application_engine, private["environment"]["DATABASE_URL"])


@asynccontextmanager
async def lifespan(_):
    engine = create_async_engine(private["environment"]["DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            await verify_database(connection, manifest, private)
        monitor.start()
        async with domain_app.router.lifespan_context(domain_app):
            yield
    finally:
        await monitor.close()
        await engine.dispose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def ownership_gate(request: Request, call_next):
    if not hmac.compare_digest(request.headers.get("X-Load-Token", ""), private["token"]):
        return JSONResponse({"code": "ISOLATED_LOAD_ONLY"}, status_code=403)
    try:
        return await call_next(request)
    except Exception:  # noqa: BLE001 -- never log SQL parameters or private HTTP input
        return JSONResponse({"code": "LOAD_APPLICATION_FAILURE"}, status_code=503)


@app.get("/__load__/identity")
async def identity():
    engine = create_async_engine(private["environment"]["DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            await verify_database(connection, manifest, private)
    finally:
        await engine.dispose()
    return dict(manifest, runner_owned=True)


@app.get("/__load__/metrics")
async def metrics():
    return monitor.snapshot()


app.mount("/", domain_app)
