from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import AppError
from app.main import app
from app.models import (
    Asset,
    Attempt,
    AttemptAnswer,
    ListeningPart,
    Question,
    QuestionGroup,
    ReadingPassage,
)
from app.models import (
    Test as DomainTest,
)
from app.models import (
    TestModule as DomainModule,
)
from app.models import (
    TestVersion as DomainVersion,
)
from app.models.enums import (
    AssetType,
    AttemptStatus,
    ModuleType,
    TimerMode,
    VersionStatus,
)
from app.services.tests import TestService as LifecycleService


async def persist(session: AsyncSession, *records: object) -> None:
    async with session.begin():
        session.add_all(records)
        await session.flush()


def draft_content(
    version: DomainVersion,
) -> tuple[DomainModule, ReadingPassage, QuestionGroup, Question]:
    module = DomainModule(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional passage",
        order_index=0,
        content_json=[],
        plain_text="",
    )
    group = QuestionGroup(
        question_type="multiple_choice",
        instruction="Choose one.",
        config={},
        order_index=0,
    )
    question = Question(
        number=1,
        prompt="Fictional question",
        config={"options": []},
        answer_key={"kind": "SINGLE_OPTION", "value": str(uuid4())},
        order_index=0,
    )
    version.modules.append(module)
    module.passages.append(passage)
    module.question_groups.append(group)
    passage.question_groups.append(group)
    group.questions.append(question)
    return module, passage, group, question


@pytest.mark.integration
async def test_delete_draft_removes_owned_children_and_keeps_other_version(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Draft lifecycle")
    deleted_version = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    surviving_version = DomainVersion(version_number=2, status=VersionStatus.ARCHIVED)
    test.versions.extend([deleted_version, surviving_version])
    module, passage, group, question = draft_content(deleted_version)
    await persist(db_session, test)

    await LifecycleService(db_session).delete_draft(test.id, deleted_version.id)

    assert await db_session.get(DomainVersion, deleted_version.id) is None
    assert await db_session.get(DomainModule, module.id) is None
    assert await db_session.get(ReadingPassage, passage.id) is None
    assert await db_session.get(QuestionGroup, group.id) is None
    assert await db_session.get(Question, question.id) is None
    assert await db_session.get(DomainVersion, surviving_version.id) is not None


@pytest.mark.integration
async def test_delete_only_draft_removes_empty_test(db_session: AsyncSession) -> None:
    test = DomainTest(title="Only draft")
    draft = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(draft)
    await persist(db_session, test)
    test_id = test.id
    draft_id = draft.id

    await LifecycleService(db_session).delete_draft(test_id, draft_id)

    assert await db_session.get(DomainVersion, draft_id) is None
    assert await db_session.get(DomainTest, test_id) is None


@pytest.mark.integration
async def test_delete_draft_rejects_published_and_wrong_test_versions(
    db_session: AsyncSession,
) -> None:
    first = DomainTest(title="First")
    published = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    first.versions.append(published)
    second = DomainTest(title="Second")
    other_draft = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    second.versions.append(other_draft)
    await persist(db_session, first, second)
    service = LifecycleService(db_session)
    first_id = first.id
    published_id = published.id
    other_draft_id = other_draft.id

    with pytest.raises(AppError) as published_error:
        await service.delete_draft(first_id, published_id)
    assert published_error.value.code == "VERSION_NOT_DRAFT"

    with pytest.raises(AppError) as wrong_test_error:
        await service.delete_draft(first_id, other_draft_id)
    assert wrong_test_error.value.code == "VERSION_NOT_FOUND"
    assert await db_session.get(DomainVersion, other_draft_id) is not None


@pytest.mark.integration
async def test_delete_draft_rejects_unexpected_attempt_history(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Protected draft")
    draft = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(draft)
    now = datetime.now(UTC)
    attempt = Attempt(
        test_version=draft,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=now,
        last_active_at=now,
        status=AttemptStatus.IN_PROGRESS,
    )
    await persist(db_session, test, attempt)
    test_id = test.id
    draft_id = draft.id

    with pytest.raises(AppError) as caught:
        await LifecycleService(db_session).delete_draft(test_id, draft_id)

    assert caught.value.code == "DELETE_CONFLICT"
    assert await db_session.get(DomainVersion, draft_id) is not None


@pytest.mark.integration
async def test_delete_draft_preserves_asset_referenced_by_surviving_version(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Shared draft asset")
    owner = DomainVersion(id=uuid4(), version_number=1, status=VersionStatus.DRAFT)
    survivor = DomainVersion(version_number=2, status=VersionStatus.ARCHIVED)
    test.versions.extend([owner, survivor])
    listening = DomainModule(module_type=ModuleType.LISTENING, order_index=0)
    survivor.modules.append(listening)
    asset = Asset(
        id=uuid4(),
        test_version_id=owner.id,
        asset_type=AssetType.LISTENING_AUDIO,
        relative_path=f"audio/{uuid4()}.mp3",
        mime_type="audio/mpeg",
        original_name="fictional.mp3",
        file_size=10,
        created_at=datetime.now(UTC),
    )
    await persist(db_session, test)
    await persist(db_session, asset)
    listening_id = listening.id
    asset_id = asset.id
    part = ListeningPart(
        module_id=listening_id,
        title="Part 1",
        order_index=0,
    )
    async with db_session.begin():
        stored_listening = await db_session.get(DomainModule, listening_id)
        assert stored_listening is not None
        stored_listening.audio_asset_id = asset_id
        db_session.add(part)
        await db_session.flush()
    test_id = test.id
    owner_id = owner.id
    survivor_id = survivor.id
    part_id = part.id

    await LifecycleService(db_session).delete_draft(test_id, owner_id)

    preserved = await db_session.scalar(select(Asset).where(Asset.id == asset_id))
    assert preserved is not None
    assert preserved.test_version_id == survivor_id
    assert (await db_session.get(DomainModule, listening_id)).audio_asset_id == asset_id  # type: ignore[union-attr]
    assert await db_session.get(ListeningPart, part_id) is not None


@pytest.mark.integration
async def test_delete_draft_deletes_unreferenced_asset_record_without_touching_file_storage(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Unused asset")
    draft = DomainVersion(id=uuid4(), version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(draft)
    asset = Asset(
        id=uuid4(),
        test_version_id=draft.id,
        asset_type=AssetType.QUESTION_IMAGE,
        relative_path=f"images/{uuid4()}.png",
        mime_type="image/png",
        original_name="fictional.png",
        file_size=10,
        created_at=datetime.now(UTC),
    )
    await persist(db_session, test)
    await persist(db_session, asset)
    test_id = test.id
    draft_id = draft.id
    asset_id = asset.id

    await LifecycleService(db_session).delete_draft(test_id, draft_id)

    assert await db_session.scalar(select(Asset).where(Asset.id == asset_id)) is None


@pytest.mark.integration
async def test_delete_draft_only_test_hard_deletes_test_and_owned_versions(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Disposable")
    draft = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(draft)
    await persist(db_session, test)

    result = await LifecycleService(db_session).delete_test(test.id)

    assert result.action == "DELETED"
    assert await db_session.get(DomainTest, test.id) is None
    assert await db_session.get(DomainVersion, draft.id) is None


@pytest.mark.integration
async def test_hard_delete_preserves_asset_referenced_by_unrelated_test(
    db_session: AsyncSession,
) -> None:
    deleted_test = DomainTest(title="Disposable asset owner")
    deleted_draft = DomainVersion(id=uuid4(), version_number=1, status=VersionStatus.DRAFT)
    deleted_test.versions.append(deleted_draft)
    surviving_test = DomainTest(title="Asset consumer")
    surviving_draft = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    surviving_test.versions.append(surviving_draft)
    listening = DomainModule(module_type=ModuleType.LISTENING, order_index=0)
    surviving_draft.modules.append(listening)
    await persist(db_session, deleted_test, surviving_test)
    asset = Asset(
        id=uuid4(),
        test_version_id=deleted_draft.id,
        asset_type=AssetType.LISTENING_AUDIO,
        relative_path=f"audio/{uuid4()}.mp3",
        mime_type="audio/mpeg",
        original_name="fictional-shared.mp3",
        file_size=10,
        created_at=datetime.now(UTC),
    )
    await persist(db_session, asset)
    listening_id = listening.id
    asset_id = asset.id
    part = ListeningPart(
        module_id=listening_id,
        title="Part 1",
        order_index=0,
    )
    async with db_session.begin():
        stored_listening = await db_session.get(DomainModule, listening_id)
        assert stored_listening is not None
        stored_listening.audio_asset_id = asset_id
        db_session.add(part)
        await db_session.flush()
    deleted_test_id = deleted_test.id
    surviving_draft_id = surviving_draft.id
    part_id = part.id

    result = await LifecycleService(db_session).delete_test(deleted_test_id)

    assert result.action == "DELETED"
    preserved = await db_session.scalar(select(Asset).where(Asset.id == asset_id))
    assert preserved is not None
    assert preserved.test_version_id == surviving_draft_id
    assert (await db_session.get(DomainModule, listening_id)).audio_asset_id == asset_id  # type: ignore[union-attr]
    assert await db_session.get(ListeningPart, part_id) is not None


@pytest.mark.integration
async def test_published_test_is_archived_listed_and_restored_with_history(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Historical")
    version = DomainVersion(
        version_number=1,
        status=VersionStatus.PUBLISHED,
        published_at=datetime.now(UTC),
    )
    test.versions.append(version)
    _, _, _, question = draft_content(version)
    now = datetime.now(UTC)
    attempt = Attempt(
        test_version=version,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=now,
        last_active_at=now,
        finished_at=now,
        status=AttemptStatus.SUBMITTED,
    )
    answer = AttemptAnswer(attempt=attempt, question=question, value="A", is_correct=True)
    await persist(db_session, test, attempt, answer)
    service = LifecycleService(db_session)
    test_id = test.id
    version_id = version.id
    attempt_id = attempt.id
    answer_id = answer.id

    result = await service.delete_test(test_id)

    assert result.action == "ARCHIVED"
    assert test_id not in {item.id for item in await service.list_tests(archived=False)}
    assert test_id in {item.id for item in await service.list_tests(archived=True)}
    await db_session.rollback()

    restored = await service.restore_test(test_id)

    assert restored.id == test_id
    assert restored.archived_at is None
    assert test_id in {item.id for item in await service.list_tests(archived=False)}
    assert await db_session.get(DomainVersion, version_id) is not None
    assert await db_session.get(Attempt, attempt_id) is not None
    assert await db_session.get(AttemptAnswer, answer_id) is not None


@pytest.mark.integration
async def test_test_with_archived_version_is_archived_instead_of_deleted(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Archived version history")
    version = DomainVersion(version_number=1, status=VersionStatus.ARCHIVED)
    test.versions.append(version)
    await persist(db_session, test)

    result = await LifecycleService(db_session).delete_test(test.id)

    assert result.action == "ARCHIVED"
    assert await db_session.get(DomainVersion, version.id) is not None

    with pytest.raises(AppError) as caught:
        await LifecycleService(db_session).delete_test(test.id)
    assert caught.value.code == "TEST_ALREADY_ARCHIVED"


@pytest.mark.integration
async def test_restore_active_test_returns_conflict(db_session: AsyncSession) -> None:
    test = DomainTest(title="Already active")
    await persist(db_session, test)

    with pytest.raises(AppError) as caught:
        await LifecycleService(db_session).restore_test(test.id)

    assert caught.value.code == "TEST_NOT_ARCHIVED"
    assert caught.value.status_code == 409


@pytest.mark.integration
async def test_delete_and_restore_endpoints_return_structured_results(
    db_session: AsyncSession,
    authenticated_admin,
) -> None:
    test = DomainTest(title="API lifecycle")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    test.versions.append(version)
    await persist(db_session, test)
    test_id = test.id

    async def override_session():
        try:
            yield db_session
        finally:
            if db_session.in_transaction():
                await db_session.rollback()

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            archived = await client.delete(f"/api/v1/tests/{test_id}")
            hidden = await client.get("/api/v1/tests")
            archived_list = await client.get("/api/v1/tests", params={"archived": "true"})
            restored = await client.post(f"/api/v1/tests/{test_id}/restore")
            active_conflict = await client.post(f"/api/v1/tests/{test_id}/restore")
    finally:
        app.dependency_overrides.clear()

    assert archived.status_code == 200
    assert archived.json() == {"test_id": str(test_id), "action": "ARCHIVED"}
    assert all(item["id"] != str(test_id) for item in hidden.json())
    assert any(item["id"] == str(test_id) for item in archived_list.json())
    assert restored.status_code == 200
    assert restored.json()["id"] == str(test_id)
    assert active_conflict.status_code == 409
    assert active_conflict.json()["code"] == "TEST_NOT_ARCHIVED"


@pytest.mark.integration
async def test_delete_draft_endpoint_rejects_published_version(
    db_session: AsyncSession,
    authenticated_admin,
) -> None:
    test = DomainTest(title="API draft lifecycle")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    test.versions.append(version)
    await persist(db_session, test)
    test_id = test.id
    version_id = version.id

    async def override_session():
        try:
            yield db_session
        finally:
            if db_session.in_transaction():
                await db_session.rollback()

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(f"/api/v1/tests/{test_id}/versions/{version_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["code"] == "VERSION_NOT_DRAFT"
    assert await db_session.get(DomainVersion, version_id) is not None
