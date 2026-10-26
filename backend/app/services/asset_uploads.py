"""Bounded file staging outside Builder locks, with rollback compensation."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from app.models import Asset
from app.schemas.assets import AssetResponse
from app.services.asset_cleanup import compensate_files
from app.services.tests import TestService
from app.storage import LocalAssetStorage
from app.storage.local import StoredAsset


async def upload_asset(*, version_id, upload, category, asset_type, session, actor, settings):
    # Preserve authorization/conflict precedence without keeping these locks
    # during file I/O. Recheck under locks when attaching the staged file.
    async with session.begin():
        await TestService(session, actor=actor).ensure_draft(version_id)
    storage = LocalAssetStorage(settings.resolved_storage_root)
    original_name = Path((upload.filename or "upload").replace("\\", "/")).name[:255]
    mime_type = upload.content_type or "application/octet-stream"
    maximum = (
        (settings.max_image_upload_mb if category == "images" else settings.max_audio_upload_mb)
        * 1024
        * 1024
    )
    staging = asyncio.create_task(
        asyncio.to_thread(
            storage.store_stream,
            category=category,
            mime_type=mime_type,
            original_name=original_name,
            source=upload.file,
            max_bytes=maximum,
        )
    )
    stored = None
    try:
        # Cancellation must join the file writer before it can remove its output.
        stored = await asyncio.shield(staging)
        async with session.begin():
            await TestService(session, actor=actor).ensure_draft(version_id)
            asset = Asset(
                test_version_id=version_id,
                asset_type=asset_type,
                relative_path=stored.relative_path,
                mime_type=mime_type,
                original_name=original_name,
                file_size=stored.size,
                created_at=datetime.now(UTC),
            )
            session.add(asset)
            await session.flush()
            response = AssetResponse.model_validate(asset, from_attributes=True)
        return response
    except BaseException:
        if stored is None:
            result = (await asyncio.gather(staging, return_exceptions=True))[0]
            if isinstance(result, StoredAsset):
                stored = result
        if stored is not None:
            await compensate_files(session, storage, [stored.relative_path])
        raise
