import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.domains.questions import question_registry
from app.domains.questions.normalization import (
    normalize_passage_blocks,
    normalize_question_group_payload,
    remap_question_references,
)
from app.domains.questions.numbering import group_slots
from app.models import (
    Asset,
    Attempt,
    ListeningPart,
    Question,
    QuestionGroup,
    ReadingPassage,
    Test,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.models.enums import AssetType, ModuleType, VersionStatus
from app.repositories.tests import TestRepository, version_detail_query
from app.schemas.common import ValidationIssue, ValidationResult
from app.schemas.content import TextBlock
from app.schemas.tests import TestCreate, TestDeleteResult, TestUpdate, VersionCreate
from app.storage import LocalAssetStorage


class TestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = TestRepository(session)

    async def list_tests(self, *, archived: bool = False) -> list[Test]:
        return await self.repository.list(archived=archived)

    async def get_test(self, test_id: uuid.UUID) -> Test:
        test = await self.repository.get(test_id)
        if test is None:
            raise AppError("TEST_NOT_FOUND", "The requested test does not exist.", 404)
        return test

    async def create_test(self, data: TestCreate) -> Test:
        async with self.session.begin():
            test = Test(
                title=data.title.strip(),
                description=data.description,
                source_label=data.source_label,
                test_number=data.test_number,
            )
            self.session.add(test)
            if data.create_initial_draft:
                test.versions.append(TestVersion(version_number=1, status=VersionStatus.DRAFT))
            await self.session.flush()
        return test

    async def update_test(self, test_id: uuid.UUID, data: TestUpdate) -> Test:
        async with self.session.begin():
            test = await self.session.scalar(
                select(Test).where(Test.id == test_id).with_for_update()
            )
            if test is None:
                raise AppError("TEST_NOT_FOUND", "The requested test does not exist.", 404)
            test.title = data.title
            await self.session.flush()
            await self.session.refresh(test, attribute_names=["updated_at"])
        return await self.get_test(test_id)

    async def delete_test(self, test_id: uuid.UUID) -> TestDeleteResult:
        deleted_paths: list[str] = []
        async with self.session.begin():
            test = await self.session.scalar(
                select(Test).where(Test.id == test_id).with_for_update()
            )
            if test is None:
                raise AppError("TEST_NOT_FOUND", "The requested test does not exist.", 404)
            if test.archived_at is not None:
                raise AppError(
                    "TEST_ALREADY_ARCHIVED", "The requested test is already archived.", 409
                )
            version_rows = list(
                (
                    await self.session.execute(
                        select(TestVersion.id, TestVersion.status).where(
                            TestVersion.test_id == test_id
                        )
                    )
                ).all()
            )
            has_history = any(
                status in {VersionStatus.PUBLISHED, VersionStatus.ARCHIVED}
                for _, status in version_rows
            )
            has_attempts = (
                await self.session.scalar(
                    select(Attempt.id)
                    .join(TestVersion, Attempt.test_version_id == TestVersion.id)
                    .where(TestVersion.test_id == test_id)
                    .limit(1)
                )
                is not None
            )
            if has_history or has_attempts:
                test.archived_at = datetime.now(UTC)
                await self.session.flush()
                return TestDeleteResult(test_id=test_id, action="ARCHIVED")
            deleted_version_ids = {version_id for version_id, _ in version_rows}
            for version_id in deleted_version_ids:
                await self._preserve_shared_assets(
                    version_id, excluded_version_ids=deleted_version_ids
                )
            deleted_paths = list(
                await self.session.scalars(
                    select(Asset.relative_path).where(
                        Asset.test_version_id.in_(deleted_version_ids)
                    )
                )
            )
            await self.session.delete(test)
            await self.session.flush()
        self._delete_files(deleted_paths)
        return TestDeleteResult(test_id=test_id, action="DELETED")

    async def permanently_delete_test(self, test_id: uuid.UUID) -> None:
        deleted_paths: list[str] = []
        async with self.session.begin():
            test = await self.session.scalar(
                select(Test).where(Test.id == test_id).with_for_update()
            )
            if test is None:
                raise AppError("TEST_NOT_FOUND", "The requested test does not exist.", 404)
            if test.archived_at is None:
                raise AppError(
                    "TEST_NOT_ARCHIVED",
                    "Archive this test before deleting it permanently.",
                    409,
                )
            version_ids = set(
                await self.session.scalars(
                    select(TestVersion.id).where(TestVersion.test_id == test_id)
                )
            )
            if version_ids:
                await self.session.execute(
                    delete(Attempt).where(Attempt.test_version_id.in_(version_ids))
                )
                for version_id in version_ids:
                    await self._preserve_shared_assets(version_id, excluded_version_ids=version_ids)
                deleted_paths = list(
                    await self.session.scalars(
                        select(Asset.relative_path).where(Asset.test_version_id.in_(version_ids))
                    )
                )
            await self.session.delete(test)
            await self.session.flush()
        self._delete_files(deleted_paths)

    async def delete_module(self, module_id: uuid.UUID) -> None:
        deleted_paths: list[str] = []
        async with self.session.begin():
            version_id = await self.session.scalar(
                select(TestModule.test_version_id).where(TestModule.id == module_id)
            )
            if version_id is None:
                raise AppError("TEST_MODULE_NOT_FOUND", "The test module does not exist.", 404)
            await self.ensure_draft(version_id)
            module = await self.session.scalar(
                select(TestModule)
                .where(TestModule.id == module_id)
                .options(
                    selectinload(TestModule.test_version),
                    selectinload(TestModule.question_groups),
                    selectinload(TestModule.writing_tasks),
                )
                .with_for_update()
            )
            if module is None or module.test_version_id != version_id:
                raise AppError("TEST_MODULE_NOT_FOUND", "The test module does not exist.", 404)
            asset_ids = {
                asset_id
                for asset_id in [
                    module.audio_asset_id,
                    *(group.image_asset_id for group in module.question_groups),
                    *(task.image_asset_id for task in module.writing_tasks),
                ]
                if asset_id is not None
            }
            await self.session.delete(module)
            await self.session.flush()
            for asset_id in asset_ids:
                path = await self.cleanup_asset_if_unreferenced(asset_id)
                if path:
                    deleted_paths.append(path)
        self._delete_files(deleted_paths)

    async def cleanup_asset_if_unreferenced(self, asset_id: uuid.UUID) -> str | None:
        referenced = any(
            item is not None
            for item in [
                await self.session.scalar(
                    select(TestModule.id).where(TestModule.audio_asset_id == asset_id).limit(1)
                ),
                await self.session.scalar(
                    select(QuestionGroup.id)
                    .where(QuestionGroup.image_asset_id == asset_id)
                    .limit(1)
                ),
                await self.session.scalar(
                    select(WritingTask.id).where(WritingTask.image_asset_id == asset_id).limit(1)
                ),
            ]
        )
        if referenced:
            return None
        asset = await self.session.scalar(
            select(Asset).where(Asset.id == asset_id).with_for_update()
        )
        if asset is None:
            return None
        path = asset.relative_path
        await self.session.delete(asset)
        await self.session.flush()
        return path

    async def resolve_owned_or_inherited_asset(
        self,
        *,
        target_version: TestVersion,
        requested_asset_id: uuid.UUID,
        current_asset_id: uuid.UUID | None,
        asset_type: AssetType,
    ) -> tuple[Asset | None, str | None]:
        owned = await self.session.scalar(
            select(Asset).where(
                Asset.id == requested_asset_id,
                Asset.test_version_id == target_version.id,
                Asset.asset_type == asset_type,
            )
        )
        if owned is not None:
            return owned, None
        if requested_asset_id != current_asset_id:
            return None, None

        inherited = await self.session.scalar(
            select(Asset)
            .join(TestVersion, Asset.test_version_id == TestVersion.id)
            .where(
                Asset.id == requested_asset_id,
                Asset.asset_type == asset_type,
                TestVersion.test_id == target_version.test_id,
                TestVersion.version_number < target_version.version_number,
                TestVersion.status.in_({VersionStatus.PUBLISHED, VersionStatus.ARCHIVED}),
            )
        )
        if inherited is None:
            return None, None

        if asset_type == AssetType.LISTENING_AUDIO:
            inherited_reference = await self.session.scalar(
                select(TestModule.id)
                .where(
                    TestModule.test_version_id == inherited.test_version_id,
                    TestModule.audio_asset_id == inherited.id,
                )
                .limit(1)
            )
        elif asset_type == AssetType.QUESTION_IMAGE:
            inherited_reference = await self.session.scalar(
                select(QuestionGroup.id)
                .join(TestModule, QuestionGroup.module_id == TestModule.id)
                .where(
                    TestModule.test_version_id == inherited.test_version_id,
                    QuestionGroup.image_asset_id == inherited.id,
                )
                .limit(1)
            )
        else:
            inherited_reference = await self.session.scalar(
                select(WritingTask.id)
                .join(TestModule, WritingTask.module_id == TestModule.id)
                .where(
                    TestModule.test_version_id == inherited.test_version_id,
                    WritingTask.image_asset_id == inherited.id,
                )
                .limit(1)
            )
        if inherited_reference is None:
            return None, None

        settings = get_settings()
        storage = LocalAssetStorage(settings.resolved_storage_root)
        is_audio = asset_type == AssetType.LISTENING_AUDIO
        stored = storage.store_file(
            category="audio" if is_audio else "images",
            mime_type=inherited.mime_type,
            original_name=inherited.original_name,
            source=storage.resolve(inherited.relative_path),
            max_bytes=(settings.max_audio_upload_mb if is_audio else settings.max_image_upload_mb)
            * 1024
            * 1024,
        )
        try:
            copy = Asset(
                id=uuid.uuid4(),
                test_version_id=target_version.id,
                asset_type=inherited.asset_type,
                relative_path=stored.relative_path,
                mime_type=inherited.mime_type,
                original_name=inherited.original_name,
                file_size=stored.size,
                created_at=datetime.now(UTC),
            )
            self.session.add(copy)
            await self.session.flush()
        except BaseException:
            storage.delete(stored.relative_path)
            raise
        return copy, stored.relative_path

    @staticmethod
    def _delete_files(paths: list[str]) -> None:
        storage = LocalAssetStorage(get_settings().resolved_storage_root)
        for path in paths:
            storage.delete(path)

    async def restore_test(self, test_id: uuid.UUID) -> Test:
        async with self.session.begin():
            test = await self.session.scalar(
                select(Test)
                .where(Test.id == test_id)
                .options(selectinload(Test.versions))
                .with_for_update()
            )
            if test is None:
                raise AppError("TEST_NOT_FOUND", "The requested test does not exist.", 404)
            if test.archived_at is None:
                raise AppError("TEST_NOT_ARCHIVED", "Only archived tests can be restored.", 409)
            test.archived_at = None
            await self.session.flush()
            await self.session.refresh(test, attribute_names=["updated_at"])
        return test

    async def delete_draft(self, test_id: uuid.UUID, version_id: uuid.UUID) -> None:
        deleted_paths: list[str] = []
        async with self.session.begin():
            test = await self.session.scalar(
                select(Test).where(Test.id == test_id).with_for_update()
            )
            if test is None:
                raise AppError("TEST_NOT_FOUND", "The requested test does not exist.", 404)
            version = await self.session.scalar(
                select(TestVersion)
                .where(TestVersion.id == version_id, TestVersion.test_id == test_id)
                .with_for_update()
            )
            if version is None:
                raise AppError(
                    "VERSION_NOT_FOUND",
                    "The requested draft version does not belong to this test.",
                    404,
                )
            if version.status != VersionStatus.DRAFT:
                raise AppError("VERSION_NOT_DRAFT", "Only draft versions can be deleted.", 409)
            attempt_id = await self.session.scalar(
                select(Attempt.id).where(Attempt.test_version_id == version_id).limit(1)
            )
            if attempt_id is not None:
                raise AppError(
                    "DELETE_CONFLICT",
                    "This draft has attempt history and cannot be deleted.",
                    409,
                )
            await self._preserve_shared_assets(version_id, excluded_version_ids={version_id})
            deleted_paths = list(
                await self.session.scalars(
                    select(Asset.relative_path).where(Asset.test_version_id == version_id)
                )
            )
            await self.session.delete(version)
            await self.session.flush()
            remaining_version_id = await self.session.scalar(
                select(TestVersion.id)
                .where(TestVersion.test_id == test_id, TestVersion.id != version_id)
                .limit(1)
            )
            if remaining_version_id is None:
                await self.session.execute(delete(Test).where(Test.id == test_id))
                await self.session.flush()
        self._delete_files(deleted_paths)

    async def _preserve_shared_assets(
        self,
        version_id: uuid.UUID,
        *,
        excluded_version_ids: set[uuid.UUID],
    ) -> None:
        assets = list(
            await self.session.scalars(
                select(Asset).where(Asset.test_version_id == version_id).with_for_update()
            )
        )
        for asset in assets:
            replacement_version_id = await self.session.scalar(
                select(TestModule.test_version_id)
                .where(
                    TestModule.audio_asset_id == asset.id,
                    TestModule.test_version_id.not_in(excluded_version_ids),
                )
                .limit(1)
            )
            if replacement_version_id is None:
                replacement_version_id = await self.session.scalar(
                    select(TestModule.test_version_id)
                    .join(WritingTask, WritingTask.module_id == TestModule.id)
                    .where(
                        WritingTask.image_asset_id == asset.id,
                        TestModule.test_version_id.not_in(excluded_version_ids),
                    )
                    .limit(1)
                )
            if replacement_version_id is None:
                replacement_version_id = await self.session.scalar(
                    select(TestModule.test_version_id)
                    .join(QuestionGroup, QuestionGroup.module_id == TestModule.id)
                    .where(
                        QuestionGroup.image_asset_id == asset.id,
                        TestModule.test_version_id.not_in(excluded_version_ids),
                    )
                    .limit(1)
                )
            if replacement_version_id is not None:
                asset.test_version_id = replacement_version_id
        await self.session.flush()

    async def get_version(self, version_id: uuid.UUID) -> TestVersion:
        version = await self.repository.get_version(version_id)
        if version is None:
            raise AppError(
                "TEST_VERSION_NOT_FOUND", "The requested test version does not exist.", 404
            )
        return version

    async def create_version(self, test_id: uuid.UUID, data: VersionCreate) -> TestVersion:
        created_paths: list[str] = []
        try:
            async with self.session.begin():
                test = await self.session.scalar(
                    select(Test).where(Test.id == test_id).with_for_update()
                )
                if test is None:
                    raise AppError("TEST_NOT_FOUND", "The requested test does not exist.", 404)
                if test.archived_at is not None:
                    raise AppError("TEST_ARCHIVED", "Restore this test before editing it.", 409)
                existing_draft_id = await self.session.scalar(
                    select(TestVersion.id).where(
                        TestVersion.test_id == test_id,
                        TestVersion.status == VersionStatus.DRAFT,
                    )
                )
                if existing_draft_id is not None:
                    version_id = existing_draft_id
                else:
                    number = await self.repository.next_version_number(test_id)
                    version = TestVersion(
                        test_id=test_id,
                        version_number=number,
                        status=VersionStatus.DRAFT,
                        modules=[],
                        assets=[],
                    )
                    self.session.add(version)
                    if data.source_version_id is not None:
                        source = await self.repository.get_version(data.source_version_id)
                        if source is None or source.test_id != test_id:
                            raise AppError(
                                "TEST_VERSION_NOT_FOUND",
                                "The source version does not belong to this test.",
                                404,
                            )
                        asset_map = self._clone_referenced_assets(source, version, created_paths)
                        self._clone_content(source, version, asset_map)
                    await self.session.flush()
                    version_id = version.id
        except BaseException:
            self._delete_files(created_paths)
            raise
        return await self.get_version(version_id)

    @staticmethod
    def _clone_referenced_assets(
        source: TestVersion,
        target: TestVersion,
        created_paths: list[str],
    ) -> dict[uuid.UUID, Asset]:
        referenced: dict[uuid.UUID, Asset] = {}
        for module in source.modules:
            if module.audio_asset is not None:
                referenced[module.audio_asset.id] = module.audio_asset
            for task in module.writing_tasks:
                if task.image_asset is not None:
                    referenced[task.image_asset.id] = task.image_asset
            for group in module.question_groups:
                if group.image_asset is not None:
                    referenced[group.image_asset.id] = group.image_asset

        settings = get_settings()
        storage = LocalAssetStorage(settings.resolved_storage_root)
        cloned: dict[uuid.UUID, Asset] = {}
        for asset_id, asset in referenced.items():
            is_audio = asset.asset_type == AssetType.LISTENING_AUDIO
            stored = storage.store_file(
                category="audio" if is_audio else "images",
                mime_type=asset.mime_type,
                original_name=asset.original_name,
                source=storage.resolve(asset.relative_path),
                max_bytes=(
                    settings.max_audio_upload_mb if is_audio else settings.max_image_upload_mb
                )
                * 1024
                * 1024,
            )
            created_paths.append(stored.relative_path)
            copy = Asset(
                id=uuid.uuid4(),
                asset_type=asset.asset_type,
                relative_path=stored.relative_path,
                mime_type=asset.mime_type,
                original_name=asset.original_name,
                file_size=stored.size,
                created_at=datetime.now(UTC),
            )
            target.assets.append(copy)
            cloned[asset_id] = copy
        return cloned

    @staticmethod
    def _clone_content(
        source: TestVersion,
        target: TestVersion,
        asset_map: dict[uuid.UUID, Asset] | None = None,
    ) -> None:
        asset_map = asset_map or {}
        for module in source.modules:
            new_module = TestModule(
                module_type=module.module_type,
                title=module.title,
                recommended_duration_seconds=module.recommended_duration_seconds,
                order_index=module.order_index,
                audio_asset=asset_map.get(module.audio_asset_id),
            )
            target.modules.append(new_module)
            passage_map: dict[uuid.UUID, ReadingPassage] = {}
            part_map: dict[uuid.UUID, ListeningPart] = {}
            for passage in module.passages:
                cloned_passage = ReadingPassage(
                    title=passage.title,
                    order_index=passage.order_index,
                    content_json=passage.content_json,
                    plain_text=passage.plain_text,
                )
                new_module.passages.append(cloned_passage)
                passage_map[passage.id] = cloned_passage
            for part in module.listening_parts:
                cloned_part = ListeningPart(
                    title=part.title,
                    order_index=part.order_index,
                )
                new_module.listening_parts.append(cloned_part)
                part_map[part.id] = cloned_part
            for task in module.writing_tasks:
                new_module.writing_tasks.append(
                    WritingTask(
                        task_number=task.task_number,
                        prompt=task.prompt,
                        image_asset=asset_map.get(task.image_asset_id),
                        minimum_recommended_words=task.minimum_recommended_words,
                        recommended_duration_seconds=task.recommended_duration_seconds,
                        order_index=task.order_index,
                    )
                )
            for group in module.question_groups:
                question_ids = {str(question.id): str(uuid.uuid4()) for question in group.questions}
                new_group = QuestionGroup(
                    passage=passage_map.get(group.passage_id),
                    listening_part=part_map.get(group.listening_part_id),
                    image_asset=asset_map.get(group.image_asset_id),
                    section_reference=group.section_reference,
                    question_type=group.question_type,
                    instruction=group.instruction,
                    config=remap_question_references(group.config, question_ids),
                    order_index=group.order_index,
                )
                new_module.question_groups.append(new_group)
                for question in group.questions:
                    new_group.questions.append(
                        Question(
                            id=uuid.UUID(question_ids[str(question.id)]),
                            number=question.number,
                            prompt=question.prompt,
                            config=question.config,
                            answer_key=question.answer_key,
                            explanation=question.explanation,
                            order_index=question.order_index,
                        )
                    )

    @staticmethod
    def validate_version(version: TestVersion) -> ValidationResult:
        issues: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        usable_modules = 0
        if not version.modules:
            issues.append(ValidationIssue(path="modules", message="Add at least one module."))
        for module in version.modules:
            prefix = module.module_type.value.lower()
            normalized_passages: dict[uuid.UUID, list[dict]] = {}
            if module.module_type == ModuleType.READING:
                ordered_groups = [
                    group
                    for passage in sorted(module.passages, key=lambda item: item.order_index)
                    for group in sorted(passage.question_groups, key=lambda item: item.order_index)
                ]
            elif module.module_type == ModuleType.LISTENING:
                ordered_groups = [
                    group
                    for part in sorted(module.listening_parts, key=lambda item: item.order_index)
                    for group in sorted(part.question_groups, key=lambda item: item.order_index)
                ]
                if len(module.listening_parts) != 4:
                    warnings.append(
                        ValidationIssue(
                            path="listening.parts",
                            message=f"IELTS readiness: Listening contains {len(module.listening_parts)} / 4 sections.",
                        )
                    )
                if sorted(part.order_index for part in module.listening_parts) != list(
                    range(len(module.listening_parts))
                ):
                    issues.append(
                        ValidationIssue(
                            path="listening.parts",
                            message="Listening sections must use a canonical contiguous order.",
                        )
                    )
            else:
                ordered_groups = sorted(module.question_groups, key=lambda item: item.order_index)
            question_numbers = [
                number
                for group in ordered_groups
                for number in group_slots(
                    group.question_type,
                    sorted(group.questions, key=lambda item: item.order_index),
                )
            ]
            duplicate_numbers = sorted(
                number for number in set(question_numbers) if question_numbers.count(number) > 1
            )
            if duplicate_numbers:
                issues.append(
                    ValidationIssue(
                        path=f"{prefix}.questions",
                        message=(
                            "Question numbers must be unique across the module; duplicates: "
                            + ", ".join(map(str, duplicate_numbers))
                        ),
                    )
                )
            expected_numbers = list(range(1, len(question_numbers) + 1))
            if question_numbers != expected_numbers:
                issues.append(
                    ValidationIssue(
                        path=f"{prefix}.questions",
                        message="Question numbers must form the canonical sequence 1 through N.",
                    )
                )
            if (
                module.module_type in {ModuleType.READING, ModuleType.LISTENING}
                and len(question_numbers) != 40
            ):
                warnings.append(
                    ValidationIssue(
                        path=f"{prefix}.questions",
                        message=f"IELTS readiness: {module.module_type.value.title()} contains {len(question_numbers)} / 40 questions.",
                    )
                )
            is_nonempty = {
                ModuleType.READING: bool(module.passages),
                ModuleType.LISTENING: bool(module.listening_parts),
                ModuleType.WRITING: bool(module.writing_tasks),
            }[module.module_type]
            if not is_nonempty:
                warnings.append(
                    ValidationIssue(path=prefix, message=f"The {prefix} module has no content yet.")
                )
            if module.module_type == ModuleType.LISTENING and module.audio_asset_id is None:
                warnings.append(
                    ValidationIssue(
                        path="listening.audio",
                        message="IELTS readiness: Listening has no audio attached.",
                    )
                )
            elif module.module_type == ModuleType.LISTENING and (
                module.audio_asset is None
                or module.audio_asset.asset_type != AssetType.LISTENING_AUDIO
                or module.audio_asset.test_version_id != module.test_version_id
            ):
                issues.append(
                    ValidationIssue(
                        path="listening.audio",
                        message="Listening audio must belong to this test version.",
                    )
                )
            if module.module_type == ModuleType.WRITING:
                task_numbers = [task.task_number for task in module.writing_tasks]
                task_orders = [task.order_index for task in module.writing_tasks]
                if len(module.writing_tasks) != 2:
                    warnings.append(
                        ValidationIssue(
                            path="writing.tasks",
                            message=(
                                "IELTS readiness: Writing contains "
                                f"{len(module.writing_tasks)} / 2 tasks."
                            ),
                        )
                    )
                if len(task_numbers) != len(set(task_numbers)):
                    issues.append(
                        ValidationIssue(
                            path="writing.tasks",
                            message="Writing task numbers must be unique.",
                        )
                    )
                if len(task_orders) != len(set(task_orders)):
                    issues.append(
                        ValidationIssue(
                            path="writing.tasks",
                            message="Writing task order indexes must be unique.",
                        )
                    )
                expected_settings = {
                    (1, 0): (150, 1200),
                    (2, 1): (250, 2400),
                }
                for task in module.writing_tasks:
                    task_path = f"writing.tasks.{task.task_number}"
                    identity = (task.task_number, task.order_index)
                    if identity not in expected_settings:
                        issues.append(
                            ValidationIssue(
                                path=task_path,
                                message=(
                                    "Writing tasks must use fixed identities: "
                                    "Task 1 at order 0 and Task 2 at order 1."
                                ),
                            )
                        )
                    if task.module is not module and task.module_id != module.id:
                        issues.append(
                            ValidationIssue(
                                path=task_path,
                                message="The Writing task must belong to its containing module.",
                            )
                        )
                    has_image = task.image_asset_id is not None or task.image_asset is not None
                    if task.task_number == 2 and has_image:
                        issues.append(
                            ValidationIssue(
                                path=f"{task_path}.image",
                                message="Writing Task 2 cannot have an image attachment.",
                            )
                        )
                    elif task.task_number == 1 and has_image:
                        if (
                            task.image_asset is None
                            or task.image_asset.asset_type != AssetType.WRITING_TASK_IMAGE
                            or task.image_asset.mime_type not in LocalAssetStorage.IMAGE_TYPES
                            or task.image_asset.test_version_id != module.test_version_id
                        ):
                            issues.append(
                                ValidationIssue(
                                    path=f"{task_path}.image",
                                    message="Writing Task 1 has an invalid image attachment.",
                                )
                            )
                    if not task.prompt.strip():
                        warnings.append(
                            ValidationIssue(
                                path=f"{task_path}.prompt",
                                message=f"Writing Task {task.task_number} has no prompt yet.",
                            )
                        )
                    expected = expected_settings.get(identity)
                    if expected and (
                        task.minimum_recommended_words != expected[0]
                        or task.recommended_duration_seconds != expected[1]
                    ):
                        warnings.append(
                            ValidationIssue(
                                path=f"{task_path}.recommendations",
                                message=(
                                    f"IELTS readiness: Writing Task {task.task_number} uses "
                                    "nonstandard word or time guidance."
                                ),
                            )
                        )
            for passage in module.passages:
                try:
                    raw_blocks = normalize_passage_blocks(passage.content_json, passage.id)
                    normalized_blocks = [
                        TextBlock.model_validate(block).model_dump(mode="json")
                        for block in raw_blocks
                    ]
                except (AttributeError, KeyError, TypeError, ValidationError, ValueError) as exc:
                    issues.append(
                        ValidationIssue(
                            path=f"{prefix}.passages.{passage.id}.blocks",
                            message=f"Invalid passage block configuration: {exc}",
                        )
                    )
                    normalized_passages[passage.id] = []
                    continue
                normalized_passages[passage.id] = normalized_blocks
                block_ids = [block["id"] for block in normalized_blocks]
                if len(block_ids) != len(set(block_ids)):
                    issues.append(
                        ValidationIssue(
                            path=f"{prefix}.passages.{passage.id}.blocks",
                            message="Passage block IDs must be unique.",
                        )
                    )
                paragraph_labels = [
                    str(block.get("label", "")).casefold()
                    for block in normalized_blocks
                    if block.get("type") == "paragraph" and block.get("label")
                ]
                if len(paragraph_labels) != len(set(paragraph_labels)):
                    issues.append(
                        ValidationIssue(
                            path=f"{prefix}.passages.{passage.id}.blocks",
                            message="Paragraph labels must be unique.",
                        )
                    )
            available_passage_ids = {passage.id for passage in module.passages if passage.id}
            available_part_ids = {part.id for part in module.listening_parts if part.id}
            for group in module.question_groups:
                reading_relationship_matches = any(
                    group is passage_group
                    for passage in module.passages
                    for passage_group in passage.question_groups
                )
                reading_ids_match = (
                    group.passage_id in available_passage_ids and group.module_id == module.id
                )
                if module.module_type == ModuleType.READING and not (
                    reading_relationship_matches or reading_ids_match
                ):
                    issues.append(
                        ValidationIssue(
                            path=f"{prefix}.question_groups.{group.id}",
                            message="Reading question groups must reference an available passage.",
                        )
                    )
                    continue
                listening_relationship_matches = any(
                    group is part_group
                    for part in module.listening_parts
                    for part_group in part.question_groups
                )
                listening_ids_match = (
                    group.listening_part_id in available_part_ids and group.module_id == module.id
                )
                if module.module_type == ModuleType.LISTENING and not (
                    listening_relationship_matches or listening_ids_match
                ):
                    issues.append(
                        ValidationIssue(
                            path=f"{prefix}.question_groups.{group.id}",
                            message="Listening question groups must reference an available Part.",
                        )
                    )
                    continue
                if not question_registry.supports(group.question_type):
                    issues.append(
                        ValidationIssue(
                            path=f"{prefix}.question_groups.{group.id}",
                            message=f"Unsupported question type: {group.question_type}.",
                        )
                    )
                    continue
                if not group.questions:
                    issues.append(
                        ValidationIssue(
                            path=f"{prefix}.question_groups.{group.id}",
                            message="The question group is empty.",
                        )
                    )
                passage_blocks = normalized_passages.get(group.passage_id, [])
                question_rows = [
                    {
                        "id": question.id,
                        "number": question.number,
                        "prompt": question.prompt,
                        "config": question.config,
                        "answer_key": question.answer_key,
                        "explanation": question.explanation,
                        "order_index": question.order_index,
                    }
                    for question in group.questions
                ]
                try:
                    normalized_config, normalized_questions = normalize_question_group_payload(
                        question_type=group.question_type,
                        group_config=group.config,
                        questions=question_rows,
                        group_id=group.id,
                        passage_blocks=passage_blocks,
                        module_type=module.module_type,
                    )
                except (AttributeError, KeyError, TypeError, ValidationError, ValueError) as exc:
                    issues.append(
                        ValidationIssue(
                            path=f"{prefix}.question_groups.{group.id}",
                            message=f"Invalid question group configuration: {exc}",
                        )
                    )
                    continue
                for question, normalized in zip(group.questions, normalized_questions, strict=True):
                    key = normalized["answer_key"]
                    question_path = f"{prefix}.questions.{question.number}"
                    if group.question_type == "multiple_choice_multiple":
                        required = normalized["config"].get("min_selections", 2)
                        if len(key.get("values", [])) != required:
                            issues.append(ValidationIssue(
                                path=question_path,
                                message=f"Select exactly {required} official answers before publishing.",
                            ))
                            continue
                    elif not any(key.get(field) for field in ("value", "accepted")):
                        issues.append(ValidationIssue(
                            path=question_path, message="Answer key is incomplete."
                        ))
                        continue
                    try:
                        question_registry.validate(
                            group.question_type,
                            normalized_config,
                            normalized["config"],
                            normalized["answer_key"],
                        )
                        TestService._validate_references(
                            group,
                            question,
                            group_config=normalized_config,
                            question_config=normalized["config"],
                            answer_key=normalized["answer_key"],
                            passage_blocks=passage_blocks,
                        )
                    except (ValidationError, KeyError, ValueError) as exc:
                        issues.append(
                            ValidationIssue(
                                path=question_path,
                                message=f"Invalid question configuration: {exc}",
                            )
                        )
                try:
                    TestService._validate_group_references(
                        group,
                        normalized_config,
                        normalized_questions,
                        module_type=module.module_type,
                    )
                except (ValidationError, KeyError, ValueError) as exc:
                    issues.append(
                        ValidationIssue(
                            path=f"{prefix}.question_groups.{group.id}",
                            message=f"Invalid question group configuration: {exc}",
                        )
                    )
            if module.module_type == ModuleType.READING:
                meaningful_passages = [
                    passage
                    for passage in module.passages
                    if any(
                        str(block.get("text", "")).strip()
                        for block in normalized_passages.get(passage.id, [])
                    )
                ]
                if meaningful_passages and question_numbers:
                    usable_modules += 1
                if len(module.passages) != 3:
                    warnings.append(
                        ValidationIssue(
                            path="reading.passages",
                            message=f"IELTS readiness: Reading contains {len(module.passages)} / 3 passages.",
                        )
                    )
            elif module.module_type == ModuleType.LISTENING:
                if module.listening_parts and question_numbers:
                    usable_modules += 1
            elif module.module_type == ModuleType.WRITING:
                if any(task.prompt.strip() for task in module.writing_tasks):
                    usable_modules += 1
        if version.modules and usable_modules == 0:
            issues.append(
                ValidationIssue(
                    path="modules",
                    message="Add at least one usable module with valid question content.",
                )
            )
        return ValidationResult(valid=not issues, errors=issues, warnings=warnings)

    @staticmethod
    def _validate_references(
        group: QuestionGroup,
        question: Question,
        *,
        group_config: dict | None = None,
        question_config: dict | None = None,
        answer_key: dict | None = None,
        passage_blocks: list[dict] | None = None,
    ) -> None:
        resolved_group_config = group_config if group_config is not None else group.config
        resolved_question_config = (
            question_config if question_config is not None else question.config
        )
        resolved_answer_key = answer_key if answer_key is not None else question.answer_key
        if group.question_type == "multiple_choice":
            option_ids = {str(option["id"]) for option in resolved_question_config["options"]}
            if resolved_answer_key["value"] not in option_ids:
                raise ValueError("The answer key does not reference an available option")
        elif group.question_type == "multiple_choice_multiple":
            option_ids = {str(option["id"]) for option in resolved_question_config["options"]}
            values = set(resolved_answer_key["values"])
            if not values or not values.issubset(option_ids):
                raise ValueError("The answer key references unavailable options")
            selected_count = len(values)
            if not (
                resolved_question_config["min_selections"]
                <= selected_count
                <= resolved_question_config["max_selections"]
            ):
                raise ValueError("The answer key does not satisfy the selection limits")
        elif group.question_type == "true_false_not_given":
            if resolved_answer_key["value"] not in {"TRUE", "FALSE", "NOT_GIVEN"}:
                raise ValueError("The answer key must be TRUE, FALSE, or NOT_GIVEN")
        elif group.question_type == "yes_no_not_given":
            if resolved_answer_key["value"] not in {"YES", "NO", "NOT_GIVEN"}:
                raise ValueError("The answer key must be YES, NO, or NOT_GIVEN")
        elif group.question_type == "matching_headings":
            option_ids = {str(option["id"]) for option in resolved_group_config["options"]}
            if resolved_answer_key["value"] not in option_ids:
                raise ValueError("The heading key does not reference an available heading")
            paragraph_ids = {
                str(block["id"])
                for block in (passage_blocks or [])
                if block.get("type") == "paragraph"
            }
            if str(resolved_question_config["target_block_id"]) not in paragraph_ids:
                raise ValueError("The paragraph target does not reference an available block")
        elif group.question_type == "matching_information":
            paragraph_ids = {
                str(block["id"])
                for block in (passage_blocks or [])
                if block.get("type") == "paragraph"
            }
            if resolved_answer_key["value"] not in paragraph_ids:
                raise ValueError("The answer key does not reference an available passage paragraph")
        elif group.question_type in {
            "matching",
            "matching_features",
            "matching_sentence_endings",
            "summary_completion_word_list",
            "plan_labelling",
            "map_labelling",
        }:
            option_ids = {str(option["id"]) for option in resolved_group_config["options"]}
            if resolved_answer_key["value"] not in option_ids:
                raise ValueError("The answer key does not reference an available option")

    @staticmethod
    def _validate_group_references(
        group: QuestionGroup,
        group_config: dict,
        normalized_questions: list[dict],
        *,
        module_type: ModuleType = ModuleType.READING,
    ) -> None:
        question_ids = {str(question["id"]) for question in normalized_questions}
        if group.question_type in {"plan_labelling", "map_labelling"}:
            if (
                group.image_asset is None
                or group.image_asset.asset_type != AssetType.QUESTION_IMAGE
                or group.image_asset.test_version_id != group.module.test_version_id
            ):
                raise ValueError(
                    "Visual labelling requires a question image owned by this test version"
                )
            if module_type == ModuleType.READING:
                marker_question_ids = {
                    str(marker["question_id"]) for marker in group_config.get("markers", [])
                }
                if marker_question_ids != question_ids:
                    raise ValueError(
                        "Visual markers must reference every group question exactly once"
                    )
        if group.question_type == "diagram_labelling":
            if (
                group.image_asset is None
                or group.image_asset.asset_type != AssetType.QUESTION_IMAGE
                or group.image_asset.test_version_id != group.module.test_version_id
            ):
                raise ValueError(
                    "Diagram labelling requires a question image owned by this test version"
                )
            item_question_ids = [str(item["question_id"]) for item in group_config.get("items", [])]
            if (
                len(item_question_ids) != len(set(item_question_ids))
                or set(item_question_ids) != question_ids
            ):
                raise ValueError("Diagram items must reference every group question exactly once")
            if any(
                str(question.get("prompt") or "").count("{{gap}}") != 1
                for question in normalized_questions
            ):
                raise ValueError(
                    "Every diagram question prompt must contain exactly one {{gap}} marker"
                )
        if group.question_type == "table_completion":
            layout = group_config.get("layout", {})
            gap_ids = [
                str(segment.get("question_id"))
                for row in layout.get("rows", [])
                for cell in row.get("cells", [])
                for segment in cell.get("segments", [])
                if segment.get("type") == "GAP"
            ]
            if len(gap_ids) != len(set(gap_ids)) or set(gap_ids) != question_ids:
                raise ValueError(
                    "Every table completion question must map to exactly one layout gap"
                )
        if group.question_type == "note_completion":
            layout = group_config.get("layout", {})
            gap_ids = [
                str(segment.get("question_id"))
                for block in layout.get("blocks", [])
                for segment in block.get("segments", [])
                if segment.get("type") == "GAP"
            ]
            if len(gap_ids) != len(set(gap_ids)) or set(gap_ids) != question_ids:
                raise ValueError(
                    "Every note completion question must map to exactly one layout gap"
                )
        if group.question_type in {
            "form_completion",
            "flow_chart_completion",
            "summary_completion",
            "sentence_completion",
        }:
            layout = group_config.get("layout", {})
            gap_ids = {
                str(cell.get("question_id"))
                for row in layout.get("rows", [])
                for cell in row.get("cells", [])
                if cell.get("type") == "GAP"
            } | {
                str(node.get("question_id"))
                for node in layout.get("nodes", [])
                if node.get("type") == "GAP"
            }
            if gap_ids != question_ids:
                raise ValueError("Every completion question must map to exactly one layout gap")
        if group.question_type == "text_completion":
            gap_ids = [
                str(segment.get("question_id"))
                for block in group_config.get("blocks", [])
                for segment in block.get("segments", [])
                if segment.get("type") == "GAP"
            ]
            if len(gap_ids) != len(set(gap_ids)) or set(gap_ids) != question_ids:
                raise ValueError("Every text completion question must map to exactly one gap")
        if group.question_type == "summary_completion_word_list":
            gap_ids = [
                str(segment.get("question_id"))
                for block in group_config.get("blocks", [])
                for segment in block.get("segments", [])
                if segment.get("type") == "GAP"
            ]
            if len(gap_ids) != len(set(gap_ids)) or set(gap_ids) != question_ids:
                raise ValueError("Every word-list summary question must map to exactly one gap")

    async def validate(self, version_id: uuid.UUID) -> ValidationResult:
        return self.validate_version(await self.get_version(version_id))

    async def publish(self, version_id: uuid.UUID) -> TestVersion:
        async with self.session.begin():
            test_id = await self.session.scalar(
                select(TestVersion.test_id).where(TestVersion.id == version_id)
            )
            if test_id is None:
                raise AppError(
                    "TEST_VERSION_NOT_FOUND", "The requested test version does not exist.", 404
                )
            test = await self.session.scalar(
                select(Test).where(Test.id == test_id).with_for_update()
            )
            assert test is not None
            if test.archived_at is not None:
                raise AppError("TEST_ARCHIVED", "Restore this test before publishing.", 409)
            version = await self.session.scalar(
                version_detail_query()
                .where(TestVersion.id == version_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            if version is None:
                raise AppError(
                    "TEST_VERSION_NOT_FOUND", "The requested test version does not exist.", 404
                )
            if version.status != VersionStatus.DRAFT:
                raise AppError(
                    "TEST_VERSION_IMMUTABLE", "Only draft versions can be published.", 409
                )
            validation = self.validate_version(version)
            if not validation.valid:
                raise AppError(
                    "VALIDATION_FAILED",
                    "The test version has validation errors and cannot be published.",
                    422,
                )
            self._persist_normalized_draft(version)
            await self.session.execute(
                update(TestVersion)
                .where(
                    TestVersion.test_id == version.test_id,
                    TestVersion.id != version.id,
                    TestVersion.status == VersionStatus.PUBLISHED,
                )
                .values(status=VersionStatus.ARCHIVED)
            )
            version.status = VersionStatus.PUBLISHED
            version.published_at = datetime.now(UTC)
            await self.session.flush()
        return await self.get_version(version_id)

    @staticmethod
    def _persist_normalized_draft(version: TestVersion) -> None:
        for module in version.modules:
            passage_blocks = {
                passage.id: normalize_passage_blocks(passage.content_json, passage.id)
                for passage in module.passages
            }
            for passage in module.passages:
                blocks = passage_blocks[passage.id]
                passage.content_json = blocks
            for group in module.question_groups:
                question_rows = [
                    {
                        "id": question.id,
                        "number": question.number,
                        "prompt": question.prompt,
                        "config": question.config,
                        "answer_key": question.answer_key,
                        "explanation": question.explanation,
                        "order_index": question.order_index,
                    }
                    for question in group.questions
                ]
                config, normalized_questions = normalize_question_group_payload(
                    question_type=group.question_type,
                    group_config=group.config,
                    questions=question_rows,
                    group_id=group.id,
                    passage_blocks=passage_blocks.get(group.passage_id, []),
                    module_type=module.module_type,
                )
                group.config = config
                for question, normalized in zip(group.questions, normalized_questions, strict=True):
                    question.config = normalized["config"]
                    question.answer_key = normalized["answer_key"]

    async def ensure_draft(self, version_id: uuid.UUID) -> TestVersion:
        version = await self.session.scalar(
            select(TestVersion)
            .where(TestVersion.id == version_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if version is None:
            raise AppError(
                "TEST_VERSION_NOT_FOUND", "The requested test version does not exist.", 404
            )
        if version.status != VersionStatus.DRAFT:
            raise AppError("TEST_VERSION_IMMUTABLE", "Published versions cannot be changed.", 409)
        return version
