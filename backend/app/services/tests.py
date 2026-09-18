import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domains.questions import question_registry
from app.domains.questions.normalization import (
    normalize_passage_blocks,
    normalize_question_group_payload,
)
from app.models import (
    ListeningPart,
    Question,
    QuestionGroup,
    ReadingPassage,
    Test,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.models.enums import ModuleType, VersionStatus
from app.repositories.tests import TestRepository, version_detail_query
from app.schemas.common import ValidationIssue, ValidationResult
from app.schemas.content import TextBlock
from app.schemas.tests import TestCreate, VersionCreate


class TestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = TestRepository(session)

    async def list_tests(self) -> list[Test]:
        return await self.repository.list()

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

    async def get_version(self, version_id: uuid.UUID) -> TestVersion:
        version = await self.repository.get_version(version_id)
        if version is None:
            raise AppError(
                "TEST_VERSION_NOT_FOUND", "The requested test version does not exist.", 404
            )
        return version

    async def create_version(self, test_id: uuid.UUID, data: VersionCreate) -> TestVersion:
        async with self.session.begin():
            test = await self.repository.get(test_id)
            if test is None:
                raise AppError("TEST_NOT_FOUND", "The requested test does not exist.", 404)
            number = await self.repository.next_version_number(test_id)
            version = TestVersion(
                test_id=test_id, version_number=number, status=VersionStatus.DRAFT
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
                self._clone_content(source, version)
            await self.session.flush()
            version_id = version.id
        return await self.get_version(version_id)

    @staticmethod
    def _clone_content(source: TestVersion, target: TestVersion) -> None:
        for module in source.modules:
            new_module = TestModule(
                module_type=module.module_type,
                title=module.title,
                recommended_duration_seconds=module.recommended_duration_seconds,
                order_index=module.order_index,
            )
            target.modules.append(new_module)
            passage_map: dict[uuid.UUID, ReadingPassage] = {}
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
                new_module.listening_parts.append(
                    ListeningPart(
                        title=part.title,
                        order_index=part.order_index,
                        audio_asset_id=part.audio_asset_id,
                    )
                )
            for task in module.writing_tasks:
                new_module.writing_tasks.append(
                    WritingTask(
                        task_number=task.task_number,
                        prompt=task.prompt,
                        image_asset_id=task.image_asset_id,
                        minimum_recommended_words=task.minimum_recommended_words,
                        recommended_duration_seconds=task.recommended_duration_seconds,
                        order_index=task.order_index,
                    )
                )
            for group in module.question_groups:
                new_group = QuestionGroup(
                    passage=passage_map.get(group.passage_id),
                    section_reference=group.section_reference,
                    question_type=group.question_type,
                    instruction=group.instruction,
                    config=group.config,
                    order_index=group.order_index,
                )
                new_module.question_groups.append(new_group)
                for question in group.questions:
                    new_group.questions.append(
                        Question(
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
            else:
                ordered_groups = sorted(module.question_groups, key=lambda item: item.order_index)
            question_numbers = [
                question.number
                for group in ordered_groups
                for question in sorted(group.questions, key=lambda item: item.order_index)
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
            is_nonempty = {
                ModuleType.READING: bool(module.passages),
                ModuleType.LISTENING: bool(module.listening_parts),
                ModuleType.WRITING: bool(module.writing_tasks),
            }[module.module_type]
            if not is_nonempty:
                issues.append(
                    ValidationIssue(path=prefix, message=f"The {prefix} module has no content.")
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
            for group in module.question_groups:
                if module.module_type == ModuleType.READING and not any(
                    group is passage_group
                    for passage in module.passages
                    for passage_group in passage.question_groups
                ):
                    issues.append(
                        ValidationIssue(
                            path=f"{prefix}.question_groups.{group.id}",
                            message="Reading question groups must reference an available passage.",
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
                                path=f"{prefix}.questions.{question.number}",
                                message=f"Invalid question configuration: {exc}",
                            )
                        )
        return ValidationResult(valid=not issues, errors=issues)

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
        elif group.question_type == "true_false_not_given":
            if resolved_answer_key["value"] not in {"TRUE", "FALSE", "NOT_GIVEN"}:
                raise ValueError("The answer key must be TRUE, FALSE, or NOT_GIVEN")
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

    async def validate(self, version_id: uuid.UUID) -> ValidationResult:
        return self.validate_version(await self.get_version(version_id))

    async def publish(self, version_id: uuid.UUID) -> TestVersion:
        async with self.session.begin():
            version = await self.session.scalar(
                version_detail_query().where(TestVersion.id == version_id).with_for_update()
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
            version.status = VersionStatus.PUBLISHED
            version.published_at = datetime.now(UTC)
            await self.session.flush()
        return await self.get_version(version_id)

    @staticmethod
    def _persist_normalized_draft(version: TestVersion) -> None:
        for module in version.modules:
            for passage in module.passages:
                blocks = normalize_passage_blocks(passage.content_json, passage.id)
                passage.content_json = blocks
                for group in passage.question_groups:
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
                        passage_blocks=blocks,
                    )
                    group.config = config
                    for question, normalized in zip(
                        group.questions, normalized_questions, strict=True
                    ):
                        question.config = normalized["config"]
                        question.answer_key = normalized["answer_key"]

    async def ensure_draft(self, version_id: uuid.UUID) -> TestVersion:
        version = await self.session.scalar(
            select(TestVersion).where(TestVersion.id == version_id).with_for_update()
        )
        if version is None:
            raise AppError(
                "TEST_VERSION_NOT_FOUND", "The requested test version does not exist.", 404
            )
        if version.status != VersionStatus.DRAFT:
            raise AppError("TEST_VERSION_IMMUTABLE", "Published versions cannot be changed.", 409)
        return version
