"""Read authorization for assets referenced by immutable historical content."""

from uuid import UUID

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, Attempt, QuestionGroup, TestModule, TestVersion, WritingTask
from app.models.enums import ModuleType, VersionStatus


async def can_user_read_asset(session: AsyncSession, user_id: UUID, asset: Asset) -> bool:
    """Allow current published assets or an owned archived module's referenced asset."""
    version_status = await session.scalar(
        select(TestVersion.status).where(TestVersion.id == asset.test_version_id)
    )
    if version_status == VersionStatus.PUBLISHED:
        return True
    if version_status != VersionStatus.ARCHIVED:
        return False

    owned_module = and_(
        Attempt.user_id == user_id,
        Attempt.test_version_id == asset.test_version_id,
        Attempt.test_version_id == TestModule.test_version_id,
        # These columns use distinct PostgreSQL enum types.
        cast(Attempt.module_type, String) == cast(TestModule.module_type, String),
    )
    listening_audio = (
        select(1)
        .select_from(TestModule)
        .join(Attempt, owned_module)
        .where(
            TestModule.test_version_id == asset.test_version_id,
            TestModule.module_type == ModuleType.LISTENING,
            TestModule.audio_asset_id == asset.id,
        )
        .exists()
    )
    question_image = (
        select(1)
        .select_from(QuestionGroup)
        .join(TestModule, QuestionGroup.module_id == TestModule.id)
        .join(Attempt, owned_module)
        .where(
            TestModule.test_version_id == asset.test_version_id,
            QuestionGroup.image_asset_id == asset.id,
        )
        .exists()
    )
    writing_image = (
        select(1)
        .select_from(WritingTask)
        .join(TestModule, WritingTask.module_id == TestModule.id)
        .join(Attempt, owned_module)
        .where(
            TestModule.test_version_id == asset.test_version_id,
            TestModule.module_type == ModuleType.WRITING,
            WritingTask.image_asset_id == asset.id,
        )
        .exists()
    )
    return bool(await session.scalar(select(or_(listening_audio, question_image, writing_image))))
