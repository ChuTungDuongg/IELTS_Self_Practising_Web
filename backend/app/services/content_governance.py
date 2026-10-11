from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import TestVersion, TestVersionModeration, User
from app.models.enums import ModerationScope, ModerationStatus, TestOrigin, UserRole, VersionStatus
from app.repositories.content_governance import ContentGovernanceRepository
from app.repositories.tests import version_detail_query
from app.schemas.content_governance import ModerationDetail
from app.services.access_policy import AccessPolicy
from app.services.tests import TestService


class ContentGovernanceService:
    def __init__(self, session: AsyncSession, actor: User, *, notifier=None):
        self.session = session
        self.policy = AccessPolicy(session, actor)
        self.repository = ContentGovernanceRepository(session)
        self.notifier = notifier

    async def submit_moderation(self, version_id: UUID, scope: ModerationScope, note: str | None):
        async with self.session.begin():
            await self.policy.lock_actor()
            version = await self.policy.lock_version(version_id)
            await self.policy.require_test_edit(version.test)
            if (
                self.policy.actor.role != UserRole.TEACHER
                or version.test.origin != TestOrigin.TEACHER
            ):
                raise AppError(
                    "TEACHER_REQUIRED", "Only the teacher owner can submit content.", 403
                )
            if version.test.archived_at or version.status == VersionStatus.ARCHIVED:
                raise AppError("VERSION_IMMUTABLE", "Archived content cannot be submitted.", 409)
            existing = await self.session.scalar(
                select(TestVersionModeration.id).where(
                    TestVersionModeration.test_version_id == version_id,
                    TestVersionModeration.scope == scope,
                    TestVersionModeration.status.in_(
                        [ModerationStatus.PENDING, ModerationStatus.APPROVED]
                    ),
                )
            )
            if existing:
                raise AppError(
                    "MODERATION_ALREADY_PENDING",
                    "This scope already has a pending request or active approval.",
                    409,
                )
            request = TestVersionModeration(
                test_version_id=version_id,
                scope=scope,
                submitted_by_user_id=self.policy.actor_id,
                submit_note=note,
            )
            self.session.add(request)
            await self.session.flush()
            response = await self._present(request)
        return response

    async def cancel_request(self, request_id: UUID):
        async with self.session.begin():
            version, request = await self._lock_request(request_id)
            await self.policy.require_test_edit(version.test)
            if request.submitted_by_user_id != self.policy.actor_id:
                raise AppError(
                    "TEST_OWNERSHIP_REQUIRED", "Only the submitter may cancel this request.", 403
                )
            self._pending(request)
            request.status = ModerationStatus.CANCELLED
            request.cancelled_at = datetime.now(UTC)
            await self.session.flush()
            response = await self._present(request)
        return response

    async def approve(self, request_id: UUID, note: str | None):
        return await self._decide(request_id, note, approve=True)

    async def reject(self, request_id: UUID, note: str | None):
        return await self._decide(request_id, note, approve=False)

    async def _decide(self, request_id, note, *, approve):
        async with self.session.begin():
            version, request = await self._lock_request(request_id)
            await self.policy.require_admin_moderation()
            self._pending(request)
            if approve:
                if version.test.archived_at or version.status == VersionStatus.ARCHIVED:
                    raise AppError("VERSION_IMMUTABLE", "Archived content cannot be approved.", 409)
                validation = TestService.validate_version(version)
                if not validation.valid:
                    raise AppError(
                        "VALIDATION_FAILED",
                        "Resolve content validation errors before approval.",
                        422,
                    )
                if version.status == VersionStatus.DRAFT:
                    TestService._persist_normalized_draft(version)
                    previous = list(
                        await self.session.scalars(
                            select(TestVersion)
                            .where(
                                TestVersion.test_id == version.test_id,
                                TestVersion.status == VersionStatus.PUBLISHED,
                                TestVersion.id != version.id,
                            )
                            .with_for_update()
                        )
                    )
                    for item in previous:
                        item.status = VersionStatus.ARCHIVED
                    await self.session.flush()
                    version.status = VersionStatus.PUBLISHED
                    version.published_at = datetime.now(UTC)
            request.status = ModerationStatus.APPROVED if approve else ModerationStatus.REJECTED
            request.reviewed_at = datetime.now(UTC)
            request.reviewed_by_user_id = self.policy.actor_id
            request.review_note = note
            await self.session.flush()
            if self.notifier is not None:
                await self.notifier(request, version)
            else:
                from app.models.enums import NotificationEntityType, NotificationType
                from app.services.notifications import NotificationService

                event_type = NotificationType(f"TEST_{request.scope.value}_{request.status.value}")
                await NotificationService(self.session).create_once(
                    user_id=request.submitted_by_user_id,
                    type=event_type,
                    entity_type=NotificationEntityType.MODERATION,
                    entity_id=request.id,
                    payload={
                        "test_title": version.test.title,
                        "test_id": str(version.test_id),
                        "version_id": str(version.id),
                    },
                )
            response = await self._present(request)
        return response

    async def revoke(self, request_id: UUID, note: str | None):
        async with self.session.begin():
            _, request = await self._lock_request(request_id)
            await self.policy.require_admin_moderation()
            if request.status != ModerationStatus.APPROVED:
                raise AppError(
                    "MODERATION_ALREADY_RESOLVED", "Only an active approval may be revoked.", 409
                )
            request.status = ModerationStatus.REVOKED
            request.revoked_at = datetime.now(UTC)
            request.revoked_by_user_id = self.policy.actor_id
            request.revoke_reason = note
            await self.session.flush()
            response = await self._present(request)
        return response

    async def list_requests(self, *, version_id=None, status=None, limit=100, offset=0):
        if version_id:
            version = await self.session.scalar(
                version_detail_query().where(TestVersion.id == version_id)
            )
            if version is None:
                raise AppError("TEST_VERSION_NOT_FOUND", "Version not found.", 404)
            await self.policy.require_builder_read(version)
        else:
            await self.policy.require_admin_moderation()
        records = await self.repository.list(
            version_id=version_id, status=status, limit=limit, offset=offset
        )
        return [await self._present(item) for item in records]

    async def get_request(self, request_id):
        await self.policy.require_admin_moderation()
        request = await self.session.get(TestVersionModeration, request_id)
        if request is None:
            raise AppError("MODERATION_NOT_FOUND", "Request not found.", 404)
        return await self._present(request)

    async def _lock_request(self, request_id):
        await self.policy.lock_actor()
        version_id = await self.session.scalar(
            select(TestVersionModeration.test_version_id).where(
                TestVersionModeration.id == request_id
            )
        )
        if version_id is None:
            raise AppError("MODERATION_NOT_FOUND", "Request not found.", 404)
        await self.policy.lock_version(version_id)
        version = await self.session.scalar(
            version_detail_query()
            .where(TestVersion.id == version_id)
            .execution_options(populate_existing=True)
        )
        request = await self.session.scalar(
            select(TestVersionModeration)
            .where(TestVersionModeration.id == request_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return version, request

    @staticmethod
    def _pending(request):
        if request.status != ModerationStatus.PENDING:
            raise AppError("MODERATION_ALREADY_RESOLVED", "This request is no longer pending.", 409)

    async def _present(self, request):
        version = await self.session.scalar(
            version_detail_query().where(TestVersion.id == request.test_version_id)
        )
        return ModerationDetail.model_validate(request).model_copy(
            update={
                "test_id": version.test_id,
                "test_title": version.test.title,
                "version_number": version.version_number,
            }
        )
