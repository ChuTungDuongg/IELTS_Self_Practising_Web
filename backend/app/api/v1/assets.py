from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_admin
from app.core.config import get_settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.models import Asset
from app.models.enums import AssetType, UserRole
from app.schemas.assets import AssetResponse
from app.services.asset_access import can_user_read_asset
from app.services.tests import TestService
from app.storage import LocalAssetStorage

router = APIRouter(prefix="/assets", tags=["assets"])


async def _upload(
    *,
    version_id: UUID,
    upload: UploadFile,
    category: str,
    asset_type: AssetType,
    session: AsyncSession,
) -> AssetResponse:
    settings = get_settings()
    original_name = Path((upload.filename or "upload").replace("\\", "/")).name[:255]
    content = await upload.read()
    maximum = (
        (settings.max_image_upload_mb if category == "images" else settings.max_audio_upload_mb)
        * 1024
        * 1024
    )
    async with session.begin():
        await TestService(session).ensure_draft(version_id)
        stored = LocalAssetStorage(settings.resolved_storage_root).store(
            category=category,
            mime_type=upload.content_type or "application/octet-stream",
            original_name=original_name,
            content=content,
            max_bytes=maximum,
        )
        asset = Asset(
            test_version_id=version_id,
            asset_type=asset_type,
            relative_path=stored.relative_path,
            mime_type=upload.content_type or "application/octet-stream",
            original_name=original_name,
            file_size=stored.size,
            created_at=datetime.now(UTC),
        )
        session.add(asset)
        await session.flush()
        response = AssetResponse.model_validate(asset, from_attributes=True)
    return response


@router.post(
    "/images",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def upload_image(
    test_version_id: UUID = Form(),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
) -> AssetResponse:
    return await _upload(
        version_id=test_version_id,
        upload=file,
        category="images",
        asset_type=AssetType.WRITING_TASK_IMAGE,
        session=session,
    )


@router.post(
    "/question-images",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def upload_question_image(
    test_version_id: UUID = Form(),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
) -> AssetResponse:
    return await _upload(
        version_id=test_version_id,
        upload=file,
        category="images",
        asset_type=AssetType.QUESTION_IMAGE,
        session=session,
    )


@router.post(
    "/audio",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def upload_audio(
    test_version_id: UUID = Form(),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
) -> AssetResponse:
    return await _upload(
        version_id=test_version_id,
        upload=file,
        category="audio",
        asset_type=AssetType.LISTENING_AUDIO,
        session=session,
    )


@router.get("/{asset_id}/content", response_class=FileResponse)
async def get_asset_content(
    asset_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    asset = await session.scalar(select(Asset).where(Asset.id == asset_id))
    if asset is None:
        raise AppError("ASSET_NOT_FOUND", "The asset does not exist.", 404)
    if user.role != UserRole.ADMIN and not await can_user_read_asset(session, user.id, asset):
        raise AppError("ASSET_NOT_FOUND", "The asset does not exist.", 404)
    path = LocalAssetStorage(get_settings().resolved_storage_root).resolve(asset.relative_path)
    return FileResponse(
        path,
        media_type=asset.mime_type,
        filename=asset.original_name,
        content_disposition_type="inline",
    )
