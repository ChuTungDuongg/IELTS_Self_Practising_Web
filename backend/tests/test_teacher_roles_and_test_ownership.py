"""Resource-scoped teacher Builder authorization and role administration."""

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.exceptions import AppError
from app.main import app
from app.models import Classroom, ListeningPart, QuestionGroup, ReadingPassage, User, WritingTask
from app.models import Test as ContentTest
from app.models import TestModule as ContentModule
from app.models import TestVersion as ContentVersion
from app.models import TestVersionModeration as ModerationRecord
from app.models.enums import (
    ClassroomStatus,
    ModerationScope,
    ModerationStatus,
    ModuleType,
    UserRole,
    VersionStatus,
)
from app.models.enums import (
    TestOrigin as ContentOrigin,
)
from app.schemas.admin import AdminUserUpdate
from app.schemas.auth import RegisterRequest
from app.schemas.tests import TestCreate as CreateTest
from app.services.access_policy import AccessPolicy
from app.services.admin import AdminService
from app.services.tests import TestService as ContentService


@pytest_asyncio.fixture
async def actors(db_session):
    users = [
        User(
            email=f"{uuid4()}@example.com",
            display_name=role.value,
            role=role,
            is_active=True,
            email_verified=True,
        )
        for role in (UserRole.ADMIN, UserRole.TEACHER, UserRole.TEACHER, UserRole.USER)
    ]
    async with db_session.begin():
        db_session.add_all(users)
        await db_session.flush()
    for user in users:
        db_session.expunge(user)
    return users


@pytest_asyncio.fixture
async def client(db_session):
    async def override_session():
        try:
            yield db_session
        finally:
            if db_session.in_transaction():
                await db_session.rollback()

    app.dependency_overrides[get_session] = override_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as value:
        yield value
    app.dependency_overrides.clear()


async def owned_draft(db_session, teacher):
    return await ContentService(db_session, actor=teacher).create_test(
        CreateTest(title="Fictional owned test")
    )


@pytest.mark.asyncio
async def test_teacher_create_persists_owner_and_origin_admin_stays_official(db_session, actors):
    admin, teacher, _, student = actors
    for actor, origin in ((teacher, ContentOrigin.TEACHER), (admin, ContentOrigin.ADMIN)):
        test = await owned_draft(db_session, actor)
        assert test.owner_user_id == actor.id and test.origin == origin
    with pytest.raises(AppError) as rejected:
        await owned_draft(db_session, student)
    assert rejected.value.status_code == 403


@pytest.mark.asyncio
async def test_only_owner_or_admin_reads_builder_and_mutates_draft(client, db_session, actors):
    admin, teacher, other, student = actors
    test = await owned_draft(db_session, teacher)
    test_id = test.id
    version_id = test.versions[0].id
    for actor, expected in ((teacher, 200), (admin, 200), (other, 403), (student, 403)):
        app.dependency_overrides[get_current_user] = lambda actor=actor: actor
        assert (
            await client.get(f"/api/v1/test-versions/{version_id}/builder")
        ).status_code == expected
        assert (
            await client.patch(f"/api/v1/tests/{test_id}", json={"description": "safe"})
        ).status_code == expected
    app.dependency_overrides[get_current_user] = lambda: teacher
    assert (await client.get("/api/v1/admin/users")).status_code == 403
    assert (await client.post(f"/api/v1/test-versions/{version_id}/publish")).status_code == 403


@pytest.mark.asyncio
async def test_pending_review_locks_metadata_content_upload_and_delete(client, db_session, actors):
    _, teacher, _, _ = actors
    test = await owned_draft(db_session, teacher)
    test_id = test.id
    version_id = test.versions[0].id
    async with db_session.begin():
        db_session.add(
            ModerationRecord(
                test_version_id=version_id,
                scope=ModerationScope.CLASSROOM,
                status=ModerationStatus.PENDING,
                submitted_by_user_id=teacher.id,
            )
        )
    app.dependency_overrides[get_current_user] = lambda: teacher
    requests = (
        ("patch", f"/api/v1/tests/{test_id}", {"description": "changed"}),
        ("post", f"/api/v1/test-versions/{version_id}/modules", {"module_type": "READING"}),
        ("delete", f"/api/v1/tests/{test_id}/versions/{version_id}", None),
        ("delete", f"/api/v1/tests/{test_id}", None),
    )
    for method, url, body in requests:
        response = await client.request(method, url, json=body)
        assert response.status_code == 409
    response = await client.post(
        "/api/v1/assets/question-images",
        data={"test_version_id": str(version_id)},
        files={"file": ("safe.png", b"unused", "image/png")},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_published_content_immutable_and_approval_does_not_transfer_owner(db_session, actors):
    admin, teacher, _, _ = actors
    test = await owned_draft(db_session, teacher)
    async with db_session.begin():
        test.versions[0].status = VersionStatus.PUBLISHED
    test_id, version_id = test.id, test.versions[0].id
    for actor in (teacher, admin):
        with pytest.raises(AppError) as rejected:
            async with db_session.begin():
                await ContentService(db_session, actor=actor).ensure_draft(version_id)
        assert rejected.value.code == "TEST_VERSION_IMMUTABLE"
    test = await db_session.get(ContentTest, test_id)
    assert test.owner_user_id == teacher.id


@pytest.mark.asyncio
async def test_teacher_private_drafts_hidden_from_other_users_and_publication_is_not_public(
    client, db_session, actors
):
    _, teacher, other, student = actors
    test = await owned_draft(db_session, teacher)
    test_id, version_id = test.id, test.versions[0].id
    app.dependency_overrides[get_current_user] = lambda: teacher
    assert (await client.get(f"/api/v1/tests/{test_id}")).status_code == 200
    for actor in (other, student):
        app.dependency_overrides[get_current_user] = lambda actor=actor: actor
        assert (await client.get(f"/api/v1/tests/{test_id}")).status_code == 404
    async with db_session.begin():
        version = await db_session.get(ContentVersion, version_id)
        version.status = VersionStatus.PUBLISHED
    assert (await client.get(f"/api/v1/test-versions/{version_id}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["classroom", "pending", "draft"])
@pytest.mark.parametrize("departure", ["USER", "ADMIN", "inactive"])
async def test_demotion_requires_resolution_and_preserves_owned_history(
    db_session, actors, resource, departure
):
    admin, teacher, _, _ = actors
    test = await owned_draft(db_session, teacher)
    test_id = test.id
    async with db_session.begin():
        test.versions[0].status = (
            VersionStatus.PUBLISHED if resource != "draft" else VersionStatus.DRAFT
        )
        if resource == "classroom":
            item = Classroom(
                teacher_id=teacher.id, name="Fictional class", status=ClassroomStatus.ACTIVE
            )
            db_session.add(item)
        elif resource == "pending":
            item = ModerationRecord(
                test_version_id=test.versions[0].id,
                scope=ModerationScope.PUBLIC,
                status=ModerationStatus.PENDING,
                submitted_by_user_id=teacher.id,
            )
            db_session.add(item)
    item_id = item.id if resource != "draft" else None
    with pytest.raises(AppError) as rejected:
        await AdminService(db_session).update_user(
            admin.id,
            teacher.id,
            AdminUserUpdate(is_active=False)
            if departure == "inactive"
            else AdminUserUpdate(role=UserRole(departure)),
        )
    assert rejected.value.code == "TEACHER_HAS_ACTIVE_RESOURCES"
    async with db_session.begin():
        if resource == "classroom":
            item = await db_session.get(Classroom, item_id)
            item.status = ClassroomStatus.ARCHIVED
        elif resource == "pending":
            item = await db_session.get(ModerationRecord, item_id)
            item.status = ModerationStatus.CANCELLED
        else:
            test = await db_session.get(ContentTest, test_id)
            test.archived_at = datetime.now(UTC)
    result = await AdminService(db_session).update_user(
        admin.id,
        teacher.id,
        AdminUserUpdate(is_active=False)
        if departure == "inactive"
        else AdminUserUpdate(role=UserRole(departure)),
    )
    assert result.role == (UserRole.TEACHER if departure == "inactive" else UserRole(departure))
    assert result.is_active == (departure != "inactive")
    assert (
        await db_session.scalar(select(ContentTest.id).where(ContentTest.id == test_id)) == test_id
    )


@pytest.mark.asyncio
async def test_admin_promotes_teacher_but_public_registration_cannot_request_role(
    db_session, actors
):
    admin, _, _, student = actors
    result = await AdminService(db_session).update_user(
        admin.id, student.id, AdminUserUpdate(role=UserRole.TEACHER)
    )
    assert result.role == UserRole.TEACHER
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="safe@example.com",
            password="safe-password",
            display_name="Student",
            role="TEACHER",
        )


@pytest.mark.asyncio
async def test_version_access_classroom_public_are_separate(db_session, actors):
    _, teacher, _, student = actors
    test = await owned_draft(db_session, teacher)
    version = test.versions[0]
    async with db_session.begin():
        version.status = VersionStatus.PUBLISHED
        approval = ModerationRecord(
            test_version_id=version.id,
            scope=ModerationScope.CLASSROOM,
            status=ModerationStatus.APPROVED,
            submitted_by_user_id=teacher.id,
        )
        db_session.add(approval)
    version_id, approval_id = version.id, approval.id
    policy = AccessPolicy(db_session, student)
    assert await policy.version_access(version, classroom=True)
    assert not await policy.version_access(version)
    await db_session.rollback()
    async with db_session.begin():
        approval = await db_session.get(ModerationRecord, approval_id)
        approval.scope = ModerationScope.PUBLIC
        version = await db_session.get(ContentVersion, version_id)
    assert await policy.version_access(version) and await policy.version_access(
        version, classroom=True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("pending", [False, True], ids=["other-teacher", "pending-owner"])
async def test_lower_level_builder_endpoints_cannot_bypass_owner_or_pending_lock(
    client, db_session, actors, pending
):
    admin, teacher, other, _ = actors
    test = await owned_draft(db_session, teacher)
    test_id, version_id = test.id, test.versions[0].id
    reading, listening, writing = [
        ContentModule(test_version_id=version_id, module_type=kind, order_index=i)
        for i, kind in enumerate((ModuleType.READING, ModuleType.LISTENING, ModuleType.WRITING))
    ]
    async with db_session.begin():
        db_session.add_all([reading, listening, writing])
        await db_session.flush()
        passage = ReadingPassage(
            module_id=reading.id,
            title="Fictional passage",
            order_index=0,
            content_json=[],
            plain_text="Fictional source",
        )
        part = ListeningPart(module_id=listening.id, title="Fictional section", order_index=0)
        task = WritingTask(
            module_id=writing.id, task_number=2, prompt="Fictional prompt", order_index=0
        )
        db_session.add_all([passage, part, task])
        await db_session.flush()
        groups = [
            QuestionGroup(
                module_id=reading.id,
                passage_id=passage.id,
                question_type="single_choice",
                instruction="Fictional",
                order_index=0,
            ),
            QuestionGroup(
                module_id=listening.id,
                listening_part_id=part.id,
                question_type="single_choice",
                instruction="Fictional",
                order_index=0,
            ),
        ]
        db_session.add_all(groups)
        if pending:
            db_session.add(
                ModerationRecord(
                    test_version_id=version_id,
                    scope=ModerationScope.PUBLIC,
                    status=ModerationStatus.PENDING,
                    submitted_by_user_id=teacher.id,
                )
            )
        await db_session.flush()
        reading_id, listening_id, passage_id, part_id, task_id = (
            reading.id,
            listening.id,
            passage.id,
            part.id,
            task.id,
        )
        reading_group, listening_group = [group.id for group in groups]
    app.dependency_overrides[get_current_user] = lambda: teacher if pending else other
    passage_body = {
        "title": "Fictional",
        "order_index": 0,
        "blocks": [{"id": str(uuid4()), "text": "Source"}],
    }
    part_body = {"title": "Fictional", "order_index": 0}
    group_body = {
        "question_type": "single_choice",
        "order_index": 0,
        "questions": [
            {"number": 1, "prompt": "Fictional?", "config": {}, "answer_key": {}, "order_index": 0}
        ],
    }
    requests = [
        ("post", f"/test-versions/{version_id}/modules", {"module_type": "READING"}),
        (
            "patch",
            f"/test-modules/{reading_id}",
            {"expected_revision": 1, "recommended_duration_seconds": 3600},
        ),
        ("delete", f"/test-modules/{reading_id}", None),
        ("post", f"/test-versions/{version_id}/reading/passages", passage_body),
        ("put", f"/reading/passages/{passage_id}", {**passage_body, "expected_revision": 1}),
        ("delete", f"/reading/passages/{passage_id}", None),
        ("post", f"/reading/passages/{passage_id}/question-groups", group_body),
        ("put", f"/question-groups/{reading_group}", {**group_body, "expected_revision": 1}),
        ("delete", f"/question-groups/{reading_group}", None),
        (
            "put",
            f"/test-modules/{reading_id}/question-groups/order",
            {"expected_revision": 1, "group_ids": [str(reading_group)]},
        ),
        ("post", f"/test-versions/{version_id}/listening/parts", part_body),
        ("put", f"/listening/parts/{part_id}", {**part_body, "expected_revision": 1}),
        ("delete", f"/listening/parts/{part_id}", None),
        ("put", f"/listening/modules/{listening_id}/audio", {"expected_revision": 1}),
        ("post", f"/listening/parts/{part_id}/question-groups", group_body),
        (
            "put",
            f"/listening/question-groups/{listening_group}",
            {**group_body, "expected_revision": 1},
        ),
        ("delete", f"/question-groups/{listening_group}", None),
        (
            "put",
            f"/writing/tasks/{task_id}",
            {"expected_revision": 1, "prompt": "Fictional replacement"},
        ),
        ("post", f"/tests/{test_id}/versions", {}),
        ("post", f"/test-versions/{version_id}/validate", {}),
    ]
    for method, path, body in requests:
        response = await client.request(method, f"/api/v1{path}", json=body)
        if pending and (path.endswith("/validate") or path.endswith("/versions")):
            # Validation and returning an existing draft do not mutate the review target.
            assert response.status_code == (201 if path.endswith("/versions") else 200)
        else:
            assert response.status_code == (409 if pending else 403), (method, path, response.text)
    for asset_path in ("images", "question-images", "audio"):
        response = await client.post(
            f"/api/v1/assets/{asset_path}",
            data={"test_version_id": str(version_id)},
            files={"file": ("fictional.png", b"unused", "image/png")},
        )
        assert response.status_code == (409 if pending else 403)
    app.dependency_overrides[get_current_user] = lambda: admin
    assert (await client.post(f"/api/v1/test-versions/{version_id}/publish")).status_code == 409


@pytest.mark.asyncio
async def test_imported_drafts_have_an_explicit_owner_and_user_cannot_import(
    db_session, actors, tmp_path
):
    from app.schemas.draft_import import DraftImportManifest
    from app.services.draft_import import DraftImportService

    admin, teacher, _, student = actors
    source = DraftImportManifest.model_validate(
        {
            "format": "ielts-draft-import-v1",
            "title": "Fictional authored import",
            "allow_incomplete": True,
            "modules": [
                {
                    "type": "WRITING",
                    "tasks": [{"task_number": 2, "prompt": "Discuss a fictional garden."}],
                }
            ],
        }
    )
    for actor, origin in ((teacher, ContentOrigin.TEACHER), (admin, ContentOrigin.ADMIN)):
        result = await DraftImportService(db_session, actor=actor).import_manifest(source, tmp_path)
        async with db_session.begin():
            test = await db_session.get(ContentTest, result.test_id)
            assert test.owner_user_id == actor.id and test.origin == origin
    with pytest.raises(AppError) as rejected:
        await DraftImportService(db_session, actor=student).import_manifest(source, tmp_path)
    assert rejected.value.status_code == 403


@pytest.mark.asyncio
async def test_content_service_cannot_invent_admin_actor(db_session):
    del db_session.info["current_user_identity"]
    with pytest.raises(ValueError, match="explicit authenticated actor"):
        ContentService(db_session)


@pytest.mark.asyncio
async def test_next_draft_can_clone_published_version_under_public_review(
    client, db_session, actors
):
    _, teacher, _, _ = actors
    test = await owned_draft(db_session, teacher)
    test_id, version_id = test.id, test.versions[0].id
    async with db_session.begin():
        test.versions[0].status = VersionStatus.PUBLISHED
        db_session.add(
            ModerationRecord(
                test_version_id=version_id,
                scope=ModerationScope.PUBLIC,
                status=ModerationStatus.PENDING,
                submitted_by_user_id=teacher.id,
            )
        )
    app.dependency_overrides[get_current_user] = lambda: teacher
    response = await client.post(
        f"/api/v1/tests/{test_id}/versions", json={"source_version_id": str(version_id)}
    )
    assert response.status_code == 201
    assert response.json()["status"] == "DRAFT" and response.json()["version_number"] == 2
    async with db_session.begin():
        original = await db_session.get(ContentVersion, version_id)
        assert original.status == VersionStatus.PUBLISHED
    assert (
        await client.patch(f"/api/v1/tests/{test_id}", json={"title": "Blocked metadata"})
    ).status_code == 409


@pytest.mark.asyncio
async def test_notification_only_inactive_user_deletion_preserves_notification(db_session, actors):
    from app.models import Notification
    from app.models.enums import NotificationEntityType, NotificationType

    admin, _, _, student = actors
    student_id = student.id
    async with db_session.begin():
        row = await db_session.get(User, student_id)
        row.is_active = False
        notification = Notification(
            user_id=student_id,
            type=NotificationType.CLASSROOM_ARCHIVED,
            entity_type=NotificationEntityType.CLASSROOM,
            entity_id=uuid4(),
            payload_json={"classroom_name": "Fictional archived class"},
        )
        db_session.add(notification)
        await db_session.flush()
        notification_id = notification.id
    with pytest.raises(AppError) as rejected:
        await AdminService(db_session).delete_user(admin.id, student_id)
    assert rejected.value.code == "USER_HAS_ACADEMIC_RESOURCES"
    async with db_session.begin():
        assert await db_session.get(User, student_id) is not None
        assert await db_session.get(Notification, notification_id) is not None
