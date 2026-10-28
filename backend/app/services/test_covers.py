"""Logical-test covers, separate from immutable version assets."""

import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models import Test, TestCover, TestVersion, User
from app.models.enums import UserRole, VersionStatus
from app.schemas.tests import TestCoverSummary
from app.services.access_policy import AccessPolicy
from app.services.asset_cleanup import compensate_files
from app.services.cover_validation import validate_cover_image
from app.storage import LocalAssetStorage
from app.storage.local import StoredAsset


class TestCoverService:
    def __init__(self, session: AsyncSession, actor: User, settings: Settings):
        self.session = session
        self.policy = AccessPolicy(session, actor)
        self.settings = settings
        self.storage = LocalAssetStorage(settings.resolved_storage_root)

    async def _require_edit(self, test_id, *, lock=False):
        statement = select(Test).where(Test.id == test_id)
        if lock:
            statement = statement.execution_options(populate_existing=True).with_for_update()
        test = await self.session.scalar(statement)
        if test is None:
            raise AppError("TEST_NOT_FOUND", "The requested test does not exist.", 404)
        await self.policy.require_test_edit(test)
        await self.policy.require_no_pending_test(test.id)
        if test.archived_at is not None:
            raise AppError("TEST_ARCHIVED", "Restore this test before editing it.", 409)
        if self.policy.actor.role == UserRole.TEACHER:
            draft = await self.session.scalar(
                select(TestVersion).where(
                    TestVersion.test_id == test.id, TestVersion.status == VersionStatus.DRAFT
                )
            )
            if draft is None:
                raise AppError(
                    "TEST_VERSION_IMMUTABLE", "Create a draft before editing this test.", 409
                )
            await self.policy.require_version_mutable(draft)
        return test

    async def upload(self, test_id, upload) -> TestCoverSummary:
        async with self.session.begin():
            await self._require_edit(test_id)
        original_name = Path((upload.filename or "upload").replace("\\", "/")).name[:255]
        mime = upload.content_type or "application/octet-stream"
        task = asyncio.create_task(
            asyncio.to_thread(
                self.storage.store_stream,
                category="images",
                mime_type=mime,
                original_name=original_name,
                source=upload.file,
                max_bytes=min(self.settings.max_image_upload_mb, 10) * 1024 * 1024,
            )
        )
        stored = None
        old_path = None
        try:
            stored = await asyncio.shield(task)

            def validate_stored():
                validate_cover_image(mime, self.storage.resolve(stored.relative_path).read_bytes())

            validation = asyncio.create_task(asyncio.to_thread(validate_stored))
            try:
                await asyncio.shield(validation)
            except BaseException as error:
                await asyncio.gather(validation, return_exceptions=True)
                if isinstance(error, ValueError):
                    raise AppError(
                        "ASSET_UPLOAD_INVALID",
                        "The uploaded image is invalid or its dimensions are too large.",
                        422,
                    ) from None
                raise
            async with self.session.begin():
                await self.policy.lock_actor()
                await self._require_edit(test_id, lock=True)
                previous = await self.session.scalar(
                    select(TestCover).where(TestCover.test_id == test_id)
                )
                if previous is not None:
                    old_path = previous.relative_path
                    await self.session.delete(previous)
                    await self.session.flush()
                cover = TestCover(
                    test_id=test_id,
                    relative_path=stored.relative_path,
                    mime_type=mime,
                    original_name=original_name,
                    file_size=stored.size,
                )
                self.session.add(cover)
                await self.session.flush()
                response = TestCoverSummary.model_validate(cover)
        except BaseException:
            if stored is None:
                result = (await asyncio.gather(task, return_exceptions=True))[0]
                if isinstance(result, StoredAsset):
                    stored = result
            paths = ([stored.relative_path] if stored is not None else []) + (
                [old_path] if old_path else []
            )
            await compensate_files(self.session, self.storage, paths)
            raise
        if old_path:
            await compensate_files(self.session, self.storage, [old_path])
        return response

    async def remove(self, test_id):
        old_path = None
        async with self.session.begin():
            await self.policy.lock_actor()
            await self._require_edit(test_id, lock=True)
            cover = await self.session.scalar(select(TestCover).where(TestCover.test_id == test_id))
            if cover is not None:
                old_path = cover.relative_path
                await self.session.delete(cover)
        if old_path:
            await compensate_files(self.session, self.storage, [old_path])

    async def read(self, test_id, cover_id):
        test = await self.session.scalar(
            select(Test).where(Test.id == test_id).options(selectinload(Test.versions))
        )
        if test is None or test.cover_image is None or test.cover_image.id != cover_id:
            raise AppError("ASSET_NOT_FOUND", "The asset does not exist.", 404)
        actor = self.policy.actor
        if actor.role != UserRole.ADMIN and not (
            actor.role == UserRole.TEACHER and test.owner_user_id == actor.id
        ):
            if not await self.policy.public_version_ids([test]):
                raise AppError("ASSET_NOT_FOUND", "The asset does not exist.", 404)
        return test.cover_image
