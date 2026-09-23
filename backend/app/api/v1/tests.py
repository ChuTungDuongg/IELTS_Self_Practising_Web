from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser, CurrentUser
from app.api.v1.presenters import present_version
from app.core.database import get_session
from app.schemas.common import ValidationResult
from app.schemas.tests import (
    TestCreate,
    TestDeleteResult,
    TestSummary,
    VersionCreate,
    VersionDetail,
)
from app.services.tests import TestService

router = APIRouter(tags=["tests"])


@router.get("/tests", response_model=list[TestSummary])
async def list_tests(
    user: CurrentUser,
    archived: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[TestSummary]:
    records = await TestService(session).list_tests(archived=archived)
    summaries = [TestSummary.model_validate(record) for record in records]
    if user.role.value == "ADMIN":
        return summaries
    return [
        summary.model_copy(
            update={
                "versions": [item for item in summary.versions if item.status.value == "PUBLISHED"]
            }
        )
        for summary in summaries
        if any(item.status.value == "PUBLISHED" for item in summary.versions)
    ]


@router.post("/tests", response_model=TestSummary, status_code=status.HTTP_201_CREATED)
async def create_test(
    body: TestCreate, _: AdminUser, session: AsyncSession = Depends(get_session)
) -> TestSummary:
    return TestSummary.model_validate(await TestService(session).create_test(body))


@router.get("/tests/{test_id}", response_model=TestSummary)
async def get_test(
    test_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TestSummary:
    summary = TestSummary.model_validate(await TestService(session).get_test(test_id))
    if user.role.value == "ADMIN":
        return summary
    published = [item for item in summary.versions if item.status.value == "PUBLISHED"]
    if not published:
        from app.core.exceptions import AppError

        raise AppError("TEST_NOT_FOUND", "The requested test does not exist.", 404)
    return summary.model_copy(update={"versions": published})


@router.delete("/tests/{test_id}", response_model=TestDeleteResult)
async def delete_test(
    test_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)
) -> TestDeleteResult:
    return await TestService(session).delete_test(test_id)


@router.post("/tests/{test_id}/restore", response_model=TestSummary)
async def restore_test(
    test_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)
) -> TestSummary:
    return TestSummary.model_validate(await TestService(session).restore_test(test_id))


@router.delete("/tests/{test_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_test(
    test_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)
) -> None:
    await TestService(session).permanently_delete_test(test_id)


@router.delete("/test-modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)
) -> None:
    await TestService(session).delete_module(module_id)


@router.post(
    "/tests/{test_id}/versions",
    response_model=VersionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    test_id: UUID,
    body: VersionCreate,
    _: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> VersionDetail:
    version = await TestService(session).create_version(test_id, body)
    return present_version(version)


@router.delete("/tests/{test_id}/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    test_id: UUID,
    version_id: UUID,
    _: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> None:
    await TestService(session).delete_draft(test_id, version_id)


@router.get("/test-versions/{version_id}", response_model=VersionDetail)
async def get_version(
    version_id: UUID, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> VersionDetail:
    version = await TestService(session).get_version(version_id)
    if user.role.value != "ADMIN":
        from app.core.exceptions import AppError
        from app.models.enums import VersionStatus

        if version.status != VersionStatus.PUBLISHED:
            raise AppError(
                "TEST_VERSION_NOT_FOUND", "The requested test version does not exist.", 404
            )
    return present_version(version)


@router.post("/test-versions/{version_id}/validate", response_model=ValidationResult)
async def validate_version(
    version_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)
) -> ValidationResult:
    return await TestService(session).validate(version_id)


@router.post("/test-versions/{version_id}/publish", response_model=VersionDetail)
async def publish_version(
    version_id: UUID, _: AdminUser, session: AsyncSession = Depends(get_session)
) -> VersionDetail:
    return present_version(await TestService(session).publish(version_id))
