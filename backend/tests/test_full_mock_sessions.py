import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domains.questions.numbering import group_slots
from app.models import Question, QuestionGroup
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AttemptStatus, ModuleType, VersionStatus
from app.models.enums import TestSessionStatus as SessionStatus
from app.services.attempts import AttemptService
from app.services.test_sessions import TestSessionService as SessionService


def _published_full_test() -> DomainTest:
    test = DomainTest(title="Fictional Full Mock")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    version.modules.extend(
        DomainModule(
            module_type=module,
            order_index=index,
            recommended_duration_seconds=2400 if module == ModuleType.LISTENING else 3600,
        )
        for index, module in enumerate(
            (ModuleType.LISTENING, ModuleType.READING, ModuleType.WRITING)
        )
    )
    test.versions.append(version)
    return test


def _add_numbered_questions(module: DomainModule, singles: int, spans: tuple[int, ...]) -> None:
    number = 1
    if singles:
        group = QuestionGroup(
            question_type="short_answer", instruction="Answer briefly.", config={}, order_index=0
        )
        for index in range(singles):
            group.questions.append(
                Question(
                    number=number,
                    prompt=f"Fictional question {index + 1}",
                    config={"max_words": 2, "max_numbers": 0},
                    answer_key={"kind": "TEXT", "accepted": ["fixture"]},
                    order_index=index,
                )
            )
            number += 1
        module.question_groups.append(group)
    for index, span in enumerate(spans):
        group = QuestionGroup(
            question_type="multiple_choice_multiple",
            instruction=f"Choose {span} letters.",
            config={},
            order_index=index + 1,
        )
        group.questions.append(
            Question(
                number=number,
                prompt="Choose fictional options.",
                config={"min_selections": span, "max_selections": span},
                answer_key={"kind": "MULTIPLE_OPTIONS", "values": []},
                order_index=0,
            )
        )
        module.question_groups.append(group)
        number += span


@pytest.mark.parametrize(
    ("singles", "spans", "physical_rows", "canonical_slots"),
    [
        (40, (), 40, 40),
        (38, (2,), 39, 40),
        (30, (2, 2, 2, 2, 2), 35, 40),
        (37, (3,), 38, 40),
        (39, (), 39, 39),
    ],
)
def test_full_mock_question_slots_not_physical_rows(
    singles: int, spans: tuple[int, ...], physical_rows: int, canonical_slots: int
) -> None:
    module = DomainModule(module_type=ModuleType.READING, order_index=0)
    _add_numbered_questions(module, singles, spans)
    assert sum(len(group.questions) for group in module.question_groups) == physical_rows
    assert (
        sum(
            len(group_slots(group.question_type, group.questions))
            for group in module.question_groups
        )
        == canonical_slots
    )


@pytest.mark.integration
async def test_full_mock_response_uses_canonical_40_slots_for_both_skills(
    db_session: AsyncSession,
) -> None:
    test = _published_full_test()
    version = test.versions[0]
    modules = {module.module_type: module for module in version.modules}
    _add_numbered_questions(modules[ModuleType.LISTENING], 30, (2, 2, 2, 2, 2))
    _add_numbered_questions(modules[ModuleType.READING], 38, (2,))
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
        version_id = version.id

    response = await SessionService(db_session).start(version_id)
    assert response.session.warnings == []


@pytest.mark.integration
async def test_full_mock_response_still_warns_for_genuine_39_slots(
    db_session: AsyncSession,
) -> None:
    test = _published_full_test()
    version = test.versions[0]
    modules = {module.module_type: module for module in version.modules}
    _add_numbered_questions(modules[ModuleType.LISTENING], 40, ())
    _add_numbered_questions(modules[ModuleType.READING], 39, ())
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
        version_id = version.id

    response = await SessionService(db_session).start(version_id)
    assert response.session.warnings == [
        "Reading has 39 questions. An official band will not be calculated."
    ]


@pytest.mark.integration
async def test_full_mock_lazily_creates_attempts_locks_review_and_completes(
    db_session: AsyncSession,
) -> None:
    test = _published_full_test()
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
        version_id = test.versions[0].id

    started = await SessionService(db_session).start(version_id)
    listening = started.current_attempt
    assert listening.module == ModuleType.LISTENING
    assert listening.timer_limit_seconds == 2400
    assert listening.test_session_id == started.session.session_id
    assert len(started.session.attempts) == 1

    await AttemptService(db_session).submit(listening.attempt_id)
    with pytest.raises(AppError, match="Module review"):
        await AttemptService(db_session).review(listening.attempt_id)
    await db_session.rollback()

    reading_session = await SessionService(db_session).advance(started.session.session_id)
    assert reading_session.current_attempt is not None
    assert reading_session.current_attempt.module == ModuleType.READING
    assert len(reading_session.attempts) == 2
    await AttemptService(db_session).submit(reading_session.current_attempt.attempt_id)

    writing_session = await SessionService(db_session).advance(started.session.session_id)
    assert writing_session.current_attempt is not None
    assert writing_session.current_attempt.module == ModuleType.WRITING
    await AttemptService(db_session).submit(writing_session.current_attempt.attempt_id)

    completed = await SessionService(db_session).get(started.session.session_id)
    assert completed.status == SessionStatus.COMPLETED
    assert completed.finished_at is not None
    assert len(completed.attempts) == 3
    review = await AttemptService(db_session).review(listening.attempt_id)
    assert review.attempt.status == AttemptStatus.SUBMITTED


@pytest.mark.integration
async def test_full_mock_requires_all_modules_and_durations(db_session: AsyncSession) -> None:
    test = DomainTest(title="Incomplete fictional mock")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    version.modules.append(
        DomainModule(
            module_type=ModuleType.LISTENING,
            order_index=0,
            recommended_duration_seconds=2400,
        )
    )
    test.versions.append(version)
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
        version_id = version.id
    with pytest.raises(AppError, match="module is missing"):
        await SessionService(db_session).start(version_id)
