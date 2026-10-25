"""Actor/resource authorization shared by Builder, governance and classrooms."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models import (
    Classroom,
    ClassroomAssignment,
    Test,
    TestVersion,
    TestVersionModeration,
    User,
)
from app.models.enums import ModerationScope, ModerationStatus, TestOrigin, UserRole, VersionStatus


def resolve_actor(session: AsyncSession, actor: User | None) -> User:
    value = actor if actor is not None else session.info.get("current_user_identity")
    if not isinstance(value, User):
        raise ValueError("Content operations require an explicit authenticated actor")
    return value


class AccessPolicy:
    def __init__(self, session: AsyncSession, actor: User | None = None) -> None:
        self.session = session
        self.actor = resolve_actor(session, actor)
        self.actor_id = self.actor.id

    async def lock_actor(self) -> User:
        """Serialize creation of teacher resources with administrative demotion."""
        actor = await self.session.scalar(
            select(User)
            .where(User.id == self.actor_id)
            .execution_options(populate_existing=True)
            .with_for_update(key_share=True)
        )
        if actor is None or not actor.is_active:
            raise AppError("ACCOUNT_INACTIVE", "This account is inactive.", 403)
        # A rollback expires ORM rows. Keep the policy's authenticated identity
        # detached so reusing a service after a conflict does not trigger lazy IO.
        self.actor = User(id=actor.id, role=actor.role, is_active=actor.is_active)
        return actor

    async def require_test_create(self) -> None:
        if self.actor.role not in {UserRole.ADMIN, UserRole.TEACHER}:
            raise AppError("TEACHER_REQUIRED", "Teacher or administrator access is required.", 403)

    async def require_test_edit(self, test: Test) -> None:
        await self.require_test_create()
        if self.actor.role != UserRole.ADMIN and test.owner_user_id != self.actor.id:
            raise AppError(
                "TEST_OWNERSHIP_REQUIRED", "Only the test owner may manage this content.", 403
            )

    async def require_builder_read(self, version: TestVersion) -> None:
        test = await self.session.get(Test, version.test_id)
        assert test is not None
        await self.require_test_edit(test)

    async def pending(self, version_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(TestVersionModeration.id)
                .where(
                    TestVersionModeration.test_version_id == version_id,
                    TestVersionModeration.status == ModerationStatus.PENDING,
                )
                .limit(1)
            )
            is not None
        )

    async def require_version_mutable(self, version: TestVersion) -> None:
        await self.require_builder_read(version)
        if version.status != VersionStatus.DRAFT:
            raise AppError("TEST_VERSION_IMMUTABLE", "Published versions cannot be changed.", 409)
        test = await self.session.get(Test, version.test_id)
        assert test is not None
        if test.archived_at is not None:
            raise AppError("TEST_ARCHIVED", "Restore this test before editing it.", 409)
        if await self.pending(version.id):
            raise AppError("VERSION_MODERATION_PENDING", "Pending review locks this version.", 409)

    async def require_no_pending_test(self, test_id: UUID) -> None:
        pending = await self.session.scalar(
            select(TestVersionModeration.id)
            .join(TestVersion, TestVersionModeration.test_version_id == TestVersion.id)
            .where(
                TestVersion.test_id == test_id,
                TestVersionModeration.status == ModerationStatus.PENDING,
            )
            .limit(1)
        )
        if pending is not None:
            raise AppError("VERSION_MODERATION_PENDING", "Pending review locks this test.", 409)

    async def lock_version(
        self, version_id: UUID, *, mutable: bool = False, builder: bool = False
    ) -> TestVersion:
        if mutable:
            await self.lock_actor()
        test_id = await self.session.scalar(
            select(TestVersion.test_id).where(TestVersion.id == version_id)
        )
        if test_id is None:
            raise AppError("TEST_VERSION_NOT_FOUND", "The test version does not exist.", 404)
        test = await self.session.scalar(
            select(Test)
            .where(Test.id == test_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        assert test is not None
        statement = (
            select(TestVersion)
            .where(TestVersion.id == version_id)
            .options(selectinload(TestVersion.test))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if mutable:
            statement = statement.options(selectinload(TestVersion.modules))
        version = await self.session.scalar(statement)
        if version is None:
            raise AppError("TEST_VERSION_NOT_FOUND", "The test version does not exist.", 404)
        if mutable:
            await self.require_version_mutable(version)
        elif builder:
            await self.require_builder_read(version)
        return version

    async def version_access(self, version: TestVersion, *, classroom: bool = False) -> bool:
        test = await self.session.get(Test, version.test_id)
        if (
            test is None
            or test.archived_at is not None
            or version.status != VersionStatus.PUBLISHED
        ):
            return False
        if test.origin == TestOrigin.ADMIN:
            return True
        scopes = (
            {ModerationScope.PUBLIC, ModerationScope.CLASSROOM}
            if classroom
            else {ModerationScope.PUBLIC}
        )
        return (
            await self.session.scalar(
                select(TestVersionModeration.id)
                .where(
                    TestVersionModeration.test_version_id == version.id,
                    TestVersionModeration.scope.in_(scopes),
                    TestVersionModeration.status == ModerationStatus.APPROVED,
                )
                .limit(1)
            )
            is not None
        )

    async def public_version_ids(self, tests: list[Test]) -> set[UUID]:
        """Resolve library visibility with one moderation query for the listed tests."""
        public = {
            version.id
            for test in tests
            if test.archived_at is None and test.origin == TestOrigin.ADMIN
            for version in test.versions
            if version.status == VersionStatus.PUBLISHED
        }
        teacher_version_ids = [
            version.id
            for test in tests
            if test.archived_at is None and test.origin == TestOrigin.TEACHER
            for version in test.versions
            if version.status == VersionStatus.PUBLISHED
        ]
        if teacher_version_ids:
            approved = await self.session.scalars(
                select(TestVersionModeration.test_version_id).where(
                    TestVersionModeration.test_version_id.in_(teacher_version_ids),
                    TestVersionModeration.scope == ModerationScope.PUBLIC,
                    TestVersionModeration.status == ModerationStatus.APPROVED,
                )
            )
            public.update(approved)
        return public

    async def require_version_read(self, version: TestVersion) -> None:
        test = await self.session.get(Test, version.test_id)
        assert test is not None
        if self.actor.role == UserRole.ADMIN or (
            self.actor.role == UserRole.TEACHER and test.owner_user_id == self.actor.id
        ):
            return
        if not await self.version_access(version):
            raise AppError(
                "TEST_VERSION_NOT_FOUND", "The requested test version does not exist.", 404
            )

    async def require_admin_moderation(self) -> None:
        if self.actor.role != UserRole.ADMIN:
            raise AppError("ADMIN_REQUIRED", "Administrator access is required.", 403)

    async def require_classroom_manage(self, classroom: Classroom) -> None:
        if self.actor.role == UserRole.ADMIN:
            return
        if self.actor.role != UserRole.TEACHER:
            raise AppError("TEACHER_REQUIRED", "Teacher access is required.", 403)
        if classroom.teacher_id != self.actor.id:
            raise AppError(
                "CLASSROOM_OWNERSHIP_REQUIRED", "Only the classroom owner may manage it.", 403
            )

    async def require_assignment_view(self, assignment: ClassroomAssignment) -> None:
        classroom = await self.session.get(Classroom, assignment.classroom_id)
        if classroom is None:
            raise AppError("CLASSROOM_NOT_FOUND", "The classroom does not exist.", 404)
        await self.require_classroom_manage(classroom)
