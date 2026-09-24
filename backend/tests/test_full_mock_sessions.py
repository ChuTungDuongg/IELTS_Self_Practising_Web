import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
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
