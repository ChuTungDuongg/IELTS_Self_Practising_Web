import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models import Asset, ListeningPart, Question, QuestionGroup, TestModule, TestVersion
from app.models.enums import AssetType, ModuleType
from app.schemas.content import (
    BuilderListeningPart,
    BuilderModule,
    BuilderQuestionGroup,
    ListeningModuleAudioWrite,
    ListeningPartUpdate,
    ListeningPartWrite,
    QuestionGroupUpdate,
    QuestionGroupWrite,
    QuestionWrite,
)
from app.services.draft_revisions import advance_revision
from app.services.reading import ReadingService


class ListeningService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.shared = ReadingService(session)

    async def create_part(
        self, version_id: uuid.UUID, body: ListeningPartWrite
    ) -> BuilderListeningPart:
        async with self.session.begin():
            module = await self._draft_module_for_version(version_id)
            if any(part.order_index == body.order_index for part in module.listening_parts):
                raise AppError("LISTENING_PART_EXISTS", "This Listening part already exists.", 409)
            part = ListeningPart(
                module_id=module.id,
                title=body.title.strip(),
                order_index=body.order_index,
            )
            self.session.add(part)
            await self.session.flush()
            part_id = part.id
        return await self.get_part(part_id)

    async def update_part(
        self, part_id: uuid.UUID, body: ListeningPartUpdate
    ) -> BuilderListeningPart:
        async with self.session.begin():
            part = await self._draft_part(part_id)
            advance_revision(part, body.expected_revision)
            part.title = body.title.strip()
            part.order_index = body.order_index
            await self.shared._canonicalize_module(part.module_id)
            saved = await self.get_part(part_id)
        return saved

    async def delete_part(self, part_id: uuid.UUID) -> None:
        async with self.session.begin():
            part = await self._draft_part(part_id)
            if part.question_groups:
                raise AppError(
                    "LISTENING_PART_HAS_GROUPS",
                    "Delete this part's question groups before deleting the part.",
                    409,
                )
            await self.session.delete(part)

    async def attach_audio(
        self, module_id: uuid.UUID, body: ListeningModuleAudioWrite
    ) -> BuilderModule:
        deleted_path: str | None = None
        copied_path: str | None = None
        try:
            async with self.session.begin():
                module = await self._draft_module(module_id)
                advance_revision(module, body.expected_revision)
                previous_asset_id = module.audio_asset_id
                if body.asset_id is None:
                    module.audio_asset_id = None
                else:
                    from app.services.tests import TestService

                    repaired, copied_path = await TestService(
                        self.session
                    ).resolve_owned_or_inherited_asset(
                        target_version=module.test_version,
                        requested_asset_id=body.asset_id,
                        current_asset_id=module.audio_asset_id,
                        asset_type=AssetType.LISTENING_AUDIO,
                    )
                    asset = repaired or await self.session.scalar(
                        select(Asset).where(
                            Asset.id == body.asset_id,
                            Asset.test_version_id == module.test_version_id,
                            Asset.asset_type == AssetType.LISTENING_AUDIO,
                        )
                    )
                    if asset is None:
                        raise AppError(
                            "INVALID_AUDIO_ASSET",
                            "The audio asset does not belong to this draft version.",
                            422,
                        )
                    module.audio_asset_id = asset.id
                await self.session.flush()
                if previous_asset_id is not None and previous_asset_id != module.audio_asset_id:
                    from app.services.tests import TestService

                    deleted_path = await TestService(self.session).cleanup_asset_if_unreferenced(
                        previous_asset_id
                    )
                version_id = module.test_version_id
                version = await self.shared.builder_version(version_id)
                saved = next(item for item in version.modules if item.id == module_id)
        except BaseException:
            if copied_path:
                from app.services.tests import TestService

                TestService._delete_files([copied_path])
            raise
        if deleted_path:
            from app.services.tests import TestService

            TestService._delete_files([deleted_path])
        return saved

    async def create_group(
        self, part_id: uuid.UUID, body: QuestionGroupWrite
    ) -> BuilderQuestionGroup:
        async with self.session.begin():
            part = await self._draft_part(part_id)
            await self._validate_image_asset(part.module.test_version_id, body)
            group_id = uuid.uuid4()
            body = self.shared._normalize_group_body(
                body, group_id, [], module_type=ModuleType.LISTENING
            )
            self.shared._validate_group_body(body, [], module_type=ModuleType.LISTENING)
            await self.shared._ensure_numbers_available(part.module_id, body, None)
            group = QuestionGroup(
                id=group_id,
                module_id=part.module_id,
                listening_part_id=part.id,
                image_asset_id=body.image_asset_id,
                question_type=body.question_type,
                instruction=body.instruction,
                config=body.config,
                order_index=body.order_index,
            )
            self.shared._apply_questions(group, body)
            self.session.add(group)
            await self.session.flush()
            await self.shared._canonicalize_module(part.module_id, already_advanced={group.id})
        return await self.get_group(group_id)

    async def update_group(
        self, group_id: uuid.UUID, body: QuestionGroupUpdate
    ) -> BuilderQuestionGroup:
        deleted_path: str | None = None
        copied_path: str | None = None
        try:
            async with self.session.begin():
                group = await self._draft_group(group_id)
                advance_revision(group, body.expected_revision)
                previous_image_asset_id = group.image_asset_id
                if body.image_asset_id is not None:
                    from app.services.tests import TestService

                    repaired, copied_path = await TestService(
                        self.session
                    ).resolve_owned_or_inherited_asset(
                        target_version=group.module.test_version,
                        requested_asset_id=body.image_asset_id,
                        current_asset_id=group.image_asset_id,
                        asset_type=AssetType.QUESTION_IMAGE,
                    )
                    if repaired is not None:
                        body = body.model_copy(update={"image_asset_id": repaired.id})
                await self._validate_image_asset(group.module.test_version_id, body)
                body = self.shared._normalize_group_body(
                    body, group.id, [], module_type=ModuleType.LISTENING
                )
                self.shared._validate_group_body(body, [], module_type=ModuleType.LISTENING)
                await self.shared._ensure_numbers_available(group.module_id, body, group.id)
                group.question_type = body.question_type
                group.instruction = body.instruction
                group.config = body.config
                group.image_asset_id = body.image_asset_id
                group.order_index = body.order_index
                existing = {item.id: item for item in group.questions}
                for temporary_index, question in enumerate(existing.values(), start=1):
                    question.number = -temporary_index
                    question.order_index = -temporary_index
                await self.session.flush()
                retained: set[uuid.UUID] = set()
                for item in body.questions:
                    if item.id is not None and item.id in existing:
                        question = existing[item.id]
                        self._apply_question(question, item)
                        retained.add(item.id)
                    else:
                        question = Question(id=item.id or uuid.uuid4())
                        self._apply_question(question, item)
                        group.questions.append(question)
                for question_id, question in existing.items():
                    if question_id not in retained:
                        group.questions.remove(question)
                await self.session.flush()
                await self.shared._canonicalize_module(group.module_id, already_advanced={group.id})
                if previous_image_asset_id and previous_image_asset_id != group.image_asset_id:
                    from app.services.tests import TestService

                    deleted_path = await TestService(self.session).cleanup_asset_if_unreferenced(
                        previous_image_asset_id
                    )
                saved = await self.get_group(group_id)
        except BaseException:
            if copied_path:
                from app.services.tests import TestService

                TestService._delete_files([copied_path])
            raise
        if deleted_path:
            from app.services.tests import TestService

            TestService._delete_files([deleted_path])
        return saved

    async def get_part(self, part_id: uuid.UUID) -> BuilderListeningPart:
        part = await self.session.scalar(self._part_query().where(ListeningPart.id == part_id))
        if part is None:
            raise AppError("LISTENING_PART_NOT_FOUND", "The Listening part does not exist.", 404)
        return ReadingService._present_listening_part(part)

    async def get_group(self, group_id: uuid.UUID) -> BuilderQuestionGroup:
        group = await self.session.scalar(
            select(QuestionGroup)
            .where(QuestionGroup.id == group_id)
            .options(
                selectinload(QuestionGroup.questions),
                selectinload(QuestionGroup.image_asset),
            )
        )
        if group is None or group.listening_part_id is None:
            raise AppError("QUESTION_GROUP_NOT_FOUND", "The question group does not exist.", 404)
        return ReadingService._present_group(group, [], module_type=ModuleType.LISTENING)

    async def _draft_module_for_version(self, version_id: uuid.UUID) -> TestModule:
        from app.services.tests import TestService

        await TestService(self.session).ensure_draft(version_id)
        version = await self.session.scalar(
            select(TestVersion)
            .where(TestVersion.id == version_id)
            .options(selectinload(TestVersion.modules).selectinload(TestModule.listening_parts))
            .execution_options(populate_existing=True)
        )
        assert version is not None
        module = next(
            (item for item in version.modules if item.module_type == ModuleType.LISTENING), None
        )
        if module is None:
            raise AppError("LISTENING_MODULE_NOT_FOUND", "Create the Listening module first.", 422)
        return module

    async def _draft_module(self, module_id: uuid.UUID) -> TestModule:
        version_id = await self.session.scalar(
            select(TestModule.test_version_id).where(
                TestModule.id == module_id, TestModule.module_type == ModuleType.LISTENING
            )
        )
        if version_id is None:
            raise AppError(
                "LISTENING_MODULE_NOT_FOUND", "The Listening module does not exist.", 404
            )
        from app.services.tests import TestService

        await TestService(self.session).ensure_draft(version_id)
        module = await self.session.scalar(
            select(TestModule)
            .where(TestModule.id == module_id, TestModule.module_type == ModuleType.LISTENING)
            .options(selectinload(TestModule.test_version))
            .with_for_update()
        )
        if module is None or module.test_version_id != version_id:
            raise AppError(
                "LISTENING_MODULE_NOT_FOUND", "The Listening module does not exist.", 404
            )
        return module

    async def _draft_part(self, part_id: uuid.UUID) -> ListeningPart:
        version_id = await self.session.scalar(
            select(TestModule.test_version_id)
            .join(ListeningPart, ListeningPart.module_id == TestModule.id)
            .where(ListeningPart.id == part_id)
        )
        if version_id is None:
            raise AppError("LISTENING_PART_NOT_FOUND", "The Listening part does not exist.", 404)
        from app.services.tests import TestService

        await TestService(self.session).ensure_draft(version_id)
        part = await self.session.scalar(
            self._part_query().where(ListeningPart.id == part_id).with_for_update()
        )
        if part is None or part.module.test_version_id != version_id:
            raise AppError("LISTENING_PART_NOT_FOUND", "The Listening part does not exist.", 404)
        return part

    async def _draft_group(self, group_id: uuid.UUID) -> QuestionGroup:
        version_id = await self.session.scalar(
            select(TestModule.test_version_id)
            .join(QuestionGroup, QuestionGroup.module_id == TestModule.id)
            .where(QuestionGroup.id == group_id, QuestionGroup.listening_part_id.is_not(None))
        )
        if version_id is None:
            raise AppError("QUESTION_GROUP_NOT_FOUND", "The question group does not exist.", 404)
        from app.services.tests import TestService

        await TestService(self.session).ensure_draft(version_id)
        group = await self.session.scalar(
            select(QuestionGroup)
            .where(QuestionGroup.id == group_id)
            .options(
                selectinload(QuestionGroup.questions),
                selectinload(QuestionGroup.listening_part),
                selectinload(QuestionGroup.module).selectinload(TestModule.test_version),
            )
            .with_for_update()
        )
        if (
            group is None
            or group.listening_part_id is None
            or group.module.test_version_id != version_id
        ):
            raise AppError("QUESTION_GROUP_NOT_FOUND", "The question group does not exist.", 404)
        return group

    async def _validate_image_asset(self, version_id: uuid.UUID, body: QuestionGroupWrite) -> None:
        visual = body.question_type in {
            "plan_labelling",
            "map_labelling",
            "diagram_labelling",
        }
        if not visual and body.image_asset_id is not None:
            raise AppError(
                "INVALID_IMAGE_ASSET",
                "Only visual labelling groups can attach a question image.",
                422,
            )
        if not visual:
            return
        if body.image_asset_id is None:
            raise AppError("INVALID_IMAGE_ASSET", "Upload a question image first.", 422)
        asset = await self.session.scalar(
            select(Asset).where(
                Asset.id == body.image_asset_id,
                Asset.test_version_id == version_id,
                Asset.asset_type == AssetType.QUESTION_IMAGE,
            )
        )
        if asset is None:
            raise AppError(
                "INVALID_IMAGE_ASSET",
                "The question image does not belong to this draft version.",
                422,
            )

    @staticmethod
    def _apply_question(question: Question, item: QuestionWrite) -> None:
        question.number = item.number
        question.prompt = item.prompt
        question.config = item.config
        question.answer_key = item.answer_key
        question.explanation = item.explanation
        question.order_index = item.order_index

    @staticmethod
    def _part_query():
        return select(ListeningPart).options(
            selectinload(ListeningPart.question_groups).selectinload(QuestionGroup.questions),
            selectinload(ListeningPart.question_groups).selectinload(QuestionGroup.image_asset),
            selectinload(ListeningPart.module).selectinload(TestModule.test_version),
        )
