"""Read authorization for assets referenced by immutable historical content."""

from uuid import UUID

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Asset,
    Attempt,
    Classroom,
    ClassroomAssignment,
    QuestionGroup,
    Test,
    TestModule,
    TestSession,
    TestVersion,
    User,
    WritingTask,
)
from app.models.enums import ModuleType, UserRole, VersionStatus
from app.services.access_policy import AccessPolicy


async def can_user_read_asset(
    session: AsyncSession, user_id: UUID, asset: Asset, *, actor: User | None = None
) -> bool:
    """Allow current published assets or an owned archived module's referenced asset."""
    version = await session.get(TestVersion, asset.test_version_id)
    if version is None:
        return False
    identity = actor or await session.get(User, user_id)
    if identity is None:
        return False
    policy = AccessPolicy(session, identity)
    if identity.role == UserRole.ADMIN:
        return True
    test = await session.get(Test, version.test_id)
    if identity.role == UserRole.TEACHER and test is not None and test.owner_user_id == user_id:
        return True
    if await policy.version_access(version):
        return True
    if version.status == VersionStatus.DRAFT:
        return False

    teacher_standalone = (
        select(1)
        .select_from(ClassroomAssignment)
        .join(Classroom)
        .where(
            ClassroomAssignment.id == Attempt.classroom_assignment_id,
            Classroom.teacher_id == user_id,
        )
        .exists()
    )
    teacher_session = (
        select(1)
        .select_from(TestSession)
        .join(ClassroomAssignment, TestSession.classroom_assignment_id == ClassroomAssignment.id)
        .join(Classroom)
        .where(
            TestSession.id == Attempt.test_session_id,
            Classroom.teacher_id == user_id,
        )
        .exists()
    )

    owned_module = and_(
        or_(
            Attempt.user_id == user_id,
            and_(identity.role == UserRole.TEACHER, or_(teacher_standalone, teacher_session)),
        ),
        Attempt.test_version_id == asset.test_version_id,
        Attempt.test_version_id == TestModule.test_version_id,
        # These columns use distinct PostgreSQL enum types.
        cast(Attempt.module_type, String) == cast(TestModule.module_type, String),
    )
    listening_audio = (
        select(1)
        .select_from(TestModule)
        .join(Attempt, owned_module)
        .where(
            TestModule.test_version_id == asset.test_version_id,
            TestModule.module_type == ModuleType.LISTENING,
            TestModule.audio_asset_id == asset.id,
        )
        .exists()
    )
    question_image = (
        select(1)
        .select_from(QuestionGroup)
        .join(TestModule, QuestionGroup.module_id == TestModule.id)
        .join(Attempt, owned_module)
        .where(
            TestModule.test_version_id == asset.test_version_id,
            QuestionGroup.image_asset_id == asset.id,
        )
        .exists()
    )
    writing_image = (
        select(1)
        .select_from(WritingTask)
        .join(TestModule, WritingTask.module_id == TestModule.id)
        .join(Attempt, owned_module)
        .where(
            TestModule.test_version_id == asset.test_version_id,
            TestModule.module_type == ModuleType.WRITING,
            WritingTask.image_asset_id == asset.id,
        )
        .exists()
    )
    return bool(await session.scalar(select(or_(listening_audio, question_image, writing_image))))
