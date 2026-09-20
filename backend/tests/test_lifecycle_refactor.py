from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import (
    Attempt,
    AttemptAnswer,
    Highlight,
    Question,
    QuestionGroup,
    ReadingPassage,
)
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AttemptStatus, ModuleType, TimerMode, VersionStatus
from app.schemas.attempts import AttemptCreate, TimerRequest
from app.schemas.content import HighlightCreate, ModuleCreate, QuestionGroupWrite, QuestionWrite
from app.schemas.tests import VersionCreate
from app.services.attempts import AttemptService
from app.services.reading import ReadingService
from app.services.tests import TestService as LifecycleService


def add_valid_reading(version: DomainVersion) -> DomainModule:
    module = DomainModule(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional",
        order_index=0,
        content_json=[
            {"id": str(uuid4()), "type": "paragraph", "label": "A", "text": "Meaningful text"}
        ],
        plain_text="Meaningful text",
    )
    group = QuestionGroup(
        question_type="true_false_not_given", instruction="Choose", config={}, order_index=0
    )
    group.questions.append(
        Question(
            number=1,
            prompt="Statement",
            config={},
            answer_key={"kind": "SINGLE_OPTION", "value": "TRUE"},
            order_index=0,
        )
    )
    passage.question_groups.append(group)
    module.passages.append(passage)
    module.question_groups.append(group)
    version.modules.append(module)
    return module


async def persist(session: AsyncSession, *records: object) -> None:
    async with session.begin():
        session.add_all(records)
        await session.flush()


@pytest.mark.integration
async def test_generic_highlights_and_bulk_delete(db_session: AsyncSession) -> None:
    test = DomainTest(title="Highlights")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    test.versions.append(version)
    module = add_valid_reading(version)
    completion_question = Question(
        id=uuid4(),
        number=2,
        prompt="Answer",
        config={"max_words": 2},
        answer_key={"kind": "TEXT", "accepted": ["supports jobs"]},
        order_index=0,
    )
    segment_id = uuid4()
    completion_group = QuestionGroup(
        id=uuid4(),
        question_type="text_completion",
        instruction="Complete",
        order_index=1,
        config={
            "mode": "SENTENCE",
            "blocks": [
                {
                    "id": str(uuid4()),
                    "segments": [
                        {"id": str(segment_id), "type": "TEXT", "text": "Tourism supports jobs"},
                        {
                            "id": str(uuid4()),
                            "type": "GAP",
                            "question_id": str(completion_question.id),
                        },
                    ],
                }
            ],
        },
    )
    completion_group.questions.append(completion_question)
    module.passages[0].question_groups.append(completion_group)
    module.question_groups.append(completion_group)
    heading_option_id = uuid4()
    other_option_id = uuid4()
    target_block_id = module.passages[0].content_json[0]["id"]
    heading_group = QuestionGroup(
        id=uuid4(),
        question_type="matching_headings",
        instruction="Match headings",
        order_index=2,
        config={
            "options": [
                {
                    "id": str(heading_option_id),
                    "label": "i",
                    "text": "Earning foreign exchange through tourism",
                },
                {"id": str(uuid4()), "label": "ii", "text": "Mass tourism"},
            ]
        },
    )
    heading_group.questions.append(
        Question(
            number=3,
            prompt="Paragraph A",
            config={"target_block_id": target_block_id},
            answer_key={"kind": "SINGLE_OPTION", "value": str(heading_option_id)},
            order_index=0,
        )
    )
    other_group = QuestionGroup(
        id=uuid4(),
        question_type="matching_headings",
        instruction="Other headings",
        order_index=3,
        config={
            "options": [
                {"id": str(other_option_id), "label": "i", "text": "Other group option"},
                {"id": str(uuid4()), "label": "ii", "text": "Another option"},
            ]
        },
    )
    other_group.questions.append(
        Question(
            number=4,
            prompt="Paragraph A",
            config={"target_block_id": target_block_id},
            answer_key={"kind": "SINGLE_OPTION", "value": str(other_option_id)},
            order_index=0,
        )
    )
    module.passages[0].question_groups.extend([heading_group, other_group])
    module.question_groups.extend([heading_group, other_group])
    await persist(db_session, test)
    heading_group_id = heading_group.id
    passage = module.passages[0]
    question = passage.question_groups[0].questions[0]
    attempt = await AttemptService(db_session).start(
        AttemptCreate(
            test_version_id=version.id,
            module=ModuleType.READING,
            timer=TimerRequest(mode=TimerMode.COUNT_UP),
        )
    )
    block_id = passage.content_json[0]["id"]
    passage_highlight = await AttemptService(db_session).create_highlight(
        attempt.attempt_id,
        HighlightCreate(
            target_kind="PASSAGE_BLOCK",
            target_id=passage.id,
            segment_id=block_id,
            start_offset=0,
            end_offset=10,
            selected_text="Meaningful",
        ),
    )
    question_highlight = await AttemptService(db_session).create_highlight(
        attempt.attempt_id,
        HighlightCreate(
            target_kind="QUESTION_PROMPT",
            target_id=question.id,
            start_offset=0,
            end_offset=9,
            selected_text="Statement",
        ),
    )
    completion_highlight = await AttemptService(db_session).create_highlight(
        attempt.attempt_id,
        HighlightCreate(
            target_kind="TEXT_COMPLETION_SEGMENT",
            target_id=completion_group.id,
            segment_id=segment_id,
            start_offset=8,
            end_offset=16,
            selected_text="supports",
        ),
    )
    heading_highlight = await AttemptService(db_session).create_highlight(
        attempt.attempt_id,
        HighlightCreate(
            target_kind="QUESTION_GROUP_OPTION",
            target_id=heading_group_id,
            segment_id=heading_option_id,
            start_offset=0,
            end_offset=7,
            selected_text="Earning",
        ),
    )
    assert passage_highlight.target_kind == "PASSAGE_BLOCK"
    assert question_highlight.target_kind == "QUESTION_PROMPT"
    assert completion_highlight.target_kind == "TEXT_COMPLETION_SEGMENT"
    assert heading_highlight.target_kind == "QUESTION_GROUP_OPTION"

    reloaded = await AttemptService(db_session).exam(attempt.attempt_id)
    assert any(item.id == heading_highlight.id for item in reloaded.highlights)
    await db_session.commit()

    with pytest.raises(AppError) as wrong_group:
        await AttemptService(db_session).create_highlight(
            attempt.attempt_id,
            HighlightCreate(
                target_kind="QUESTION_GROUP_OPTION",
                target_id=heading_group_id,
                segment_id=other_option_id,
                start_offset=0,
                end_offset=5,
                selected_text="Other",
            ),
        )
    assert wrong_group.value.code == "INVALID_HIGHLIGHT"

    with pytest.raises(AppError) as wrong_text:
        await AttemptService(db_session).create_highlight(
            attempt.attempt_id,
            HighlightCreate(
                target_kind="QUESTION_GROUP_OPTION",
                target_id=heading_group_id,
                segment_id=heading_option_id,
                start_offset=0,
                end_offset=7,
                selected_text="Foreign",
            ),
        )
    assert wrong_text.value.code == "INVALID_HIGHLIGHT"

    await AttemptService(db_session).delete_highlight(attempt.attempt_id, heading_highlight.id)
    db_session.expire_all()
    after_delete = await AttemptService(db_session).exam(attempt.attempt_id)
    assert all(item.id != heading_highlight.id for item in after_delete.highlights)
    await db_session.commit()

    bulk_heading = await AttemptService(db_session).create_highlight(
        attempt.attempt_id,
        HighlightCreate(
            target_kind="QUESTION_GROUP_OPTION",
            target_id=heading_group_id,
            segment_id=heading_option_id,
            start_offset=8,
            end_offset=15,
            selected_text="foreign",
        ),
    )
    await AttemptService(db_session).delete_all_highlights(attempt.attempt_id)
    remaining = list(
        await db_session.scalars(
            select(Highlight).where(Highlight.attempt_id == attempt.attempt_id)
        )
    )
    assert remaining == []
    assert bulk_heading.id is not None


@pytest.mark.integration
async def test_text_completion_layout_and_answers_round_trip(db_session: AsyncSession) -> None:
    test = DomainTest(title="Text completion")
    version = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(version)
    module = add_valid_reading(version)
    await persist(db_session, test)
    question_id = uuid4()
    block_id = uuid4()
    gap_id = uuid4()
    created = await ReadingService(db_session).create_group(
        module.passages[0].id,
        QuestionGroupWrite(
            question_type="text_completion",
            instruction="",
            order_index=1,
            config={
                "mode": "PASSAGE",
                "blocks": [
                    {
                        "id": str(block_id),
                        "segments": [
                            {"id": str(uuid4()), "type": "TEXT", "text": "Tourism provides "},
                            {"id": str(gap_id), "type": "GAP", "question_id": str(question_id)},
                            {"id": str(uuid4()), "type": "TEXT", "text": "."},
                        ],
                    }
                ],
            },
            questions=[
                QuestionWrite(
                    id=question_id,
                    number=2,
                    prompt="Answer",
                    order_index=0,
                    config={"max_words": 3, "max_numbers": 1},
                    answer_key={
                        "kind": "TEXT",
                        "accepted": ["source, of income", "main source of income"],
                        "case_sensitive": False,
                    },
                )
            ],
        ),
    )

    reloaded = await ReadingService(db_session).get_group(created.id)
    assert reloaded.config["mode"] == "PASSAGE"
    assert reloaded.config["blocks"][0]["segments"][1]["question_id"] == str(question_id)
    assert reloaded.questions[0].id == question_id
    assert reloaded.questions[0].answer_key == {
        "kind": "TEXT",
        "accepted": ["source, of income", "main source of income"],
        "case_sensitive": False,
    }


@pytest.mark.integration
async def test_edit_published_reuses_single_open_draft(db_session: AsyncSession) -> None:
    test = DomainTest(title="Single draft")
    published = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    test.versions.append(published)
    add_valid_reading(published)
    await persist(db_session, test)
    test_id = test.id
    published_id = published.id

    first = await LifecycleService(db_session).create_version(
        test_id, VersionCreate(source_version_id=published_id)
    )
    first_id = first.id
    await db_session.rollback()
    second = await LifecycleService(db_session).create_version(
        test_id, VersionCreate(source_version_id=published_id)
    )

    assert first_id == second.id
    drafts = list(
        await db_session.scalars(
            select(DomainVersion).where(
                DomainVersion.test_id == test_id, DomainVersion.status == VersionStatus.DRAFT
            )
        )
    )
    assert len(drafts) == 1


@pytest.mark.integration
async def test_publish_archives_previous_current_version_and_keeps_history(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Publishing lifecycle")
    previous = DomainVersion(
        version_number=1, status=VersionStatus.PUBLISHED, published_at=datetime.now(UTC)
    )
    draft = DomainVersion(version_number=2, status=VersionStatus.DRAFT)
    test.versions.extend([previous, draft])
    add_valid_reading(previous)
    add_valid_reading(draft)
    old_attempt = Attempt(
        test_version=previous,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
        status=AttemptStatus.IN_PROGRESS,
    )
    await persist(db_session, test, old_attempt)

    await LifecycleService(db_session).publish(draft.id)

    assert (await db_session.get(DomainVersion, previous.id)).status == VersionStatus.ARCHIVED  # type: ignore[union-attr]
    assert (await db_session.get(DomainVersion, draft.id)).status == VersionStatus.PUBLISHED  # type: ignore[union-attr]
    assert (await db_session.get(Attempt, old_attempt.id)).test_version_id == previous.id  # type: ignore[union-attr]


@pytest.mark.integration
async def test_archived_test_blocks_new_attempt_and_restore_allows_it(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Archived", archived_at=datetime.now(UTC))
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    test.versions.append(version)
    add_valid_reading(version)
    await persist(db_session, test)
    test_id = test.id
    version_id = version.id
    request = AttemptCreate(
        test_version_id=version_id,
        module=ModuleType.READING,
        timer=TimerRequest(mode=TimerMode.COUNT_UP),
    )

    with pytest.raises(AppError) as caught:
        await AttemptService(db_session).start(request)
    assert caught.value.code == "TEST_MODULE_UNAVAILABLE"

    await LifecycleService(db_session).restore_test(test_id)
    started = await AttemptService(db_session).start(request)
    assert started.test_version_id == version_id


@pytest.mark.integration
async def test_draft_module_can_be_deleted_and_recreated(db_session: AsyncSession) -> None:
    test = DomainTest(title="Module lifecycle")
    draft = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(draft)
    reading = add_valid_reading(draft)
    listening = DomainModule(module_type=ModuleType.LISTENING, order_index=1)
    draft.modules.append(listening)
    await persist(db_session, test)
    draft_id = draft.id
    reading_id = reading.id
    listening_id = listening.id

    await LifecycleService(db_session).delete_module(reading_id)

    recreated = await ReadingService(db_session).create_module(
        draft_id,
        ModuleCreate(
            module_type=ModuleType.READING, title="Reading", recommended_duration_seconds=3600
        ),
    )
    assert recreated.module_type == ModuleType.READING
    assert await db_session.get(DomainModule, reading_id) is None
    assert await db_session.get(DomainModule, listening_id) is not None


@pytest.mark.integration
async def test_published_module_cannot_be_deleted(db_session: AsyncSession) -> None:
    test = DomainTest(title="Frozen module")
    published = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    test.versions.append(published)
    module = add_valid_reading(published)
    await persist(db_session, test)

    with pytest.raises(AppError) as caught:
        await LifecycleService(db_session).delete_module(module.id)
    assert caught.value.code == "TEST_VERSION_IMMUTABLE"


@pytest.mark.integration
async def test_permanent_delete_requires_archive_and_removes_attempt_dependents(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Permanent")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    test.versions.append(version)
    add_valid_reading(version)
    question = version.modules[0].question_groups[0].questions[0]
    attempt = Attempt(
        test_version=version,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
        status=AttemptStatus.SUBMITTED,
    )
    answer = AttemptAnswer(attempt=attempt, question=question, value="TRUE", is_correct=True)
    await persist(db_session, test, attempt, answer)
    test_id = test.id
    attempt_id = attempt.id
    answer_id = answer.id

    with pytest.raises(AppError) as caught:
        await LifecycleService(db_session).permanently_delete_test(test_id)
    assert caught.value.code == "TEST_NOT_ARCHIVED"
    await db_session.rollback()
    await LifecycleService(db_session).delete_test(test_id)
    await LifecycleService(db_session).permanently_delete_test(test_id)

    assert await db_session.get(DomainTest, test_id) is None
    assert await db_session.get(Attempt, attempt_id) is None
    assert await db_session.get(AttemptAnswer, answer_id) is None


def test_local_asset_storage_delete_rejects_path_traversal(tmp_path) -> None:
    from app.storage.local import LocalAssetStorage

    storage = LocalAssetStorage(tmp_path)
    with pytest.raises(AppError):
        storage.delete("../outside.mp3")
