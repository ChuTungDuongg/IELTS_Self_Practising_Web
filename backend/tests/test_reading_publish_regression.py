from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Test as DomainTest
from app.models import TestVersion as DomainVersion
from app.models.enums import ModuleType, VersionStatus
from app.schemas.content import (
    ModuleCreate,
    PassageUpdate,
    PassageWrite,
    QuestionGroupUpdate,
    QuestionGroupWrite,
    QuestionWrite,
    TextBlock,
)
from app.services.reading import ReadingService
from app.services.tests import TestService as LifecycleService


def truth_group(*, order_index: int, number: int, prompt: str) -> QuestionGroupWrite:
    return QuestionGroupWrite(
        question_type="true_false_not_given",
        instruction="Choose TRUE, FALSE, or NOT GIVEN.",
        config={},
        order_index=order_index,
        questions=[
            QuestionWrite(
                id=uuid4(),
                number=number,
                prompt=prompt,
                config={},
                answer_key={"kind": "SINGLE_OPTION", "value": "TRUE"},
                order_index=0,
            )
        ],
    )


def text_completion_group(*, order_index: int, number: int, question_id=None) -> QuestionGroupWrite:
    resolved_question_id = question_id or uuid4()
    return QuestionGroupWrite(
        question_type="text_completion",
        instruction="Complete the text.",
        config={
            "mode": "SENTENCE",
            "blocks": [
                {
                    "id": str(uuid4()),
                    "segments": [
                        {"id": str(uuid4()), "type": "TEXT", "text": "Answer "},
                        {
                            "id": str(uuid4()),
                            "type": "GAP",
                            "question_id": str(resolved_question_id),
                        },
                    ],
                }
            ],
        },
        order_index=order_index,
        questions=[
            QuestionWrite(
                id=resolved_question_id,
                number=number,
                prompt="Answer",
                config={"max_words": 2, "max_numbers": 1},
                answer_key={
                    "kind": "TEXT",
                    "accepted": ["fictional answer"],
                    "case_sensitive": False,
                },
                order_index=0,
            )
        ],
    )


async def create_reading_draft(db_session: AsyncSession) -> tuple[ReadingService, UUID]:
    test = DomainTest(title="Reading publish regression")
    version = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(version)
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
        version_id = version.id

    service = ReadingService(db_session)
    await service.create_module(
        version_id,
        ModuleCreate(module_type=ModuleType.READING, title="Reading"),
    )
    await db_session.rollback()
    return service, version_id


async def add_passage(service: ReadingService, version_id, *, title: str, order_index: int):
    passage = await service.create_passage(
        version_id,
        PassageWrite(
            title=title,
            order_index=order_index,
            blocks=[
                TextBlock(
                    id=uuid4(),
                    type="paragraph",
                    label="A",
                    text=f"Fictional content for {title}.",
                )
            ],
        ),
    )
    await service.session.rollback()
    return passage


async def add_group(service: ReadingService, passage_id, body: QuestionGroupWrite):
    group = await service.create_group(passage_id, body)
    await service.session.rollback()
    return group


@pytest.mark.integration
async def test_adding_a_second_passage_remains_publishable(db_session: AsyncSession) -> None:
    reading, version_id = await create_reading_draft(db_session)
    first = await add_passage(reading, version_id, title="Passage 1", order_index=0)
    await add_group(
        reading,
        first.id,
        truth_group(order_index=0, number=1, prompt="Passage one statement."),
    )

    second = await add_passage(reading, version_id, title="Passage 2", order_index=1)
    await add_group(
        reading,
        second.id,
        truth_group(order_index=1, number=2, prompt="Passage two statement."),
    )

    db_session.expire_all()
    reloaded = await reading.builder_version(version_id)
    assert [
        group.questions[0].number
        for passage in reloaded.modules[0].passages
        for group in passage.question_groups
    ] == [1, 2]

    validation = await LifecycleService(db_session).validate(version_id)
    assert validation.valid, [(issue.path, issue.message) for issue in validation.errors]
    await db_session.rollback()

    published = await LifecycleService(db_session).publish(version_id)
    assert published.status == VersionStatus.PUBLISHED


@pytest.mark.integration
async def test_adding_a_group_to_an_earlier_passage_recanonicalizes_module(
    db_session: AsyncSession,
) -> None:
    reading, version_id = await create_reading_draft(db_session)
    first = await add_passage(reading, version_id, title="Passage 1", order_index=0)
    second = await add_passage(reading, version_id, title="Passage 2", order_index=1)
    first_group = await add_group(
        reading,
        first.id,
        truth_group(order_index=0, number=1, prompt="First passage, first group."),
    )
    second_group = await add_group(
        reading,
        second.id,
        truth_group(order_index=1, number=2, prompt="Second passage group."),
    )

    inserted = await add_group(
        reading,
        first.id,
        truth_group(order_index=2, number=3, prompt="First passage, appended group."),
    )

    db_session.expire_all()
    reloaded = await reading.builder_version(version_id)
    passages = reloaded.modules[0].passages
    assert [group.id for group in passages[0].question_groups] == [first_group.id, inserted.id]
    assert [group.id for group in passages[1].question_groups] == [second_group.id]
    assert [
        question.number
        for passage in passages
        for group in passage.question_groups
        for question in group.questions
    ] == [1, 2, 3]

    validation = await LifecycleService(db_session).validate(version_id)
    assert validation.valid, [(issue.path, issue.message) for issue in validation.errors]
    await db_session.rollback()
    published = await LifecycleService(db_session).publish(version_id)
    assert published.status == VersionStatus.PUBLISHED


@pytest.mark.integration
async def test_new_text_completion_gap_keeps_its_question_uuid_after_reload(
    db_session: AsyncSession,
) -> None:
    reading, version_id = await create_reading_draft(db_session)
    first = await add_passage(reading, version_id, title="Passage 1", order_index=0)
    second = await add_passage(reading, version_id, title="Passage 2", order_index=1)
    completion = await add_group(
        reading,
        first.id,
        text_completion_group(order_index=0, number=1),
    )
    await add_group(
        reading,
        second.id,
        truth_group(order_index=1, number=2, prompt="Passage two statement."),
    )

    existing = completion.questions[0]
    new_question_id = uuid4()
    await reading.update_group(
        completion.id,
        QuestionGroupUpdate(
            expected_revision=completion.revision,
            question_type="text_completion",
            instruction=completion.instruction,
            config={
                "mode": "SENTENCE",
                "blocks": [
                    {
                        "id": str(uuid4()),
                        "segments": [
                            {"id": str(uuid4()), "type": "TEXT", "text": "First "},
                            {
                                "id": str(uuid4()),
                                "type": "GAP",
                                "question_id": str(existing.id),
                            },
                            {"id": str(uuid4()), "type": "TEXT", "text": " second "},
                            {
                                "id": str(uuid4()),
                                "type": "GAP",
                                "question_id": str(new_question_id),
                            },
                        ],
                    }
                ],
            },
            order_index=completion.order_index,
            questions=[
                QuestionWrite(
                    id=existing.id,
                    number=1,
                    prompt=existing.prompt,
                    config=existing.config,
                    answer_key=existing.answer_key,
                    order_index=0,
                ),
                QuestionWrite(
                    id=new_question_id,
                    # This is the canonical position inside Passage 1 but overlaps
                    # Passage 2's stale displayed Q2 until the module is renumbered.
                    number=2,
                    prompt="Second answer",
                    config={"max_words": 2, "max_numbers": 1},
                    answer_key={
                        "kind": "TEXT",
                        "accepted": ["second fictional answer"],
                        "case_sensitive": False,
                    },
                    order_index=1,
                ),
            ],
        ),
    )
    await db_session.rollback()

    db_session.expire_all()
    reloaded = await reading.builder_version(version_id)
    reloaded_completion = reloaded.modules[0].passages[0].question_groups[0]
    gap_question_ids = [
        segment["question_id"]
        for block in reloaded_completion.config["blocks"]
        for segment in block["segments"]
        if segment["type"] == "GAP"
    ]
    validation = await LifecycleService(db_session).validate(version_id)
    assert validation.valid, [(issue.path, issue.message) for issue in validation.errors]
    assert [str(question.id) for question in reloaded_completion.questions] == gap_question_ids
    assert [question.number for question in reloaded_completion.questions] == [1, 2]
    assert reloaded.modules[0].passages[1].question_groups[0].questions[0].number == 3
    await db_session.rollback()

    published = await LifecycleService(db_session).publish(version_id)
    assert published.status == VersionStatus.PUBLISHED


@pytest.mark.integration
async def test_matching_heading_target_remains_owned_by_its_passage(
    db_session: AsyncSession,
) -> None:
    reading, version_id = await create_reading_draft(db_session)
    first = await add_passage(reading, version_id, title="Passage 1", order_index=0)
    target_block_id = first.blocks[0].id
    first_heading_id = uuid4()
    matching = QuestionGroupWrite(
        question_type="matching_headings",
        instruction="Choose a heading.",
        config={
            "options": [
                {"id": str(first_heading_id), "label": "i", "text": "First heading"},
                {"id": str(uuid4()), "label": "ii", "text": "Second heading"},
            ],
            "allow_option_reuse": False,
        },
        order_index=0,
        questions=[
            QuestionWrite(
                id=uuid4(),
                number=1,
                prompt="Choose a heading for paragraph A.",
                config={"target_block_id": str(target_block_id)},
                answer_key={"kind": "SINGLE_OPTION", "value": str(first_heading_id)},
                order_index=0,
            )
        ],
    )
    created = await add_group(reading, first.id, matching)
    second = await add_passage(reading, version_id, title="Passage 2", order_index=1)
    await add_group(
        reading,
        second.id,
        truth_group(order_index=1, number=2, prompt="Passage two statement."),
    )

    db_session.expire_all()
    reloaded = await reading.builder_version(version_id)
    reloaded_matching = reloaded.modules[0].passages[0].question_groups[0]
    assert reloaded_matching.id == created.id
    assert reloaded_matching.questions[0].config["target_block_id"] == str(target_block_id)
    assert reloaded.modules[0].passages[1].question_groups[0].id != created.id

    validation = await LifecycleService(db_session).validate(version_id)
    assert validation.valid, [(issue.path, issue.message) for issue in validation.errors]


@pytest.mark.integration
async def test_stale_matching_heading_target_still_blocks_publish(
    db_session: AsyncSession,
) -> None:
    reading, version_id = await create_reading_draft(db_session)
    passage = await add_passage(reading, version_id, title="Passage 1", order_index=0)
    stale_block_id = passage.blocks[0].id
    heading_id = uuid4()
    await add_group(
        reading,
        passage.id,
        QuestionGroupWrite(
            question_type="matching_headings",
            instruction="Choose a heading.",
            config={
                "options": [
                    {"id": str(heading_id), "label": "i", "text": "First heading"},
                    {"id": str(uuid4()), "label": "ii", "text": "Second heading"},
                ]
            },
            order_index=0,
            questions=[
                QuestionWrite(
                    id=uuid4(),
                    number=1,
                    prompt="Choose a heading.",
                    config={"target_block_id": str(stale_block_id)},
                    answer_key={"kind": "SINGLE_OPTION", "value": str(heading_id)},
                    order_index=0,
                )
            ],
        ),
    )
    await reading.update_passage(
        passage.id,
        PassageUpdate(
            expected_revision=passage.revision,
            title=passage.title,
            order_index=passage.order_index,
            blocks=[
                TextBlock(
                    id=uuid4(),
                    type="paragraph",
                    label="A",
                    text="Replacement fictional paragraph.",
                )
            ],
        ),
    )
    await db_session.rollback()

    validation = await LifecycleService(db_session).validate(version_id)
    assert not validation.valid
    assert any("available block" in issue.message for issue in validation.errors)
