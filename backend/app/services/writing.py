import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models import Asset, TestModule, WritingTask
from app.models.enums import AssetType, ModuleType
from app.schemas.content import BuilderWritingTask, WritingTaskUpdate
from app.services.draft_revisions import advance_revision
from app.services.reading import ReadingService
from app.storage import LocalAssetStorage


class WritingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def update_task(self, task_id: uuid.UUID, body: WritingTaskUpdate) -> BuilderWritingTask:
        deleted_path: str | None = None
        copied_path: str | None = None
        try:
            async with self.session.begin():
                version_id = await self.session.scalar(
                    select(TestModule.test_version_id)
                    .join(WritingTask, WritingTask.module_id == TestModule.id)
                    .where(
                        WritingTask.id == task_id,
                        TestModule.module_type == ModuleType.WRITING,
                    )
                )
                if version_id is None:
                    raise AppError(
                        "WRITING_TASK_NOT_FOUND", "The Writing task does not exist.", 404
                    )
                from app.services.tests import TestService

                await TestService(self.session).ensure_draft(version_id)
                task = await self.session.scalar(
                    self._task_query().where(WritingTask.id == task_id).with_for_update()
                )
                if (
                    task is None
                    or task.module.module_type != ModuleType.WRITING
                    or task.module.test_version_id != version_id
                ):
                    raise AppError(
                        "WRITING_TASK_NOT_FOUND", "The Writing task does not exist.", 404
                    )
                advance_revision(task, body.expected_revision)
                if task.task_number == 2 and body.image_asset_id is not None:
                    raise AppError(
                        "WRITING_TASK_IMAGE_NOT_ALLOWED",
                        "Writing Task 2 cannot have an image attachment.",
                        422,
                    )
                asset: Asset | None = None
                if body.image_asset_id is not None:
                    from app.services.tests import TestService

                    repaired, copied_path = await TestService(
                        self.session
                    ).resolve_owned_or_inherited_asset(
                        target_version=task.module.test_version,
                        requested_asset_id=body.image_asset_id,
                        current_asset_id=task.image_asset_id,
                        asset_type=AssetType.WRITING_TASK_IMAGE,
                    )
                    asset = (
                        repaired
                        if (
                            repaired is not None
                            and repaired.mime_type in LocalAssetStorage.IMAGE_TYPES
                        )
                        else await self.session.scalar(
                            select(Asset).where(
                                Asset.id == body.image_asset_id,
                                Asset.test_version_id == task.module.test_version_id,
                                Asset.asset_type == AssetType.WRITING_TASK_IMAGE,
                                Asset.mime_type.in_(LocalAssetStorage.IMAGE_TYPES),
                            )
                        )
                    )
                    if asset is None:
                        raise AppError(
                            "INVALID_WRITING_TASK_IMAGE",
                            "The Writing image is invalid or does not belong to this draft version.",
                            422,
                        )
                previous_asset_id = task.image_asset_id
                task.prompt = body.prompt.strip()
                task.image_asset = asset
                task.minimum_recommended_words = body.minimum_recommended_words
                task.recommended_duration_seconds = body.recommended_duration_seconds
                await self.session.flush()
                if previous_asset_id is not None and previous_asset_id != task.image_asset_id:
                    from app.services.tests import TestService

                    deleted_path = await TestService(self.session).cleanup_asset_if_unreferenced(
                        previous_asset_id
                    )
                saved = await self.get_task(task_id)
        except BaseException:
            if copied_path:
                from app.services.tests import TestService

                TestService._delete_files([copied_path])
            raise
        if deleted_path:
            from app.services.tests import TestService

            TestService._delete_files([deleted_path])
        return saved

    async def get_task(self, task_id: uuid.UUID) -> BuilderWritingTask:
        task = await self.session.scalar(self._task_query().where(WritingTask.id == task_id))
        if task is None or task.module.module_type != ModuleType.WRITING:
            raise AppError("WRITING_TASK_NOT_FOUND", "The Writing task does not exist.", 404)
        return ReadingService._present_writing_task(task)

    @staticmethod
    def _task_query():
        return select(WritingTask).options(
            selectinload(WritingTask.image_asset),
            selectinload(WritingTask.module).selectinload(TestModule.test_version),
        )
