from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attempt, AttemptAnswer, Question, QuestionGroup, ReadingPassage
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AttemptStatus, FinishedReason, ModuleType, TimerMode, VersionStatus
from app.services.attempts import AttemptService


def _objective_version(*, status: VersionStatus = VersionStatus.PUBLISHED) -> DomainVersion:
    version = DomainVersion(version_number=1, status=status)
    module = DomainModule(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional scoring passage",
        order_index=0,
        content_json=[
            {
                "id": str(uuid4()),
                "type": "paragraph",
                "label": "A",
                "text": "Fictional passage text.",
            }
        ],
        plain_text="Fictional passage text.",
    )
    group = QuestionGroup(
        question_type="short_answer",
        instruction="Answer briefly.",
        config={},
        order_index=0,
    )
    for index in range(40):
        group.questions.append(
            Question(
                number=index + 1,
                prompt=f"Fictional question {index + 1}",
                config={"max_words": 2, "max_numbers": 0},
                answer_key={
                    "kind": "TEXT",
                    "accepted": [f"answer {index + 1}"],
                    "case_sensitive": False,
                },
                order_index=index,
            )
        )
    passage.question_groups.append(group)
    module.passages.append(passage)
    module.question_groups.append(group)
    version.modules.append(module)
    return version


def _attempt(
    version: DomainVersion,
    *,
    module: ModuleType,
    started_at: datetime,
    status: AttemptStatus = AttemptStatus.SUBMITTED,
    band_score: Decimal | None = None,
) -> Attempt:
    finalized = status not in {AttemptStatus.IN_PROGRESS, AttemptStatus.PAUSED}
    return Attempt(
        test_version=version,
        module_type=module,
        timer_mode=TimerMode.COUNT_UP,
        started_at=started_at,
        last_active_at=started_at,
        finished_at=started_at + timedelta(minutes=1) if finalized else None,
        elapsed_seconds=60 if finalized else None,
        status=status,
        finished_reason=FinishedReason.USER_SUBMIT if finalized else None,
        band_score=band_score,
    )


@pytest.mark.integration
async def test_submit_writes_band_and_serializes_it_to_review_and_history(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    test = DomainTest(title="Fictional band test")
    version = _objective_version()
    test.versions.append(version)
    attempt = _attempt(
        version,
        module=ModuleType.READING,
        started_at=now,
        status=AttemptStatus.IN_PROGRESS,
    )
    async with db_session.begin():
        db_session.add_all([test, attempt])
        await db_session.flush()
        questions = version.modules[0].question_groups[0].questions
        db_session.add_all(
            AttemptAnswer(
                attempt=attempt,
                question=question,
                value=f"answer {question.number}",
                is_correct=True,
            )
            for question in questions[:35]
        )
        await db_session.flush()

    response = await AttemptService(db_session).submit(attempt.id)
    review = await AttemptService(db_session).review(attempt.id)
    history = await AttemptService(db_session).history()

    assert (response.raw_score, response.max_score, response.band_score) == (35, 40, 8.0)
    assert review.attempt.band_score == 8.0
    item = next(row for row in history.items if row.attempt_id == attempt.id)
    assert item.test_id == test.id
    assert item.test_version_id == version.id
    assert item.band_score == 8.0


@pytest.mark.integration
async def test_timer_expiry_scores_objective_attempt_before_finalizing(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    test = DomainTest(title="Fictional expired band test")
    version = _objective_version()
    test.versions.append(version)
    attempt = Attempt(
        test_version=version,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNTDOWN,
        timer_limit_seconds=2400,
        started_at=now - timedelta(seconds=2401),
        last_active_at=now,
        status=AttemptStatus.IN_PROGRESS,
    )
    async with db_session.begin():
        db_session.add_all([test, attempt])
        await db_session.flush()
        db_session.add_all(
            AttemptAnswer(
                attempt=attempt,
                question=question,
                value=f"answer {question.number}",
                is_correct=True,
            )
            for question in version.modules[0].question_groups[0].questions[:30]
        )
        await db_session.flush()

    response = await AttemptService(db_session).get(attempt.id)

    assert response.status == AttemptStatus.AUTO_SUBMITTED
    assert (response.raw_score, response.max_score, response.band_score) == (30, 40, 7.0)


@pytest.mark.integration
async def test_writing_scoring_clears_all_objective_score_fields(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    test = DomainTest(title="Fictional Writing score test")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    version.modules.append(DomainModule(module_type=ModuleType.WRITING, order_index=0))
    test.versions.append(version)
    attempt = _attempt(
        version,
        module=ModuleType.WRITING,
        started_at=now,
        status=AttemptStatus.IN_PROGRESS,
    )
    attempt.raw_score = 10
    attempt.max_score = 40
    attempt.band_score = Decimal("4.0")
    async with db_session.begin():
        db_session.add_all([test, attempt])
        await db_session.flush()
        await AttemptService(db_session)._score(attempt)

    assert attempt.raw_score is None
    assert attempt.max_score is None
    assert attempt.band_score is None


@pytest.mark.integration
async def test_history_groups_exact_versions_and_uses_latest_finalized_attempt_per_skill(
    db_session: AsyncSession,
) -> None:
    base = datetime(2026, 9, 20, 1, tzinfo=UTC)
    test = DomainTest(title="Fictional grouped history")
    first = DomainVersion(version_number=1, status=VersionStatus.ARCHIVED)
    second = DomainVersion(version_number=2, status=VersionStatus.PUBLISHED)
    for version in (first, second):
        version.modules.extend(
            DomainModule(module_type=module, order_index=index)
            for index, module in enumerate(
                (ModuleType.READING, ModuleType.LISTENING, ModuleType.WRITING)
            )
        )
    test.versions.extend([first, second])
    older_reading = _attempt(
        first,
        module=ModuleType.READING,
        started_at=base,
        band_score=Decimal("6.0"),
    )
    latest_reading = _attempt(
        first,
        module=ModuleType.READING,
        started_at=base + timedelta(hours=1),
        band_score=Decimal("7.0"),
    )
    listening = _attempt(
        first,
        module=ModuleType.LISTENING,
        started_at=base + timedelta(hours=2),
        band_score=Decimal("7.5"),
    )
    writing = _attempt(
        first,
        module=ModuleType.WRITING,
        started_at=base + timedelta(hours=3),
        band_score=Decimal("6.5"),
    )
    active_reading = _attempt(
        first,
        module=ModuleType.READING,
        started_at=base + timedelta(hours=4),
        status=AttemptStatus.IN_PROGRESS,
        band_score=Decimal("9.0"),
    )
    paused_reading = _attempt(
        first,
        module=ModuleType.READING,
        started_at=base + timedelta(hours=4, minutes=30),
        status=AttemptStatus.PAUSED,
        band_score=Decimal("9.0"),
    )
    paused_reading.paused_at = base + timedelta(hours=4, minutes=31)
    second_version_reading = _attempt(
        second,
        module=ModuleType.READING,
        started_at=base + timedelta(hours=5),
        band_score=Decimal("8.0"),
    )
    attempts = [
        older_reading,
        latest_reading,
        listening,
        writing,
        active_reading,
        paused_reading,
        second_version_reading,
    ]
    async with db_session.begin():
        db_session.add_all([test, *attempts])
        await db_session.flush()

    history = await AttemptService(db_session).history()

    assert {attempt.id for attempt in attempts}.issubset(
        {item.attempt_id for item in history.items}
    )
    test_groups = [group for group in history.groups if group.test_id == test.id]
    assert len(test_groups) == 2
    first_group = next(group for group in test_groups if group.test_version_id == first.id)
    second_group = next(group for group in test_groups if group.test_version_id == second.id)
    assert first_group.test_id == test.id
    assert first_group.reading is not None
    assert first_group.reading.attempt_id == latest_reading.id
    assert first_group.listening is not None
    assert first_group.writing is not None
    assert first_group.overall_band_score == 7.0
    assert second_group.reading is not None
    assert second_group.reading.attempt_id == second_version_reading.id
    assert second_group.listening is None
    assert second_group.writing is None
    assert second_group.overall_band_score is None
