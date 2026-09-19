from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.questions.normalization import normalize_question_group_payload
from app.models import Question, QuestionGroup
from app.models import Test as DomainTest
from app.models import TestModule as ModuleRecord
from app.models import TestVersion as VersionRecord
from app.models.enums import ModuleType, VersionStatus
from app.schemas.content import ListeningPartWrite, ModuleCreate, PassageWrite, QuestionGroupWrite
from app.services.listening import ListeningService
from app.services.reading import ReadingService
from app.services.tests import TestService as LifecycleService


def completion_body(count=2):
    questions = [
        dict(
            id=str(uuid4()),
            number=index + 11,
            order_index=index,
            prompt="Fictional answer",
            config={"max_words": 3, "max_numbers": 2},
            answer_key={
                "kind": "TEXT",
                "accepted": ["fictional", "alternate"],
                "case_sensitive": True,
            },
        )
        for index in range(count)
    ]
    blocks = [
        dict(
            id=str(uuid4()),
            segments=[
                dict(id=str(uuid4()), type="TEXT", text="Fictional sentence "),
                dict(id=str(uuid4()), type="GAP", question_id=question["id"]),
            ],
        )
        for question in questions
    ]
    return QuestionGroupWrite(
        question_type="text_completion",
        instruction="Author instruction",
        config={"mode": "SENTENCE", "blocks": blocks},
        order_index=0,
        questions=questions,
    )


def assert_links(group, body):
    assert [question.id for question in group.questions] == [
        question.id for question in body.questions
    ]
    assert group.config == body.config
    for actual, expected in zip(group.questions, body.questions, strict=True):
        assert actual.config == expected.config
        assert actual.answer_key == expected.answer_key
    assert {str(question.id) for question in group.questions} == {
        segment["question_id"]
        for block in group.config["blocks"]
        for segment in block["segments"]
        if segment["type"] == "GAP"
    }


def test_modern_normalization_preserves_all_identity_and_answer_fields():
    body = completion_body()
    questions = [question.model_dump(mode="json") for question in body.questions]
    config, normalized = normalize_question_group_payload(
        question_type=body.question_type,
        group_config=body.config,
        questions=questions,
        group_id=uuid4(),
        passage_blocks=[],
    )
    assert config == body.config
    assert normalized == questions


@pytest.mark.integration
@pytest.mark.parametrize("kind", [ModuleType.READING, ModuleType.LISTENING])
async def test_completion_create_update_refetch_preserves_identity(db_session: AsyncSession, kind):
    test = DomainTest(title="Fictional completion identity regression")
    version = VersionRecord(id=uuid4(), version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(version)
    version_id = version.id
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
    reading = ReadingService(db_session)
    await reading.create_module(version_id, ModuleCreate(module_type=kind))
    await db_session.rollback()
    service = reading if kind == ModuleType.READING else ListeningService(db_session)
    if kind == ModuleType.READING:
        container = await reading.create_passage(
            version_id,
            PassageWrite(
                title="Fictional passage",
                order_index=0,
                blocks=[dict(id=uuid4(), type="paragraph", text="Fictional passage text.")],
            ),
        )
    else:
        container = await service.create_part(
            version_id, ListeningPartWrite(title="Fictional part", order_index=0)
        )
    await db_session.rollback()
    body = completion_body(1)
    created = await service.create_group(container.id, body)
    assert_links(created, body)
    await db_session.rollback()
    addition = completion_body(1)
    addition.questions[0].number = 12
    addition.questions[0].order_index = 1
    body.questions += addition.questions
    body.config["blocks"] += addition.config["blocks"]
    updated = await service.update_group(created.id, body)
    assert_links(updated, body)
    await db_session.rollback()
    db_session.expire_all()
    reloaded = await service.get_group(created.id)
    assert_links(reloaded, body)
    await db_session.rollback()
    body.config["blocks"].reverse()
    body.questions.reverse()
    for index, question in enumerate(body.questions):
        question.number = index + 1
        question.order_index = index
    assert_links(await service.update_group(created.id, body), body)


def test_version_clone_remaps_gaps_without_touching_source():
    body = completion_body()
    source = VersionRecord(version_number=1, status=VersionStatus.PUBLISHED, modules=[])
    module = ModuleRecord(
        module_type=ModuleType.READING,
        order_index=0,
        passages=[],
        listening_parts=[],
        writing_tasks=[],
        question_groups=[],
    )
    source.modules.append(module)
    group = QuestionGroup(
        id=uuid4(),
        question_type=body.question_type,
        config=deepcopy(body.config),
        instruction=body.instruction,
        order_index=0,
        questions=[],
    )
    module.question_groups.append(group)
    for question in body.questions:
        group.questions.append(Question(**question.model_dump()))
    target = VersionRecord(version_number=2, status=VersionStatus.DRAFT, modules=[])
    LifecycleService._clone_content(source, target)
    cloned = target.modules[0].question_groups[0]
    assert group.config == body.config
    assert {question.id for question in cloned.questions}.isdisjoint(
        {question.id for question in group.questions}
    )
    assert {str(question.id) for question in cloned.questions} == {
        segment["question_id"]
        for block in cloned.config["blocks"]
        for segment in block["segments"]
        if segment["type"] == "GAP"
    }
    assert [question.answer_key for question in cloned.questions] == [
        question.answer_key for question in group.questions
    ]


def test_empty_modern_layout_is_not_rebuilt_as_legacy_content():
    body = completion_body()
    config = {"mode": "SENTENCE", "blocks": []}
    questions = [question.model_dump(mode="json") for question in body.questions]
    normalized, normalized_questions = normalize_question_group_payload(
        question_type="text_completion",
        group_config=config,
        questions=questions,
        group_id=uuid4(),
        passage_blocks=[],
    )
    assert normalized == config
    assert normalized_questions == questions
    with pytest.raises(ValueError):
        from app.domains.questions.registry import question_registry

        question_registry.validate_group("text_completion", normalized)
