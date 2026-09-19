from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.questions.registry import question_registry
from app.models import Asset, ListeningPart, Question, QuestionGroup
from app.models import Test as DomainTest
from app.models import TestModule as ModuleRecord
from app.models import TestVersion as VersionRecord
from app.models.enums import AssetType, ModuleType, VersionStatus
from app.schemas.content import ListeningModuleAudioWrite, ListeningPartWrite, QuestionGroupWrite
from app.services.attempts import AttemptService
from app.services.listening import ListeningService
from app.services.tests import TestService as VersionService


def test_listening_registry_supports_official_builder_templates() -> None:
    expected = {
        "multiple_choice",
        "multiple_choice_multiple",
        "matching",
        "plan_labelling",
        "map_labelling",
        "diagram_labelling",
        "form_completion",
        "note_completion",
        "table_completion",
        "flow_chart_completion",
        "summary_completion",
        "sentence_completion",
        "short_answer",
    }
    assert all(question_registry.supports(name) for name in expected)


def test_multiple_choice_multiple_evaluates_as_an_unordered_set() -> None:
    key = {"kind": "MULTIPLE_OPTIONS", "values": ["a", "c"], "order_matters": False}
    config = {
        "options": [
            {"id": "a", "label": "A", "text": "One"},
            {"id": "b", "label": "B", "text": "Two"},
            {"id": "c", "label": "C", "text": "Three"},
        ],
        "min_selections": 2,
        "max_selections": 2,
    }
    assert question_registry.evaluate("multiple_choice_multiple", key, ["c", "a"], config)
    assert not question_registry.evaluate("multiple_choice_multiple", key, ["a", "b"], config)


def test_visual_markers_require_normalized_coordinates() -> None:
    with pytest.raises(ValidationError):
        question_registry.validate_group(
            "map_labelling",
            {
                "options": [
                    {"id": "a", "label": "A", "text": "One"},
                    {"id": "b", "label": "B", "text": "Two"},
                ],
                "markers": [{"id": "m", "question_id": "q", "x": 1.1, "y": 0.5}],
            },
        )


def test_active_exam_group_never_contains_answer_keys() -> None:
    group = QuestionGroup(
        id=uuid4(), question_type="short_answer", instruction="Answer", config={}, order_index=0
    )
    question = Question(
        id=uuid4(),
        number=1,
        prompt="Prompt",
        config={"max_words": 2},
        answer_key={"kind": "TEXT", "accepted": ["secret"], "case_sensitive": False},
        order_index=0,
    )
    group.questions.append(question)
    payload = AttemptService._present_exam_group(group, {}, {}, [])
    dumped = payload.model_dump(mode="json")
    assert "answer_key" not in dumped["questions"][0]
    assert "secret" not in str(dumped)


def test_complete_listening_structure_validates_four_parts_and_global_numbering() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.LISTENING, order_index=0)
    version.modules.append(module)
    asset = Asset(
        id=uuid4(),
        asset_type=AssetType.LISTENING_AUDIO,
        relative_path="audio/shared.mp3",
        mime_type="audio/mpeg",
        original_name="shared.mp3",
        file_size=10,
    )
    module.audio_asset = asset
    for part_index in range(4):
        part = ListeningPart(
            id=uuid4(), title=f"Section {part_index + 1}", order_index=part_index
        )
        group = QuestionGroup(
            id=uuid4(),
            question_type="short_answer",
            instruction="Answer",
            config={},
            order_index=part_index,
        )
        for local_index in range(10):
            number = part_index * 10 + local_index + 1
            group.questions.append(
                Question(
                    id=uuid4(),
                    number=number,
                    prompt=f"Question {number}",
                    config={"max_words": 2, "max_numbers": 1},
                    answer_key={
                        "kind": "TEXT",
                        "accepted": [f"answer {number}"],
                        "case_sensitive": False,
                    },
                    order_index=local_index,
                )
            )
        part.question_groups.append(group)
        module.listening_parts.append(part)
        module.question_groups.append(group)
    assert VersionService.validate_version(version).valid


def test_listening_validation_warns_about_missing_parts_and_allows_optional_audio() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.LISTENING, order_index=0)
    module.listening_parts.append(ListeningPart(id=uuid4(), title="Part 1", order_index=0))
    version.modules.append(module)
    result = VersionService.validate_version(version)
    assert not result.valid
    assert any(issue.path == "listening.parts" for issue in result.warnings)
    assert not any(issue.path.endswith(".audio") for issue in result.errors)


def test_partial_listening_with_one_section_and_question_is_publishable() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.LISTENING, order_index=0)
    part = ListeningPart(id=uuid4(), title="Section 1", order_index=0)
    group = QuestionGroup(id=uuid4(), question_type="short_answer", instruction="Answer", config={}, order_index=0)
    group.questions.append(Question(id=uuid4(), number=1, prompt="Prompt", config={"max_words": 2, "max_numbers": 1}, answer_key={"kind": "TEXT", "accepted": ["answer"], "case_sensitive": False}, order_index=0))
    part.question_groups.append(group)
    module.listening_parts.append(part)
    module.question_groups.append(group)
    version.modules.append(module)

    result = VersionService.validate_version(version)

    assert result.valid
    assert not result.errors
    assert any("1 / 4" in issue.message for issue in result.warnings)
    assert any("no audio" in issue.message.lower() for issue in result.warnings)


@pytest.mark.integration
async def test_shared_audio_replace_and_remove_preserves_sections_and_questions(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Shared audio")
    version = VersionRecord(id=uuid4(), version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(id=uuid4(), module_type=ModuleType.LISTENING, order_index=0)
    part = ListeningPart(id=uuid4(), title="Section 1", order_index=0)
    group = QuestionGroup(id=uuid4(), question_type="short_answer", instruction="", config={}, order_index=0)
    group.questions.append(Question(id=uuid4(), number=1, prompt="Prompt", config={"max_words": 2}, answer_key={"kind": "TEXT", "accepted": ["answer"], "case_sensitive": False}, order_index=0))
    part.question_groups.append(group)
    module.listening_parts.append(part)
    module.question_groups.append(group)
    test.versions.append(version)
    version.modules.append(module)
    first = Asset(id=uuid4(), test_version_id=version.id, asset_type=AssetType.LISTENING_AUDIO, relative_path="audio/first.mp3", mime_type="audio/mpeg", original_name="first.mp3", file_size=10)
    second = Asset(id=uuid4(), test_version_id=version.id, asset_type=AssetType.LISTENING_AUDIO, relative_path="audio/second.mp3", mime_type="audio/mpeg", original_name="second.mp3", file_size=10)
    async with db_session.begin():
        db_session.add_all([test, first, second])
        await db_session.flush()

    service = ListeningService(db_session)
    module_id = module.id
    first_id = first.id
    second_id = second.id
    part_id = part.id
    question_id = group.questions[0].id
    await service.attach_audio(module_id, ListeningModuleAudioWrite(asset_id=first_id))
    await db_session.rollback()
    await service.attach_audio(module_id, ListeningModuleAudioWrite(asset_id=second_id))
    await db_session.rollback()
    await service.attach_audio(module_id, ListeningModuleAudioWrite(asset_id=None))
    await db_session.rollback()

    stored_module = await db_session.get(ModuleRecord, module_id)
    assert stored_module is not None and stored_module.audio_asset_id is None
    assert await db_session.get(ListeningPart, part_id) is not None
    assert await db_session.get(Question, question_id) is not None


@pytest.mark.integration
async def test_listening_part_crud_and_group_numbering_use_stable_part_ids(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Listening service")
    version = VersionRecord(id=uuid4(), version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(id=uuid4(), module_type=ModuleType.LISTENING, order_index=0)
    test.versions.append(version)
    version.modules.append(module)
    version_id = version.id
    module_id = module.id
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()

    service = ListeningService(db_session)
    first = await service.create_part(version_id, ListeningPartWrite(title="Part 1", order_index=0))
    first_id = first.id
    await db_session.rollback()
    second = await service.create_part(
        version_id, ListeningPartWrite(title="Part 2", order_index=1)
    )
    second_id = second.id
    await db_session.rollback()
    group_body = QuestionGroupWrite(
        question_type="short_answer",
        instruction="Answer briefly.",
        config={},
        order_index=0,
        questions=[
            {
                "id": uuid4(),
                "number": 99,
                "prompt": "Fictional prompt",
                "config": {"max_words": 2, "max_numbers": 1},
                "answer_key": {
                    "kind": "TEXT",
                    "accepted": ["fictional"],
                    "case_sensitive": False,
                },
                "order_index": 0,
            }
        ],
    )
    created_first = await service.create_group(first_id, group_body)
    await db_session.rollback()
    second_body = group_body.model_copy(
        update={
            "order_index": 1,
            "questions": [group_body.questions[0].model_copy(update={"id": uuid4()})],
        }
    )
    created_second = await service.create_group(second_id, second_body)
    second_group_id = created_second.id
    await db_session.rollback()

    assert created_first.questions[0].number == 1
    assert created_second.questions[0].number == 2
    rows = list(
        (
            await db_session.scalars(
                select(QuestionGroup)
                .where(QuestionGroup.module_id == module_id)
                .order_by(QuestionGroup.order_index)
            )
        ).all()
    )
    assert [row.listening_part_id for row in rows] == [first_id, second_id]

    await db_session.rollback()
    await service.shared.delete_group(second_group_id)
    await db_session.rollback()
    await service.delete_part(second_id)
    await db_session.rollback()
    assert await db_session.get(ListeningPart, second_id) is None
