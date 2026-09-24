from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attempt, AttemptAnswer, Question, QuestionGroup
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AttemptStatus, FinishedReason, ModuleType, TimerMode, VersionStatus
from app.services.analytics import AnalyticsService


@pytest.mark.integration
async def test_analytics_excludes_active_and_null_bands_and_applies_weak_threshold(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    baseline = await AnalyticsService(db_session).dashboard()
    await db_session.rollback()
    test = DomainTest(title="Fictional analytics")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    module = DomainModule(module_type=ModuleType.READING, order_index=0)
    group = QuestionGroup(
        question_type="matching_headings", instruction="", config={}, order_index=0
    )
    group.questions.extend(
        Question(
            number=index + 1,
            prompt=f"Q{index + 1}",
            config={},
            answer_key={"kind": "SINGLE_OPTION", "value": "x"},
            order_index=index,
        )
        for index in range(5)
    )
    module.question_groups.append(group)
    version.modules.append(module)
    test.versions.append(version)
    finalized = Attempt(
        test_version=version,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=now,
        last_active_at=now,
        finished_at=now + timedelta(seconds=100),
        elapsed_seconds=100,
        status=AttemptStatus.SUBMITTED,
        finished_reason=FinishedReason.USER_SUBMIT,
        band_score=Decimal("7.0"),
    )
    active = Attempt(
        test_version=version,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=now,
        last_active_at=now,
        status=AttemptStatus.IN_PROGRESS,
        band_score=Decimal("9.0"),
    )
    finalized.answers.extend(
        AttemptAnswer(question=question, value="x", is_correct=index < 3)
        for index, question in enumerate(group.questions)
    )
    async with db_session.begin():
        db_session.add_all([test, finalized, active])
        await db_session.flush()

    dashboard = await AnalyticsService(db_session).dashboard()
    assert dashboard.total_finalized_attempts == baseline.total_finalized_attempts + 1
    assert dashboard.total_active_seconds == baseline.total_active_seconds + 100
    matching = next(
        item for item in dashboard.question_types if item.question_type == "matching_headings"
    )
    baseline_matching = next(
        (item for item in baseline.question_types if item.question_type == "matching_headings"),
        None,
    )
    assert matching.attempted == (baseline_matching.attempted if baseline_matching else 0) + 5
    assert matching.correct == (baseline_matching.correct if baseline_matching else 0) + 3
    assert any(item.question_type == "matching_headings" for item in dashboard.weak_areas)
