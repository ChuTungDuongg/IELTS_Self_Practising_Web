import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.exceptions import AppError, app_error_handler
from app.services.speaking_ai_worker import SpeakingAIWorker, stop_speaking_ai_workers
from app.services.speaking_transcript_worker import (
    SpeakingTranscriptWorker,
    stop_speaking_transcript_workers,
)
from app.services.writing_ai_worker import stop_writing_ai_workers
from app.storage.factory import initialize_asset_storage

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(initialize_asset_storage, settings)
    from app.services.speaking_media import cleanup_private_media

    try:
        await cleanup_private_media()
        await SpeakingTranscriptWorker(SessionFactory, settings).recover()
        await SpeakingAIWorker(SessionFactory, settings).recover()
        yield
    finally:
        try:
            await stop_speaking_ai_workers()
        finally:
            try:
                await stop_speaking_transcript_workers()
            finally:
                await stop_writing_ai_workers()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
if os.environ.get("IELTS_MODAL_WEB_TIMINGS", "").lower() in {"1", "true", "yes"}:
    from app.core.request_timing import RequestTimingMiddleware

    app.add_middleware(RequestTimingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
app.include_router(api_router, prefix=settings.api_v1_prefix)
