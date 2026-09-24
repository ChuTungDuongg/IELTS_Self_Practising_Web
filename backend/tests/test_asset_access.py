"""Asset access for immutable published content and owned historical attempts."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import (
    Asset,
    Attempt,
    ListeningPart,
    Question,
    QuestionGroup,
    ReadingPassage,
    User,
    WritingTask,
)
from app.models import (
    Test as IeltsTest,
)
from app.models import (
    TestModule as IeltsModule,
)
from app.models import (
    TestSession as FullMockSession,
)
from app.models import (
    TestVersion as VersionRecord,
)
from app.models.enums import (
    AssetType,
    AttemptStatus,
    ModuleType,
    TimerMode,
    UserRole,
    VersionStatus,
)
from app.models.enums import (
    TestSessionStatus as SessionStatus,
)
from app.schemas.tests import VersionCreate
from app.services.tests import TestService as VersionService


def _asset(version: VersionRecord, root: Path, kind: AssetType) -> Asset:
    is_audio = kind == AssetType.LISTENING_AUDIO
    relative_path = f"{'audio' if is_audio else 'images'}/{uuid4()}{'.mp3' if is_audio else '.png'}"
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    content = b"fictional audio" if is_audio else b"fictional image"
    path.write_bytes(content)
    asset = Asset(
        id=uuid4(),
        asset_type=kind,
        relative_path=relative_path,
        mime_type="audio/mpeg" if is_audio else "image/png",
        original_name=path.name,
        file_size=len(content),
    )
    version.assets.append(asset)
    return asset


def _visual_group(*, asset: Asset, reading: bool) -> QuestionGroup:
    question_id = uuid4()
    option_ids = [str(uuid4()), str(uuid4())]
    config: dict[str, object] = {
        "options": [
            {"id": option_ids[0], "label": "A", "text": "North gate"},
            {"id": option_ids[1], "label": "B", "text": "South gate"},
        ]
    }
    if reading:
        config["markers"] = [
            {"id": str(uuid4()), "question_id": str(question_id), "x": 0.5, "y": 0.5}
        ]
    group = QuestionGroup(
        question_type="map_labelling",
        instruction="Choose a letter.",
        config=config,
        order_index=0,
        image_asset=asset,
    )
    group.questions.append(
        Question(
            id=question_id,
            number=1,
            prompt="Fictional gate",
            config={},
            answer_key={"kind": "SINGLE_OPTION", "value": option_ids[0]},
            order_index=0,
        )
    )
    return group


async def _draft_with_assets(
    session: AsyncSession, root: Path
) -> tuple[UUID, UUID, dict[str, UUID], dict[str, User]]:
    users = {
        name: User(
            email=f"{name}-{uuid4()}@example.com",
            display_name=f"Fictional {name}",
            role=UserRole.USER,
            is_active=True,
            email_verified=True,
        )
        for name in ("owner", "reader", "writer", "stranger")
    }
    test = IeltsTest(title="Fictional historical asset test")
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(version)
    assets = {
        "reading": _asset(version, root, AssetType.QUESTION_IMAGE),
        "audio": _asset(version, root, AssetType.LISTENING_AUDIO),
        "listening": _asset(version, root, AssetType.QUESTION_IMAGE),
        "writing": _asset(version, root, AssetType.WRITING_TASK_IMAGE),
        "unreferenced": _asset(version, root, AssetType.QUESTION_IMAGE),
    }

    reading = IeltsModule(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional passage",
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
    reading_group = _visual_group(asset=assets["reading"], reading=True)
    passage.question_groups.append(reading_group)
    reading.passages.append(passage)
    reading.question_groups.append(reading_group)

    listening = IeltsModule(
        module_type=ModuleType.LISTENING,
        order_index=1,
        audio_asset=assets["audio"],
    )
    part = ListeningPart(title="Fictional section", order_index=0)
    listening_group = _visual_group(asset=assets["listening"], reading=False)
    part.question_groups.append(listening_group)
    listening.listening_parts.append(part)
    listening.question_groups.append(listening_group)

    writing = IeltsModule(module_type=ModuleType.WRITING, order_index=2)
    writing.writing_tasks.extend(
        [
            WritingTask(
                task_number=1,
                prompt="Describe the fictional chart.",
                image_asset=assets["writing"],
                minimum_recommended_words=150,
                recommended_duration_seconds=1200,
                order_index=0,
            ),
            WritingTask(
                task_number=2,
                prompt="Discuss a fictional proposition.",
                minimum_recommended_words=250,
                recommended_duration_seconds=2400,
                order_index=1,
            ),
        ]
    )
    version.modules.extend([reading, listening, writing])
    async with session.begin():
        session.add_all([test, *users.values()])
        await session.flush()
    identities = {
        name: User(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            is_active=True,
            email_verified=True,
        )
        for name, user in users.items()
    }
    return test.id, version.id, {name: asset.id for name, asset in assets.items()}, identities


@pytest_asyncio.fixture
async def asset_client(db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = SimpleNamespace(
        resolved_storage_root=tmp_path,
        max_image_upload_mb=10,
        max_audio_upload_mb=100,
    )
    monkeypatch.setattr("app.api.v1.assets.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.tests.get_settings", lambda: settings)
    current: dict[str, object] = {"user": None, "session": db_session}

    async def override_session():
        yield db_session
        if db_session.in_transaction():
            await db_session.rollback()

    previous_session = app.dependency_overrides.get(get_session)
    previous_user = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, current, tmp_path
    finally:
        if previous_session is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous_session
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user


async def _request_as(
    client: httpx.AsyncClient, current: dict, user: User, method: str, path: str, **kwargs
):
    session: AsyncSession = current["session"]
    if session.in_transaction():
        await session.rollback()
    current["user"] = user
    response = await client.request(method, path, **kwargs)
    if session.in_transaction():
        await session.rollback()
    return response


async def _start(
    client: httpx.AsyncClient, current: dict, user: User, version_id: UUID, module: ModuleType
) -> UUID:
    response = await _request_as(
        client,
        current,
        user,
        "POST",
        "/api/v1/attempts",
        json={
            "test_version_id": str(version_id),
            "module": module.value,
            "timer": {"mode": "COUNT_UP"},
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["attempt_id"])


async def _content(client: httpx.AsyncClient, current: dict, user: User, asset_id: UUID):
    return await _request_as(client, current, user, "GET", f"/api/v1/assets/{asset_id}/content")


@pytest.mark.integration
async def test_published_then_archived_assets_follow_owned_module_attempts(
    db_session: AsyncSession, asset_client
) -> None:
    client, current, root = asset_client
    test_id, version_id, assets, users = await _draft_with_assets(db_session, root)
    lifecycle = VersionService(db_session)
    published = await lifecycle.publish(version_id)
    assert published.status == VersionStatus.PUBLISHED
    await db_session.rollback()

    # Current published assets retain the existing authenticated USER behavior.
    assert (await _content(client, current, users["stranger"], assets["audio"])).status_code == 200

    listening_attempt = await _start(
        client, current, users["owner"], version_id, ModuleType.LISTENING
    )
    reading_attempt = await _start(client, current, users["owner"], version_id, ModuleType.READING)
    await _start(client, current, users["reader"], version_id, ModuleType.READING)
    writing_attempt = await _start(client, current, users["writer"], version_id, ModuleType.WRITING)
    submitted = await _request_as(
        client, current, users["owner"], "POST", f"/api/v1/attempts/{reading_attempt}/submit"
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"

    clone = await lifecycle.create_version(test_id, VersionCreate(source_version_id=version_id))
    clone_id = clone.id
    await db_session.rollback()
    second = await lifecycle.publish(clone_id)
    assert second.status == VersionStatus.PUBLISHED
    await db_session.rollback()
    archived_status = await db_session.scalar(
        select(VersionRecord.status).where(VersionRecord.id == version_id)
    )
    assert archived_status == VersionStatus.ARCHIVED
    await db_session.rollback()

    active_exam = await _request_as(
        client, current, users["owner"], "GET", f"/api/v1/attempts/{listening_attempt}/exam"
    )
    assert active_exam.status_code == 200, active_exam.text
    assert active_exam.json()["listening_audio_asset"]["id"] == str(assets["audio"])
    assert str(assets["listening"]) in str(active_exam.json()["listening_parts"])
    review = await _request_as(
        client, current, users["owner"], "GET", f"/api/v1/attempts/{reading_attempt}/reading-review"
    )
    assert review.status_code == 200, review.text
    assert str(assets["reading"]) in str(review.json()["passages"])
    writing_exam = await _request_as(
        client, current, users["writer"], "GET", f"/api/v1/attempts/{writing_attempt}/exam"
    )
    assert writing_exam.status_code == 200, writing_exam.text
    assert writing_exam.json()["writing_tasks"][0]["image_asset"]["id"] == str(assets["writing"])

    for name in ("audio", "listening", "reading"):
        response = await _content(client, current, users["owner"], assets[name])
        assert response.status_code == 200, (name, response.text)
    assert (await _content(client, current, users["owner"], assets["writing"])).status_code == 404
    assert (
        await _content(client, current, users["owner"], assets["unreferenced"])
    ).status_code == 404
    writing_image = await _content(client, current, users["writer"], assets["writing"])
    assert writing_image.status_code == 200
    assert writing_image.content == b"fictional image"
    assert (await _content(client, current, users["writer"], assets["audio"])).status_code == 404

    assert (await _content(client, current, users["reader"], assets["reading"])).status_code == 200
    for name in ("audio", "listening", "writing"):
        response = await _content(client, current, users["reader"], assets[name])
        assert response.status_code == 404, name
        assert response.json()["code"] == "ASSET_NOT_FOUND"
    for name in ("audio", "listening", "reading", "writing"):
        assert (await _content(client, current, users["stranger"], assets[name])).status_code == 404

    # An Attempt for the same module on the newer version never grants V1 access.
    await _start(client, current, users["stranger"], clone_id, ModuleType.LISTENING)
    assert (await _content(client, current, users["stranger"], assets["audio"])).status_code == 404


@pytest.mark.integration
async def test_historical_asset_status_full_mock_draft_and_admin_boundaries(
    db_session: AsyncSession, asset_client
) -> None:
    client, current, root = asset_client
    test_id, version_id, assets, users = await _draft_with_assets(db_session, root)
    admin = db_session.info["current_user_identity"]
    async with db_session.begin():
        db_session.add(
            Attempt(
                user_id=users["owner"].id,
                test_version_id=version_id,
                module_type=ModuleType.LISTENING,
                timer_mode=TimerMode.COUNT_UP,
                started_at=datetime.now(UTC),
                last_active_at=datetime.now(UTC),
                status=AttemptStatus.IN_PROGRESS,
            )
        )
    # Even a malformed Attempt pointing at a draft must not expose draft assets.
    for name in ("reading", "audio", "listening", "writing", "unreferenced"):
        assert (await _content(client, current, users["owner"], assets[name])).status_code == 404
        assert (await _content(client, current, admin, assets[name])).status_code == 200
    assert (await _content(client, current, users["owner"], uuid4())).status_code == 404

    await db_session.rollback()
    lifecycle = VersionService(db_session)
    await lifecycle.publish(version_id)
    await db_session.rollback()
    reading_attempt = await _start(client, current, users["owner"], version_id, ModuleType.READING)
    await _start(client, current, users["reader"], version_id, ModuleType.READING)
    clone = await lifecycle.create_version(test_id, VersionCreate(source_version_id=version_id))
    clone_id = clone.id
    await db_session.rollback()
    await lifecycle.publish(clone_id)
    await db_session.rollback()

    # No status restriction: the same owned version/module remains readable in every state.
    for status in AttemptStatus:
        async with db_session.begin():
            attempt = await db_session.get(Attempt, reading_attempt)
            assert attempt is not None
            attempt.status = status
        response = await _content(client, current, users["owner"], assets["reading"])
        assert response.status_code == 200, status

    # A Full Mock session alone does not grant access; its module Attempt does.
    await db_session.rollback()
    async with db_session.begin():
        mock = FullMockSession(
            user_id=users["reader"].id,
            test_version_id=version_id,
            status=SessionStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
        )
        db_session.add(mock)
        await db_session.flush()
        mock_id = mock.id
    assert (await _content(client, current, users["reader"], assets["audio"])).status_code == 404
    assert (await _content(client, current, users["reader"], assets["reading"])).status_code == 200
    await db_session.rollback()
    async with db_session.begin():
        db_session.add(
            Attempt(
                user_id=users["reader"].id,
                test_version_id=version_id,
                test_session_id=mock_id,
                module_type=ModuleType.LISTENING,
                timer_mode=TimerMode.COUNT_UP,
                started_at=datetime.now(UTC),
                last_active_at=datetime.now(UTC),
                status=AttemptStatus.IN_PROGRESS,
            )
        )
    assert (await _content(client, current, users["reader"], assets["audio"])).status_code == 200
    assert (
        await _content(client, current, users["reader"], assets["listening"])
    ).status_code == 200
    assert (await _content(client, current, users["reader"], assets["writing"])).status_code == 404

    # Admin access remains independent of references and Attempt ownership.
    assert (await _content(client, current, admin, assets["unreferenced"])).status_code == 200
