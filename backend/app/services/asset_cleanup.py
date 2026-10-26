"""Compensate failed file writes without deleting a committed reference."""

import asyncio
import logging

from sqlalchemy import select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset
from app.models.speaking import SpeakingAudioChunk
from app.models.speaking_transcript import SpeakingNormalizedAudio

logger = logging.getLogger(__name__)


async def compensate_files(session, storage, paths):
    """Check commit ambiguity on a fresh session, after the owner transaction exits.

    Paths are server-generated and owned by this operation. If PostgreSQL is
    unavailable, retaining the file is safer than deleting potentially committed
    media; report the need for storage reconciliation without private data.
    """
    paths = set(paths)
    if not paths:
        return

    async def cleanup():
        try:
            async with AsyncSession(bind=session.bind) as verification:
                referenced = set(
                    await verification.scalars(
                        union_all(
                            select(Asset.relative_path).where(Asset.relative_path.in_(paths)),
                            select(SpeakingAudioChunk.storage_key).where(
                                SpeakingAudioChunk.storage_key.in_(paths)
                            ),
                            select(SpeakingNormalizedAudio.storage_key).where(
                                SpeakingNormalizedAudio.storage_key.in_(paths)
                            ),
                        )
                    )
                )
            for path in paths - referenced:
                await asyncio.to_thread(storage.delete, path)
        except Exception:
            logger.warning(
                "Asset compensation needs storage reconciliation; reference check or deletion failed"
            )

    task = asyncio.create_task(cleanup())
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise
