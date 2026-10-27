from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser, CurrentUser
from app.api.v1.presenters import present_version
from app.core.database import get_session
from app.core.exceptions import AppError
from app.models import User
from app.models.enums import UserRole
from app.schemas.common import ValidationResult
from app.schemas.tests import (
    TestCreate,
    TestDeleteResult,
    TestSummary,
    TestUpdate,
    VersionCreate,
    VersionDetail,
)
from app.services.tests import TestService

router = APIRouter(tags=["tests"])


@router.get("/tests", response_model=list[TestSummary])
async def list_tests(
    user: CurrentUser,
    archived: bool = False,
    public_only: bool = False,
    include_details: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[TestSummary]:
    service = TestService(session, actor=user)
    if include_details and public_only and not archived:
        summaries, versions = await service.list_public_catalog()
        # The same key-free DTO as GET /test-versions/{id}?public_only=true.
        details = {version.test_id: present_version(version) for version in versions}
        return [
            summary.model_copy(update={"published_detail": details.get(summary.id)})
            for summary in summaries
        ]
    return await service.list_summaries(archived=archived, public_only=public_only)


@router.post("/tests", response_model=TestSummary, status_code=status.HTTP_201_CREATED)
async def create_test(
    body: TestCreate, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TestSummary:
    return TestSummary.model_validate(await TestService(session, actor=user).create_test(body))


@router.get("/tests/{test_id}", response_model=TestSummary)
async def get_test(
    test_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TestSummary:
    service = TestService(session, actor=user)
    record = await service.get_test(test_id)
    summary = TestSummary.model_validate(record)
    if record.owner_user_id is not None:
        owner = await session.get(User, record.owner_user_id)
        summary.owner_display_name = owner.display_name if owner else None
    if user.role == UserRole.ADMIN or (
        user.role == UserRole.TEACHER and record.owner_user_id == user.id
    ):
        return summary
    versions = [
        item
        for item, version in zip(summary.versions, record.versions, strict=True)
        if await service.policy.version_access(version)
    ]
    return summary.model_copy(update={"versions": versions})


@router.patch("/tests/{test_id}", response_model=TestSummary)
async def update_test(
    test_id: UUID, body: TestUpdate, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TestSummary:
    return TestSummary.model_validate(
        await TestService(session, actor=user).update_test(test_id, body)
    )


@router.delete("/tests/{test_id}", response_model=TestDeleteResult)
async def delete_test(
    test_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TestDeleteResult:
    return await TestService(session, actor=user).delete_test(test_id)


@router.post("/tests/{test_id}/restore", response_model=TestSummary)
async def restore_test(
    test_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TestSummary:
    return TestSummary.model_validate(await TestService(session, actor=user).restore_test(test_id))


@router.delete("/tests/{test_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_test(
    test_id: UUID, user: AdminUser, session: AsyncSession = Depends(get_session)
) -> None:
    await TestService(session, actor=user).permanently_delete_test(test_id)


@router.delete("/test-modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> None:
    await TestService(session, actor=user).delete_module(module_id)


@router.post(
    "/tests/{test_id}/versions",
    response_model=VersionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    test_id: UUID,
    body: VersionCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> VersionDetail:
    version = await TestService(session, actor=user).create_version(test_id, body)
    return present_version(version)


@router.delete("/tests/{test_id}/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    test_id: UUID,
    version_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> None:
    await TestService(session, actor=user).delete_draft(test_id, version_id)


@router.get("/test-versions/{version_id}", response_model=VersionDetail)
async def get_version(
    version_id: UUID,
    user: CurrentUser,
    public_only: bool = False,
    session: AsyncSession = Depends(get_session),
) -> VersionDetail:
    service = TestService(session, actor=user)
    version = await service.get_version(version_id)
    if public_only:
        if not await service.policy.version_access(version):
            raise AppError(
                "TEST_VERSION_NOT_FOUND", "The requested test version does not exist.", 404
            )
    else:
        await service.policy.require_version_read(version)
    return present_version(version)


@router.post("/test-versions/{version_id}/validate", response_model=ValidationResult)
async def validate_version(
    version_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> ValidationResult:
    return await TestService(session, actor=user).validate(version_id)


@router.post("/test-versions/{version_id}/publish", response_model=VersionDetail)
async def publish_version(
    version_id: UUID, user: AdminUser, session: AsyncSession = Depends(get_session)
) -> VersionDetail:
    return present_version(await TestService(session, actor=user).publish(version_id))
