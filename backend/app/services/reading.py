import uuid

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.domains.questions import question_registry
from app.domains.questions.normalization import (
    normalize_passage_blocks,
    normalize_question_group_payload,
)
from app.models import (
    Asset,
    ListeningPart,
    Question,
    QuestionGroup,
    ReadingPassage,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.models.enums import AssetType, ModuleType, VersionStatus
from app.repositories.tests import TestRepository
from app.schemas.assets import AssetResponse
from app.schemas.content import (
    BuilderListeningPart,
    BuilderModule,
    BuilderPassage,
    BuilderQuestion,
    BuilderQuestionGroup,
    BuilderVersion,
    BuilderWritingTask,
    ModuleCreate,
    PassageWrite,
    QuestionGroupOrderWrite,
    QuestionGroupWrite,
    QuestionWrite,
)


class ReadingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def builder_version(self, version_id: uuid.UUID) -> BuilderVersion:
        version = await TestRepository(self.session).get_version(version_id)
        if version is None:
            raise AppError("TEST_VERSION_NOT_FOUND", "The test version does not exist.", 404)
        return self._present_version(version)

    async def create_module(self, version_id: uuid.UUID, body: ModuleCreate) -> BuilderModule:
        async with self.session.begin():
            version = await self._draft_version(version_id)
            if any(item.module_type == body.module_type for item in version.modules):
                raise AppError("MODULE_EXISTS", "This module already exists.", 409)
            module = TestModule(
                module_type=body.module_type,
                title=body.title,
                recommended_duration_seconds=body.recommended_duration_seconds,
                order_index=len(version.modules),
            )
            version.modules.append(module)
            if body.module_type == ModuleType.WRITING:
                module.writing_tasks.extend(
                    [
                        WritingTask(
                            task_number=1,
                            prompt="",
                            minimum_recommended_words=150,
                            recommended_duration_seconds=1200,
                            order_index=0,
                        ),
                        WritingTask(
                            task_number=2,
                            prompt="",
                            minimum_recommended_words=250,
                            recommended_duration_seconds=2400,
                            order_index=1,
                        ),
                    ]
                )
            await self.session.flush()
            module_id = module.id
        version = await TestRepository(self.session).get_version(version_id)
        assert version is not None
        return next(item for item in self._present_version(version).modules if item.id == module_id)

    async def create_passage(self, version_id: uuid.UUID, body: PassageWrite) -> BuilderPassage:
        async with self.session.begin():
            version = await self._draft_version(version_id)
            module = next(
                (item for item in version.modules if item.module_type == ModuleType.READING), None
            )
            if module is None:
                raise AppError("READING_MODULE_NOT_FOUND", "Create the Reading module first.", 422)
            passage = ReadingPassage(
                module_id=module.id,
                title=body.title.strip(),
                order_index=body.order_index,
                content_json=[item.model_dump(mode="json") for item in body.blocks],
                plain_text="\n\n".join(item.text for item in body.blocks),
            )
            self.session.add(passage)
            await self.session.flush()
            passage_id = passage.id
        return await self.get_passage(passage_id)

    async def update_passage(self, passage_id: uuid.UUID, body: PassageWrite) -> BuilderPassage:
        async with self.session.begin():
            passage = await self._draft_passage(passage_id)
            passage.title = body.title.strip()
            passage.order_index = body.order_index
            passage.content_json = [item.model_dump(mode="json") for item in body.blocks]
            passage.plain_text = "\n\n".join(item.text for item in body.blocks)
            await self._canonicalize_module(passage.module_id)
        return await self.get_passage(passage_id)

    async def delete_passage(self, passage_id: uuid.UUID) -> None:
        async with self.session.begin():
            passage = await self._draft_passage(passage_id)
            if passage.question_groups:
                raise AppError(
                    "PASSAGE_HAS_QUESTION_GROUPS",
                    "Delete this passage's question groups before deleting the passage.",
                    409,
                )
            await self.session.delete(passage)

    async def get_passage(self, passage_id: uuid.UUID) -> BuilderPassage:
        passage = await self.session.scalar(
            self._passage_query().where(ReadingPassage.id == passage_id)
        )
        if passage is None:
            raise AppError("PASSAGE_NOT_FOUND", "The passage does not exist.", 404)
        return self._present_passage(passage)

    async def create_group(
        self, passage_id: uuid.UUID, body: QuestionGroupWrite
    ) -> BuilderQuestionGroup:
        async with self.session.begin():
            passage = await self._draft_passage(passage_id)
            await self._validate_image_asset(passage.module.test_version_id, body)
            passage_blocks = normalize_passage_blocks(passage.content_json, passage.id)
            group_id = uuid.uuid4()
            body = self._normalize_group_body(body, group_id, passage_blocks)
            self._validate_group_body(body, passage_blocks)
            self._validate_local_question_numbers(body)
            # QuestionGroup.order_index is module-global. New Builder groups are
            # appended safely, then canonicalized into passage presentation order.
            await self.session.scalar(
                select(TestModule.id).where(TestModule.id == passage.module_id).with_for_update()
            )
            highest_group_order = await self.session.scalar(
                select(func.max(QuestionGroup.order_index)).where(
                    QuestionGroup.module_id == passage.module_id
                )
            )
            group = QuestionGroup(
                id=group_id,
                module_id=passage.module_id,
                passage_id=passage.id,
                image_asset_id=body.image_asset_id,
                question_type=body.question_type,
                instruction=body.instruction,
                config=body.config,
                order_index=(highest_group_order if highest_group_order is not None else -1) + 1,
            )
            self._apply_questions(group, body)
            self.session.add(group)
            await self.session.flush()
            await self._canonicalize_module(passage.module_id)
            group_id = group.id
        return await self.get_group(group_id)

    async def update_group(
        self, group_id: uuid.UUID, body: QuestionGroupWrite
    ) -> BuilderQuestionGroup:
        deleted_path: str | None = None
        async with self.session.begin():
            group = await self._draft_group(group_id)
            previous_image_asset_id = group.image_asset_id
            await self._validate_image_asset(group.module.test_version_id, body)
            passage_blocks = (
                normalize_passage_blocks(group.passage.content_json, group.passage.id)
                if group.passage
                else []
            )
            body = self._normalize_group_body(body, group.id, passage_blocks)
            self._validate_group_body(body, passage_blocks)
            self._validate_local_question_numbers(body)
            group.question_type = body.question_type
            group.instruction = body.instruction
            group.config = body.config
            group.image_asset_id = body.image_asset_id
            existing = {item.id: item for item in group.questions}
            for temporary_index, question in enumerate(existing.values(), start=1):
                question.number = -temporary_index
                question.order_index = -temporary_index
            await self.session.flush()
            retained: set[uuid.UUID] = set()
            for item in body.questions:
                if item.id is not None and item.id in existing:
                    question = existing[item.id]
                    question.number = item.number
                    question.prompt = item.prompt
                    question.config = item.config
                    question.answer_key = item.answer_key
                    question.explanation = item.explanation
                    question.order_index = item.order_index
                    retained.add(item.id)
                else:
                    question = Question(
                        id=item.id or uuid.uuid4(),
                        number=item.number,
                        prompt=item.prompt,
                        config=item.config,
                        answer_key=item.answer_key,
                        explanation=item.explanation,
                        order_index=item.order_index,
                    )
                    group.questions.append(question)
            for question_id, question in existing.items():
                if question_id not in retained:
                    group.questions.remove(question)
            await self.session.flush()
            await self._canonicalize_module(group.module_id)
            if previous_image_asset_id and previous_image_asset_id != group.image_asset_id:
                from app.services.tests import TestService

                deleted_path = await TestService(self.session).cleanup_asset_if_unreferenced(
                    previous_image_asset_id
                )
        if deleted_path:
            from app.services.tests import TestService

            TestService._delete_files([deleted_path])
        return await self.get_group(group_id)

    async def delete_group(self, group_id: uuid.UUID) -> None:
        deleted_path: str | None = None
        async with self.session.begin():
            group = await self._draft_group(group_id)
            module_id = group.module_id
            image_asset_id = group.image_asset_id
            await self.session.delete(group)
            await self.session.flush()
            await self._canonicalize_module(module_id)
            if image_asset_id:
                from app.services.tests import TestService

                deleted_path = await TestService(self.session).cleanup_asset_if_unreferenced(
                    image_asset_id
                )
        if deleted_path:
            from app.services.tests import TestService

            TestService._delete_files([deleted_path])

    async def reorder_groups(self, module_id: uuid.UUID, body: QuestionGroupOrderWrite) -> None:
        async with self.session.begin():
            module = await self.session.scalar(
                select(TestModule)
                .where(TestModule.id == module_id)
                .options(
                    selectinload(TestModule.question_groups).selectinload(QuestionGroup.questions),
                    selectinload(TestModule.test_version),
                )
                .with_for_update()
            )
            if module is None:
                raise AppError("TEST_MODULE_NOT_FOUND", "The test module does not exist.", 404)
            if module.test_version.status != VersionStatus.DRAFT:
                raise AppError(
                    "TEST_VERSION_IMMUTABLE", "Published versions cannot be changed.", 409
                )
            groups = {group.id: group for group in module.question_groups}
            if set(body.group_ids) != set(groups):
                raise AppError(
                    "INVALID_GROUP_ORDER",
                    "The order must contain every question group exactly once.",
                    422,
                )
            for temporary_index, group_id in enumerate(body.group_ids, start=1):
                groups[group_id].order_index = -temporary_index
            await self.session.flush()
            for order_index, group_id in enumerate(body.group_ids):
                groups[group_id].order_index = order_index
            await self._canonicalize_module(module_id)

    async def _canonicalize_module(self, module_id: uuid.UUID) -> None:
        module = await self.session.scalar(
            select(TestModule)
            .where(TestModule.id == module_id)
            .options(
                selectinload(TestModule.passages),
                selectinload(TestModule.listening_parts),
                selectinload(TestModule.question_groups).selectinload(QuestionGroup.questions),
            )
            .execution_options(populate_existing=True)
        )
        assert module is not None
        passage_order = {passage.id: passage.order_index for passage in module.passages}
        part_order = {part.id: part.order_index for part in module.listening_parts}
        ordered_groups = sorted(
            module.question_groups,
            key=lambda group: (
                passage_order.get(
                    group.passage_id,
                    part_order.get(group.listening_part_id, len(passage_order) + len(part_order)),
                ),
                group.order_index,
            ),
        )
        group_questions = [
            (group, sorted(group.questions, key=lambda item: item.order_index))
            for group in ordered_groups
        ]
        all_questions = [question for _, questions in group_questions for question in questions]
        for temporary_index, group in enumerate(ordered_groups, start=1):
            group.order_index = -temporary_index
        for temporary_number, question in enumerate(all_questions, start=1):
            question.number = -temporary_number
            question.order_index = -temporary_number
        await self.session.flush()
        for order_index, group in enumerate(ordered_groups):
            group.order_index = order_index
        next_number = 1
        for _, questions in group_questions:
            for order_index, question in enumerate(questions):
                question.number = next_number
                question.order_index = order_index
                next_number += 1

    async def get_group(self, group_id: uuid.UUID) -> BuilderQuestionGroup:
        group = await self.session.scalar(
            select(QuestionGroup)
            .where(QuestionGroup.id == group_id)
            .options(
                selectinload(QuestionGroup.questions),
                selectinload(QuestionGroup.passage),
                selectinload(QuestionGroup.listening_part),
                selectinload(QuestionGroup.image_asset),
            )
        )
        if group is None:
            raise AppError("QUESTION_GROUP_NOT_FOUND", "The question group does not exist.", 404)
        blocks = (
            normalize_passage_blocks(group.passage.content_json, group.passage.id)
            if group.passage
            else []
        )
        return self._present_group(group, blocks)

    async def _draft_version(self, version_id: uuid.UUID) -> TestVersion:
        version = await self.session.scalar(
            select(TestVersion)
            .where(TestVersion.id == version_id)
            .options(selectinload(TestVersion.modules))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if version is None:
            raise AppError("TEST_VERSION_NOT_FOUND", "The test version does not exist.", 404)
        if version.status != VersionStatus.DRAFT:
            raise AppError("TEST_VERSION_IMMUTABLE", "Published versions cannot be changed.", 409)
        return version

    async def _draft_passage(self, passage_id: uuid.UUID) -> ReadingPassage:
        passage = await self.session.scalar(
            self._passage_query().where(ReadingPassage.id == passage_id).with_for_update()
        )
        if passage is None:
            raise AppError("PASSAGE_NOT_FOUND", "The passage does not exist.", 404)
        if passage.module.test_version.status != VersionStatus.DRAFT:
            raise AppError("TEST_VERSION_IMMUTABLE", "Published versions cannot be changed.", 409)
        return passage

    async def _draft_group(self, group_id: uuid.UUID) -> QuestionGroup:
        group = await self.session.scalar(
            select(QuestionGroup)
            .where(QuestionGroup.id == group_id)
            .options(
                selectinload(QuestionGroup.questions),
                selectinload(QuestionGroup.passage),
                selectinload(QuestionGroup.listening_part),
                selectinload(QuestionGroup.image_asset),
                selectinload(QuestionGroup.module).selectinload(TestModule.test_version),
            )
            .with_for_update()
        )
        if group is None:
            raise AppError("QUESTION_GROUP_NOT_FOUND", "The question group does not exist.", 404)
        if group.module.test_version.status != VersionStatus.DRAFT:
            raise AppError("TEST_VERSION_IMMUTABLE", "Published versions cannot be changed.", 409)
        return group

    @staticmethod
    def _passage_query():
        return select(ReadingPassage).options(
            selectinload(ReadingPassage.module).selectinload(TestModule.test_version),
            selectinload(ReadingPassage.question_groups).selectinload(QuestionGroup.questions),
        )

    @staticmethod
    def _validate_local_question_numbers(body: QuestionGroupWrite) -> None:
        numbers = [item.number for item in body.questions]
        if len(numbers) != len(set(numbers)):
            raise AppError("DUPLICATE_QUESTION_NUMBER", "Question numbers must be unique.", 422)

    async def _validate_image_asset(
        self, version_id: uuid.UUID, body: QuestionGroupWrite
    ) -> None:
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
        if not visual or body.image_asset_id is None:
            return
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

    async def _ensure_numbers_available(
        self, module_id: uuid.UUID, body: QuestionGroupWrite, excluded_group_id: uuid.UUID | None
    ) -> None:
        """Retain Listening's existing cross-group number guard.

        Reading mutations intentionally use _validate_local_question_numbers because
        their module-wide display numbers are reassigned passage-first after every write.
        """
        self._validate_local_question_numbers(body)
        numbers = [item.number for item in body.questions]
        statement = (
            select(Question.number)
            .join(QuestionGroup)
            .where(QuestionGroup.module_id == module_id, Question.number.in_(numbers))
        )
        if excluded_group_id is not None:
            statement = statement.where(QuestionGroup.id != excluded_group_id)
        existing = list(await self.session.scalars(statement))
        if existing:
            raise AppError(
                "DUPLICATE_QUESTION_NUMBER",
                f"Question numbers already exist: {', '.join(map(str, existing))}.",
                422,
            )

    @staticmethod
    def _normalize_group_body(
        body: QuestionGroupWrite,
        group_id: uuid.UUID,
        passage_blocks: list[dict[str, object]],
    ) -> QuestionGroupWrite:
        config, questions = normalize_question_group_payload(
            question_type=body.question_type,
            group_config=body.config,
            questions=[item.model_dump(mode="json") for item in body.questions],
            group_id=group_id,
            passage_blocks=passage_blocks,
        )
        return body.model_copy(
            update={
                "config": config,
                "questions": [QuestionWrite.model_validate(item) for item in questions],
            }
        )

    @staticmethod
    def _validate_group_body(
        body: QuestionGroupWrite, passage_blocks: list[dict[str, object]]
    ) -> None:
        if not question_registry.supports(body.question_type):
            raise AppError("UNSUPPORTED_QUESTION_TYPE", "This question type is not supported.", 422)
        try:
            for question in body.questions:
                question_registry.validate(
                    body.question_type, body.config, question.config, question.answer_key
                )
                transient = Question(config=question.config, answer_key=question.answer_key)
                transient_group = QuestionGroup(
                    question_type=body.question_type,
                    config=body.config,
                    instruction="",
                    order_index=0,
                )
                from app.services.tests import TestService

                TestService._validate_references(
                    transient_group, transient, passage_blocks=passage_blocks
                )
            question_ids = {str(question.id) for question in body.questions if question.id}
            if body.question_type in {"plan_labelling", "map_labelling"}:
                marker_question_ids = [
                    str(marker["question_id"]) for marker in body.config.get("markers", [])
                ]
                if (
                    len(marker_question_ids) != len(set(marker_question_ids))
                    or set(marker_question_ids) != question_ids
                ):
                    raise ValueError(
                        "Visual markers must reference every group question exactly once"
                    )
                if body.image_asset_id is None:
                    raise ValueError("Visual labelling groups require an image asset")
            if body.question_type == "diagram_labelling":
                item_question_ids = [
                    str(item["question_id"]) for item in body.config.get("items", [])
                ]
                if (
                    len(item_question_ids) != len(set(item_question_ids))
                    or set(item_question_ids) != question_ids
                ):
                    raise ValueError(
                        "Diagram items must reference every group question exactly once"
                    )
                if body.image_asset_id is None:
                    raise ValueError("Diagram labelling groups require an image asset")
                if any(question.prompt.count("{{gap}}") != 1 for question in body.questions):
                    raise ValueError(
                        "Every diagram question prompt must contain exactly one {{gap}} marker"
                    )
            if body.question_type in {
                "form_completion",
                "note_completion",
                "table_completion",
                "flow_chart_completion",
                "summary_completion",
                "sentence_completion",
            }:
                layout = body.config.get("layout", {})
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
            if body.question_type == "text_completion":
                gap_ids = [
                    str(segment.get("question_id"))
                    for block in body.config.get("blocks", [])
                    for segment in block.get("segments", [])
                    if segment.get("type") == "GAP"
                ]
                if len(gap_ids) != len(set(gap_ids)) or set(gap_ids) != question_ids:
                    raise ValueError("Every text completion question must map to exactly one gap")
            if body.question_type == "summary_completion_word_list":
                gap_ids = [
                    str(segment.get("question_id"))
                    for block in body.config.get("blocks", [])
                    for segment in block.get("segments", [])
                    if segment.get("type") == "GAP"
                ]
                if len(gap_ids) != len(set(gap_ids)) or set(gap_ids) != question_ids:
                    raise ValueError("Every word-list summary question must map to exactly one gap")
        except (ValidationError, KeyError, ValueError) as exc:
            raise AppError("VALIDATION_FAILED", f"Invalid question group: {exc}", 422) from exc

    @staticmethod
    def _apply_questions(group: QuestionGroup, body: QuestionGroupWrite) -> None:
        for item in body.questions:
            group.questions.append(
                Question(
                    id=item.id or uuid.uuid4(),
                    number=item.number,
                    prompt=item.prompt,
                    config=item.config,
                    answer_key=item.answer_key,
                    explanation=item.explanation,
                    order_index=item.order_index,
                )
            )

    @classmethod
    def _present_version(cls, version: TestVersion) -> BuilderVersion:
        return BuilderVersion(
            id=version.id,
            test_id=version.test_id,
            test_title=version.test.title,
            version_number=version.version_number,
            status=version.status,
            modules=[
                BuilderModule(
                    id=module.id,
                    module_type=module.module_type,
                    title=module.title,
                    recommended_duration_seconds=module.recommended_duration_seconds,
                    audio_asset=(
                        AssetResponse.model_validate(module.audio_asset, from_attributes=True)
                        if module.audio_asset
                        else None
                    ),
                    passages=[cls._present_passage(item) for item in module.passages],
                    listening_parts=[
                        cls._present_listening_part(item) for item in module.listening_parts
                    ],
                    writing_tasks=[
                        cls._present_writing_task(item) for item in module.writing_tasks
                    ],
                )
                for module in version.modules
            ],
        )

    @staticmethod
    def _present_writing_task(task: WritingTask) -> BuilderWritingTask:
        return BuilderWritingTask(
            id=task.id,
            task_number=task.task_number,
            prompt=task.prompt,
            image_asset_id=task.image_asset_id,
            image_asset=(
                AssetResponse.model_validate(task.image_asset, from_attributes=True)
                if task.image_asset
                else None
            ),
            minimum_recommended_words=task.minimum_recommended_words,
            recommended_duration_seconds=task.recommended_duration_seconds,
            order_index=task.order_index,
        )

    @classmethod
    def _present_passage(cls, passage: ReadingPassage) -> BuilderPassage:
        blocks = normalize_passage_blocks(passage.content_json, passage.id)
        return BuilderPassage(
            id=passage.id,
            title=passage.title,
            order_index=passage.order_index,
            blocks=blocks,
            question_groups=[
                cls._present_group(item, blocks)
                for item in sorted(passage.question_groups, key=lambda row: row.order_index)
            ],
        )

    @staticmethod
    def _present_group(
        group: QuestionGroup, passage_blocks: list[dict[str, object]]
    ) -> BuilderQuestionGroup:
        question_rows = [
            {
                "id": item.id,
                "number": item.number,
                "prompt": item.prompt,
                "config": item.config,
                "answer_key": item.answer_key,
                "explanation": item.explanation,
                "order_index": item.order_index,
            }
            for item in sorted(group.questions, key=lambda row: row.order_index)
        ]
        config, questions = normalize_question_group_payload(
            question_type=group.question_type,
            group_config=group.config,
            questions=question_rows,
            group_id=group.id,
            passage_blocks=passage_blocks,
        )
        return BuilderQuestionGroup(
            id=group.id,
            question_type=group.question_type,
            instruction=group.instruction,
            config=config,
            order_index=group.order_index,
            questions=[BuilderQuestion.model_validate(item) for item in questions],
            image_asset_id=group.image_asset_id,
            image_asset=(
                AssetResponse.model_validate(group.image_asset, from_attributes=True)
                if group.image_asset
                else None
            ),
        )

    @classmethod
    def _present_listening_part(cls, part: ListeningPart) -> BuilderListeningPart:
        return BuilderListeningPart(
            id=part.id,
            title=part.title,
            order_index=part.order_index,
            question_groups=[
                cls._present_group(group, [])
                for group in sorted(part.question_groups, key=lambda item: item.order_index)
            ],
        )
