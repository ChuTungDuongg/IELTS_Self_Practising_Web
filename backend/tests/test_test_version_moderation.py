from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select, update
from teacher_helpers import api_client, make_user, make_version

from app.core.exceptions import AppError
from app.models import TestVersion as Version
from app.models import TestVersionModeration as Moderation
from app.models import User
from app.models.enums import ModerationScope, ModerationStatus, UserRole, VersionStatus
from app.services.access_policy import AccessPolicy
from app.services.content_governance import ContentGovernanceService


async def test_moderation_pages_use_a_stable_order_when_requests_share_a_timestamp(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    _, version = await make_version(db_session, teacher)
    stamp = datetime(2026, 10, 11, tzinfo=UTC)
    async with db_session.begin():
        db_session.add_all(
            [
                Moderation(
                    id=UUID(int=2),
                    test_version_id=version.id,
                    scope=ModerationScope.CLASSROOM,
                    submitted_by_user_id=teacher.id,
                    submitted_at=stamp,
                ),
                Moderation(
                    id=UUID(int=1),
                    test_version_id=version.id,
                    scope=ModerationScope.PUBLIC,
                    submitted_by_user_id=teacher.id,
                    submitted_at=stamp,
                ),
            ]
        )
    service = ContentGovernanceService(db_session, db_session.info["current_user_identity"])
    first = await service.list_requests(status=ModerationStatus.PENDING, limit=1, offset=0)
    second = await service.list_requests(status=ModerationStatus.PENDING, limit=1, offset=1)
    assert [first[0].id, second[0].id] == [UUID(int=1), UUID(int=2)]


async def test_submission_uses_locked_current_role_instead_of_stale_auth_identity(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    _, version = await make_version(db_session, teacher, status=VersionStatus.PUBLISHED)
    version_id = version.id
    service = ContentGovernanceService(db_session, teacher)
    async with db_session.begin():
        await db_session.execute(
            update(User).where(User.id == teacher.id).values(role=UserRole.ADMIN)
        )
    assert teacher.role == UserRole.TEACHER  # Authentication's separate identity is stale.
    with pytest.raises(AppError) as error:
        await service.submit_moderation(version_id, ModerationScope.PUBLIC, None)
    assert error.value.code == "TEACHER_REQUIRED"


async def test_personal_library_filters_owner_private_versions_even_for_admin(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    admin = db_session.info["current_user_identity"]
    test, version = await make_version(db_session, teacher)
    test_id, version_id = test.id, version.id
    owner_service = ContentGovernanceService(db_session, teacher)
    moderator = ContentGovernanceService(db_session, admin)
    classroom = await owner_service.submit_moderation(version_id, ModerationScope.CLASSROOM, None)
    await moderator.approve(classroom.id, None)

    async def assert_library(visible):
        for actor in (teacher, admin):
            async with api_client(db_session, actor) as client:
                owned = await client.get(f"/api/v1/tests/{test_id}")
                assert owned.status_code == 200 and owned.json()["versions"]
                public = await client.get("/api/v1/tests?public_only=true")
                assert (str(test_id) in {item["id"] for item in public.json()}) is visible
                detail = await client.get(f"/api/v1/test-versions/{version_id}?public_only=true")
                assert detail.status_code == (200 if visible else 404)

    await assert_library(False)
    public = await owner_service.submit_moderation(version_id, ModerationScope.PUBLIC, None)
    await moderator.approve(public.id, None)
    await assert_library(True)
    await moderator.revoke(public.id, "Keep classroom use only")
    await assert_library(False)


@pytest.mark.parametrize("scope", list(ModerationScope))
async def test_submit_cancel_locks_and_keeps_audit(db_session, scope):
    teacher = await make_user(db_session, UserRole.TEACHER)
    _, version = await make_version(db_session, teacher)
    version_id, module_id = version.id, version.modules[0].id
    service = ContentGovernanceService(db_session, teacher)
    request = await service.submit_moderation(version_id, scope, "Please review")
    assert request.status == ModerationStatus.PENDING
    with pytest.raises(AppError) as error:
        await service.submit_moderation(version_id, scope, None)
    assert error.value.code == "MODERATION_ALREADY_PENDING"
    async with api_client(db_session, teacher) as client:
        response = await client.delete(f"/api/v1/test-modules/{module_id}")
        assert response.status_code == 409
    cancelled = await service.cancel_request(request.id)
    assert cancelled.status == ModerationStatus.CANCELLED and cancelled.cancelled_at
    async with db_session.begin():
        await AccessPolicy(db_session, teacher).lock_version(version_id, mutable=True)
    fresh = await service.submit_moderation(version_id, scope, None)
    assert fresh.id != request.id


async def test_scopes_revocation_visibility_and_owner_are_independent(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    student = await make_user(db_session)
    admin = db_session.info["current_user_identity"]
    test, version = await make_version(db_session, teacher)
    test_id, version_id = test.id, version.id
    request = await ContentGovernanceService(db_session, teacher).submit_moderation(
        version_id, ModerationScope.CLASSROOM, None
    )
    service = ContentGovernanceService(db_session, admin)
    await service.approve(request.id, "Approved")
    assert version.status == VersionStatus.PUBLISHED
    assert test.owner_user_id == teacher.id
    async with api_client(db_session, student) as client:
        assert (await client.get(f"/api/v1/tests/{test_id}")).status_code == 404
    public = await ContentGovernanceService(db_session, teacher).submit_moderation(
        version_id, ModerationScope.PUBLIC, None
    )
    await service.approve(public.id, None)
    async with api_client(db_session, student) as client:
        assert (await client.get(f"/api/v1/tests/{test_id}")).status_code == 200
    await service.revoke(public.id, "Withdraw public access")
    async with api_client(db_session, student) as client:
        assert (await client.get(f"/api/v1/tests/{test_id}")).status_code == 404
    async with db_session.begin():
        assert (await db_session.get(Moderation, request.id)).status == ModerationStatus.APPROVED
        loaded = await db_session.get(Version, version_id)
        assert await AccessPolicy(db_session, student).version_access(loaded, classroom=True)
    await service.revoke(request.id, "Withdraw classroom access")
    async with db_session.begin():
        loaded = await db_session.get(Version, version_id)
        assert not await AccessPolicy(db_session, student).version_access(loaded, classroom=True)


async def test_owner_and_admin_boundaries_and_validation(db_session):
    owner = await make_user(db_session, UserRole.TEACHER)
    other = await make_user(db_session, UserRole.TEACHER)
    _, version = await make_version(db_session, owner)
    version_id = version.id
    with pytest.raises(AppError):
        await ContentGovernanceService(db_session, other).submit_moderation(
            version_id, ModerationScope.PUBLIC, None
        )
    request = await ContentGovernanceService(db_session, owner).submit_moderation(
        version_id, ModerationScope.PUBLIC, None
    )
    with pytest.raises(AppError):
        await ContentGovernanceService(db_session, owner).approve(request.id, None)
    admin = ContentGovernanceService(db_session, db_session.info["current_user_identity"])
    rejected = await admin.reject(request.id, "Revise first")
    assert rejected.status == ModerationStatus.REJECTED
    with pytest.raises(AppError):
        await admin.approve(request.id, None)
    fresh = await ContentGovernanceService(db_session, owner).submit_moderation(
        version_id, ModerationScope.PUBLIC, None
    )
    await admin.approve(fresh.id, None)
    with pytest.raises(AppError):
        await admin.approve(fresh.id, None)


async def test_new_approval_archives_old_version_without_rewriting_references(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    _, first = await make_version(db_session, teacher, status=VersionStatus.PUBLISHED)
    first_id = first.id
    async with db_session.begin():
        second = Version(test_id=first.test_id, version_number=2, status=VersionStatus.DRAFT)
        db_session.add(second)
        await db_session.flush()
    request = await ContentGovernanceService(db_session, teacher).submit_moderation(
        second.id, ModerationScope.CLASSROOM, None
    )
    with pytest.raises(AppError) as error:
        await ContentGovernanceService(
            db_session, db_session.info["current_user_identity"]
        ).approve(request.id, None)
    assert error.value.code == "VALIDATION_FAILED"
    async with db_session.begin():
        assert (await db_session.get(Version, first_id)).status == VersionStatus.PUBLISHED
        audit = await db_session.scalar(select(Moderation).where(Moderation.id == request.id))
        assert audit.status == ModerationStatus.PENDING


async def test_classroom_v2_replaces_public_v1_and_preserves_attempt_history(db_session):
    from app.models import Attempt
    from app.models.enums import ModuleType
    from app.schemas.attempts import AttemptCreate
    from app.schemas.tests import VersionCreate
    from app.services.attempts import AttemptService
    from app.services.tests import TestService

    teacher = await make_user(db_session, UserRole.TEACHER)
    student = await make_user(db_session)
    test, first = await make_version(db_session, teacher)
    test_id, first_id = test.id, first.id
    teacher_service = ContentGovernanceService(db_session, teacher)
    admin = ContentGovernanceService(db_session, db_session.info["current_user_identity"])
    initial = await teacher_service.submit_moderation(first_id, ModerationScope.PUBLIC, None)
    await admin.approve(initial.id, None)
    attempt = await AttemptService(db_session, student.id).start(
        AttemptCreate(
            test_version_id=first_id, module=ModuleType.WRITING, timer={"mode": "COUNT_UP"}
        )
    )
    await AttemptService(db_session, student.id).submit(attempt.attempt_id)
    second = await TestService(db_session, teacher).create_version(
        test_id, VersionCreate(source_version_id=first_id)
    )
    second_id = second.id
    await db_session.rollback()  # End the Builder read transaction between API-equivalent calls.
    request = await teacher_service.submit_moderation(second_id, ModerationScope.CLASSROOM, None)
    await admin.approve(request.id, None)
    async with db_session.begin():
        assert (await db_session.get(Version, first_id)).status == VersionStatus.ARCHIVED
        assert (await db_session.get(Version, second_id)).status == VersionStatus.PUBLISHED
        assert (await db_session.get(Attempt, attempt.attempt_id)).test_version_id == first_id
    async with api_client(db_session, student) as client:
        assert (await client.get(f"/api/v1/tests/{test_id}")).status_code == 404
        assert (
            await client.get(f"/api/v1/attempts/{attempt.attempt_id}/writing-review")
        ).status_code == 200
