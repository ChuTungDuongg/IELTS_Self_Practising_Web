import asyncio
import hashlib
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domains.scoring.writing import WritingScoringRequest
from app.domains.writing.task_types import WritingTaskType
from app.models import Asset, WritingTask
from app.models.enums import AssetType
from app.providers.writing_llm.base import ImagePart
from app.schemas.chart_cross_check import ChartSpecialistIdentity
from app.storage import LocalAssetStorage

# Composite scoring/fingerprint label; the visual contract is versioned separately.
TASK1_PROMPT_VERSION = "mts-task1-visual-v5"
TASK1_VISUAL_CONTRACT_VERSION = "mts-task1-visual-v3"
TASK1_SCORING_PROMPT_VERSION = "mts-task1-scoring-v5"


class Task1ScoringRequest(WritingScoringRequest):
    task_number: Literal[1] = 1
    task_type: WritingTaskType
    image: ImagePart | None = Field(default=None, exclude=True, repr=False)
    chart_specialist: ChartSpecialistIdentity = Field(default_factory=ChartSpecialistIdentity)

    @property
    def image_checksum(self) -> str:
        return hashlib.sha256(self.image.data).hexdigest() if self.image else ""


async def load_task1_image(
    session: AsyncSession, task: WritingTask, version_id: UUID, settings: Settings
) -> ImagePart:
    asset = await session.get(Asset, task.image_asset_id) if task.image_asset_id else None
    if asset is None:
        raise AppError("AI_TASK1_IMAGE_MISSING", "Task 1 cần có hình đã lưu để chấm AI.", 422)
    if asset.test_version_id != version_id or asset.asset_type != AssetType.WRITING_TASK_IMAGE:
        raise AppError("AI_TASK1_IMAGE_INVALID", "Hình không thuộc phiên bản Task 1 đã làm.", 422)
    maximum = min(settings.max_image_upload_mb, 10) * 1024 * 1024
    if asset.mime_type not in LocalAssetStorage.IMAGE_TYPES or not 0 < asset.file_size <= maximum:
        raise AppError(
            "AI_TASK1_IMAGE_INVALID", "Định dạng hoặc kích thước hình không hợp lệ.", 422
        )

    def read() -> ImagePart:
        try:
            path = LocalAssetStorage(settings.resolved_storage_root).resolve(asset.relative_path)
            with path.open("rb") as source:
                content = source.read(maximum + 1)
            if len(content) != asset.file_size:
                raise ValueError("Image size mismatch")
            return ImagePart(mime_type=asset.mime_type, data=content)
        except (OSError, ValueError, AppError):
            raise AppError(
                "AI_TASK1_IMAGE_INVALID", "Không thể đọc hình Task 1 hợp lệ đã lưu.", 422
            ) from None

    return await asyncio.to_thread(read)
