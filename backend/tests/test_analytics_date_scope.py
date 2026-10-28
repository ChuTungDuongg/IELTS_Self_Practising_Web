"""Date-scoped analytics behavior against rollback-only, isolated PostgreSQL."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptEvent,
    Question,
    QuestionGroup,
    User,
)
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestSession as DomainSession
from app.models import TestVersion as DomainVersion
from app.models.enums import (
    AttemptStatus,
    EventType,
    ModuleType,
    TimerMode,
    VersionStatus,
)
from app.models.enums import TestSessionStatus as SessionStatus
from app.services.analytics import AnalyticsService

START = datetime(2026, 10, 1, tzinfo=UTC)
END = datetime(2026, 10, 8, tzinfo=UTC)


def fictional_group(question_type: str) -> QuestionGroup:
    group = QuestionGroup(question_type=question_type, instruction="", config={}, order_index=0)
    group.questions = [
        Question(
            number=index + 1,
            prompt=f"Fictional item {index + 1}",
            config={},
            answer_key={"kind": "SINGLE_OPTION", "value": "x"},
            order_index=index,
        )
        for index in range(5)
    ]
    return group


def fictional_version() -> DomainVersion:
    version = DomainVersion(
        test=DomainTest(title="Fictional analytics date study"),
        version_number=3,
        status=VersionStatus.PUBLISHED,
    )
    module = DomainModule(module_type=ModuleType.READING, order_index=0)
    module.question_groups.append(fictional_group("matching_headings"))
    version.modules.append(module)
    return version


def attempt(
    version: DomainVersion,
    *,
    started_at: datetime = START,
    finished_at: datetime | None = START,
    module: ModuleType = ModuleType.READING,
    status: AttemptStatus = AttemptStatus.SUBMITTED,
    band: str | None = "6.0",
    elapsed: int = 120,
    **kwargs,
) -> Attempt:
    return Attempt(
        test_version=version,
        module_type=module,
        timer_mode=TimerMode.COUNT_UP,
        started_at=started_at,
        last_active_at=started_at,
        finished_at=finished_at,
        elapsed_seconds=elapsed,
        status=status,
        band_score=Decimal(band) if band is not None else None,
        **kwargs,
    )


@pytest.mark.integration
async def test_date_scope_uses_finish_fallback_start_and_owned_active_sessions(
    isolated_db_session: AsyncSession,
):
    session = isolated_db_session
    version = fictional_version()
    other_user = User(email=f"other-{uuid4()}@example.com", display_name="Other learner")
    before = attempt(version, finished_at=START - timedelta(seconds=1), band="9.0", elapsed=900)
    included = attempt(version, started_at=START - timedelta(days=2), finished_at=START)
    fallback = attempt(
        version,
        started_at=START + timedelta(days=1),
        finished_at=None,
        status=AttemptStatus.INTERRUPTED,
        band=None,
        elapsed=20,
    )
    at_end = attempt(version, finished_at=END, band="9.0", elapsed=900)
    active = attempt(
        version,
        started_at=START + timedelta(days=2),
        finished_at=None,
        status=AttemptStatus.IN_PROGRESS,
        band="9.0",
        elapsed=30,
    )
    old_active = attempt(
        version,
        started_at=START - timedelta(days=1),
        finished_at=None,
        status=AttemptStatus.IN_PROGRESS,
        elapsed=900,
    )
    paused = attempt(
        version,
        started_at=START + timedelta(days=3),
        finished_at=None,
        status=AttemptStatus.PAUSED,
        elapsed=40,
    )
    foreign = attempt(version, user=other_user, band="9.0", elapsed=900)
    questions = version.modules[0].question_groups[0].questions
    for row in (included, at_end, foreign):
        row.answers = [
            AttemptAnswer(question=question, value="x", is_correct=index < 3)
            for index, question in enumerate(questions)
        ]
    target_id = uuid4()
    included.events.append(
        AttemptEvent(
            event_type=EventType.PASSAGE_CHANGED,
            created_at=START,
            event_metadata={"target_id": str(target_id), "active_elapsed_seconds": 20},
        )
    )
    async with session.begin():
        session.add_all(
            [
                version,
                other_user,
                before,
                included,
                fallback,
                at_end,
                active,
                old_active,
                paused,
                foreign,
            ]
        )
        await session.flush()

    service = AnalyticsService(session)
    # Offset bounds denote the same instants as START/END and remain half-open.
    dashboard = await service.dashboard(
        start=START.astimezone(timezone(timedelta(hours=7))), end=END
    )
    assert dashboard.total_finalized_attempts == 2
    assert dashboard.total_active_seconds == 210
    assert dashboard.average_attempt_seconds == 52.5
    assert [point.attempt_id for point in dashboard.trends] == [included.id]
    assert dashboard.bands["READING"].average == 6.0
    assert {option.attempt_id for option in dashboard.attempts} == {included.id, fallback.id}
    assert all(
        option.test_title == "Fictional analytics date study" for option in dashboard.attempts
    )
    assert all(
        option.label == "Fictional analytics date study · Reading" for option in dashboard.attempts
    )
    assert dashboard.question_types[0].attempted == 5
    assert dashboard.question_types[0].accuracy == 60.0
    assert dashboard.weak_areas[0].attempted == 5
    assert [
        (row.attempt_id, row.target_id, row.active_seconds) for row in dashboard.content_timing
    ] == [(included.id, target_id, 100)]

    unrestricted = await service.dashboard()
    assert unrestricted.total_finalized_attempts == 4
    assert unrestricted.total_active_seconds == 2910
    assert unrestricted.average_attempt_seconds == 415.7
    assert {row.attempt_id for row in unrestricted.attempts} == {
        before.id,
        included.id,
        fallback.id,
        at_end.id,
    }
    comparison = await service.compare(before.id, at_end.id)
    assert comparison.left.attempt_id == before.id
    assert comparison.right.attempt_id == at_end.id
    lower_only = await service.dashboard(start=START)
    assert {row.attempt_id for row in lower_only.attempts} == {included.id, fallback.id, at_end.id}
    upper_only = await service.dashboard(end=END)
    assert {row.attempt_id for row in upper_only.attempts} == {before.id, included.id, fallback.id}
    empty = await service.dashboard(start=END + timedelta(days=1))
    assert empty.total_finalized_attempts == 0
    assert empty.total_active_seconds == 0
    assert empty.average_attempt_seconds is None
    assert empty.trends == []
    assert empty.question_types == []
    assert empty.weak_areas == []
    assert empty.attempts == []
    assert empty.content_timing == []


@pytest.mark.integration
async def test_skill_filters_details_while_all_skill_bands_and_completed_mocks_use_dates(
    isolated_db_session: AsyncSession,
):
    session = isolated_db_session
    version = fictional_version()
    other_user = User(email=f"mock-other-{uuid4()}@example.com", display_name="Other learner")
    old_mock = DomainSession(
        test_version=version,
        status=SessionStatus.COMPLETED,
        started_at=START - timedelta(days=2),
        finished_at=START - timedelta(seconds=1),
    )
    selected_mock = DomainSession(
        test_version=version,
        status=SessionStatus.COMPLETED,
        started_at=START - timedelta(hours=1),
        finished_at=START + timedelta(hours=2),
        module_order_json=[module.value for module in ModuleType],
    )
    end_mock = DomainSession(
        test_version=version,
        status=SessionStatus.COMPLETED,
        started_at=START,
        finished_at=END,
    )
    foreign_mock = DomainSession(
        test_version=version,
        user=other_user,
        status=SessionStatus.COMPLETED,
        started_at=START,
        finished_at=START + timedelta(days=1),
    )
    active_mock = DomainSession(
        test_version=version,
        status=SessionStatus.IN_PROGRESS,
        started_at=START,
    )
    for module, band in zip(ModuleType, ("6.0", "7.0", "8.0", "9.0"), strict=True):
        selected_mock.attempts.append(
            attempt(version, module=module, band=band, finished_at=START + timedelta(hours=1))
        )
    reading_attempt, listening_attempt = selected_mock.attempts[:2]
    listening_group = fictional_group("matching_information")
    listening_module = DomainModule(module_type=ModuleType.LISTENING, order_index=1)
    listening_module.question_groups.append(listening_group)
    version.modules.append(listening_module)
    for row, group, event_type in (
        (reading_attempt, version.modules[0].question_groups[0], EventType.PASSAGE_CHANGED),
        (listening_attempt, listening_group, EventType.LISTENING_PART_CHANGED),
    ):
        row.answers = [
            AttemptAnswer(question=question, value="x", is_correct=False)
            for question in group.questions
        ]
        row.events.append(
            AttemptEvent(
                event_type=event_type,
                created_at=START,
                event_metadata={"target_id": str(uuid4()), "active_elapsed_seconds": 0},
            )
        )
    # An earlier attempt should not change either latest-band summary or derived overall.
    earlier_reading = attempt(version, module=ModuleType.READING, band="4.0", finished_at=START)
    async with session.begin():
        session.add_all(
            [
                version,
                other_user,
                old_mock,
                selected_mock,
                end_mock,
                foreign_mock,
                active_mock,
                earlier_reading,
            ]
        )
        await session.flush()

    reading = await AnalyticsService(session).dashboard(ModuleType.READING, start=START, end=END)
    assert reading.total_finalized_attempts == 2
    assert reading.total_active_seconds == 240
    assert {point.skill for point in reading.trends} == {ModuleType.READING}
    assert {option.skill for option in reading.attempts} == {ModuleType.READING}
    assert [row.question_type for row in reading.question_types] == ["matching_headings"]
    assert [row.question_type for row in reading.weak_areas] == ["matching_headings"]
    assert [row.attempt_id for row in reading.content_timing] == [reading_attempt.id]
    assert {skill: summary.latest for skill, summary in reading.bands.items()} == {
        "READING": 6.0,
        "LISTENING": 7.0,
        "WRITING": 8.0,
        "SPEAKING": 9.0,
    }
    assert reading.completed_full_mocks == 1
    assert reading.latest_full_mock.session_id == selected_mock.id
    assert reading.latest_full_mock.speaking_band == 9.0
    assert reading.latest_full_mock.overall_band == 7.5
    assert reading.latest_project_overall == 7.5
    listening = await AnalyticsService(session).dashboard(
        ModuleType.LISTENING, start=START, end=END
    )
    assert listening.total_finalized_attempts == 1
    assert [row.question_type for row in listening.question_types] == ["matching_information"]
    assert [row.attempt_id for row in listening.content_timing] == [listening_attempt.id]
    assert listening.completed_full_mocks == reading.completed_full_mocks
    assert listening.latest_project_overall == reading.latest_project_overall
    assert listening.bands == reading.bands
    unrestricted = await AnalyticsService(session).dashboard()
    assert unrestricted.completed_full_mocks == 3

    none = await AnalyticsService(session).dashboard(start=END, end=END + timedelta(days=1))
    assert none.completed_full_mocks == 1
    assert none.latest_full_mock.session_id == end_mock.id
    assert none.latest_project_overall is None
    assert none.trends == []


@pytest.mark.integration
async def test_ungraded_answers_do_not_satisfy_weak_area_minimum(
    isolated_db_session: AsyncSession,
):
    session = isolated_db_session
    version = fictional_version()
    row = attempt(version)
    row.answers = [
        AttemptAnswer(question=question, value="x", is_correct=False if index < 4 else None)
        for index, question in enumerate(version.modules[0].question_groups[0].questions)
    ]
    async with session.begin():
        session.add_all([version, row])
        await session.flush()
    dashboard = await AnalyticsService(session).dashboard()
    assert dashboard.question_types[0].attempted == 4
    assert dashboard.question_types[0].incorrect == 4
    assert dashboard.weak_areas == []
