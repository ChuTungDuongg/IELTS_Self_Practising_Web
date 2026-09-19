from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import (
    Attempt,
    AttemptAnswer,
    Question,
    QuestionGroup,
    ReadingPassage,
)
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AttemptStatus, ModuleType, TimerMode, VersionStatus
from app.schemas.attempts import AttemptCreate, TimerRequest
from app.schemas.content import ModuleCreate
from app.schemas.tests import VersionCreate
from app.services.attempts import AttemptService
from app.services.reading import ReadingService
from app.services.tests import TestService as LifecycleService


def add_valid_reading(version: DomainVersion) -> DomainModule:
    module = DomainModule(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional",
        order_index=0,
        content_json=[{"id": str(uuid4()), "type": "paragraph", "label": "A", "text": "Meaningful text"}],
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
        ModuleCreate(module_type=ModuleType.READING, title="Reading", recommended_duration_seconds=3600),
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
