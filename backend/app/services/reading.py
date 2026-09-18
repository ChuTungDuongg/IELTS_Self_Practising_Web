import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.domains.questions import question_registry
from app.domains.questions.normalization import (
    normalize_passage_blocks,
    normalize_question_group_payload,
)
from app.models import Question, QuestionGroup, ReadingPassage, TestModule, TestVersion
from app.models.enums import ModuleType, VersionStatus
from app.repositories.tests import TestRepository
from app.schemas.content import (
    BuilderModule,
    BuilderPassage,
    BuilderQuestion,
    BuilderQuestionGroup,
    BuilderVersion,
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
            passage_blocks = normalize_passage_blocks(passage.content_json, passage.id)
            group_id = uuid.uuid4()
            body = self._normalize_group_body(body, group_id, passage_blocks)
            self._validate_group_body(body, passage_blocks)
            await self._ensure_numbers_available(passage.module_id, body, None)
            group = QuestionGroup(
                id=group_id,
                module_id=passage.module_id,
                passage_id=passage.id,
                question_type=body.question_type,
                instruction=body.instruction,
                config=body.config,
                order_index=body.order_index,
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
        async with self.session.begin():
            group = await self._draft_group(group_id)
            passage_blocks = (
                normalize_passage_blocks(group.passage.content_json, group.passage.id)
                if group.passage
                else []
            )
            body = self._normalize_group_body(body, group.id, passage_blocks)
            self._validate_group_body(body, passage_blocks)
            await self._ensure_numbers_available(group.module_id, body, group.id)
            group.question_type = body.question_type
            group.instruction = body.instruction
            group.config = body.config
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
                    question.number = item.number
                    question.prompt = item.prompt
                    question.config = item.config
                    question.answer_key = item.answer_key
                    question.explanation = item.explanation
                    question.order_index = item.order_index
                    retained.add(item.id)
                else:
                    question = Question(
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
        return await self.get_group(group_id)

    async def delete_group(self, group_id: uuid.UUID) -> None:
        async with self.session.begin():
            group = await self._draft_group(group_id)
            module_id = group.module_id
            await self.session.delete(group)
            await self.session.flush()
            await self._canonicalize_module(module_id)

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
                selectinload(TestModule.question_groups).selectinload(QuestionGroup.questions),
            )
        )
        assert module is not None
        passage_order = {passage.id: passage.order_index for passage in module.passages}
        ordered_groups = sorted(
            module.question_groups,
            key=lambda group: (
                passage_order.get(group.passage_id, len(passage_order)),
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

    async def _ensure_numbers_available(
        self, module_id: uuid.UUID, body: QuestionGroupWrite, excluded_group_id: uuid.UUID | None
    ) -> None:
        numbers = [item.number for item in body.questions]
        if len(numbers) != len(set(numbers)):
            raise AppError("DUPLICATE_QUESTION_NUMBER", "Question numbers must be unique.", 422)
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
                    passages=[cls._present_passage(item) for item in module.passages],
                )
                for module in version.modules
            ],
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
        )
