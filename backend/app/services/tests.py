import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domains.questions import question_registry
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
            is_nonempty = {
                ModuleType.READING: bool(module.passages),
                ModuleType.LISTENING: bool(module.listening_parts),
                ModuleType.WRITING: bool(module.writing_tasks),
            }[module.module_type]
            if not is_nonempty:
                issues.append(
                    ValidationIssue(path=prefix, message=f"The {prefix} module has no content.")
                )
            for group in module.question_groups:
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
                for question in group.questions:
                    try:
                        question_registry.validate(
                            group.question_type,
                            group.config,
                            question.config,
                            question.answer_key,
                        )
                        TestService._validate_references(group, question)
                    except (ValidationError, KeyError, ValueError) as exc:
                        issues.append(
                            ValidationIssue(
                                path=f"{prefix}.questions.{question.number}",
                                message=f"Invalid question configuration: {exc}",
                            )
                        )
        return ValidationResult(valid=not issues, errors=issues)

    @staticmethod
    def _validate_references(group: QuestionGroup, question: Question) -> None:
        if group.question_type == "multiple_choice":
            option_ids = {option["id"] for option in question.config["options"]}
            if question.answer_key["accepted"][0] not in option_ids:
                raise ValueError("The answer key does not reference an available option")
        elif group.question_type == "true_false_not_given":
            if question.answer_key["accepted"][0] not in {"TRUE", "FALSE", "NOT_GIVEN"}:
                raise ValueError("The answer key must be TRUE, FALSE, or NOT_GIVEN")
        elif group.question_type == "matching_headings":
            option_ids = {option["id"] for option in group.config["options"]}
            if question.answer_key["accepted"][0] not in option_ids:
                raise ValueError("The heading key does not reference an available heading")

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
            version.status = VersionStatus.PUBLISHED
            version.published_at = datetime.now(UTC)
            await self.session.flush()
        return await self.get_version(version_id)

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
