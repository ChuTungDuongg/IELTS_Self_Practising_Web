from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.database import get_session
from app.schemas.classroom_grades import (
    AcademicProfile,
    GradebookPage,
    GradeColumn,
    GradePolicyUpdate,
)
from app.schemas.classroom_staff import StaffInvite, StaffResponse, StaffUpdate
from app.schemas.tests import TestSummary, VersionSummary
from app.services.classroom_grades import ClassroomGradeService
from app.services.classroom_staff import ClassroomStaffService

router = APIRouter(tags=["classroom-lms"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/classrooms/{classroom_id}/assignable-tests", response_model=list[TestSummary])
async def assignable_tests(classroom_id: UUID, user: CurrentUser, session: Session):
    from sqlalchemy import or_, select
    from sqlalchemy.orm import selectinload

    from app.models import Test, TestVersion, TestVersionModeration
    from app.services.classroom_capabilities import Capability

    async with session.begin():
        room = await ClassroomGradeService(session, user).authorize(
            classroom_id, Capability.CLASSROOM if user.role == "ADMIN" else Capability.ASSIGNMENTS
        )
        approved = select(TestVersionModeration.test_version_id).where(
            TestVersionModeration.status == "APPROVED",
            TestVersionModeration.scope.in_(["CLASSROOM", "PUBLIC"]),
        )
        versions = list(
            await session.scalars(
                select(TestVersion)
                .join(Test, Test.id == TestVersion.test_id)
                .where(
                    TestVersion.status == "PUBLISHED",
                    Test.archived_at.is_(None),
                    or_(Test.origin == "ADMIN", Test.owner_user_id == room.teacher_id),
                    or_(Test.origin == "ADMIN", TestVersion.id.in_(approved)),
                )
                .options(selectinload(TestVersion.test))
                .order_by(Test.title, TestVersion.id)
                .limit(200)
            )
        )
        grouped = {}
        for version in versions:
            test = version.test
            if test.id not in grouped:
                grouped[test.id] = TestSummary(
                    **{
                        key: getattr(test, key)
                        for key in TestSummary.model_fields
                        if key not in {"versions", "owner_display_name"}
                    },
                    versions=[],
                )
            grouped[test.id].versions.append(VersionSummary.model_validate(version))
        return list(grouped.values())


@router.get("/me/classroom-staff-invitations", response_model=list[StaffResponse])
async def my_staff(user: CurrentUser, session: Session):
    return await ClassroomStaffService(session, user).mine()


@router.get("/classrooms/{classroom_id}/staff", response_model=list[StaffResponse])
async def staff(classroom_id: UUID, user: CurrentUser, session: Session):
    return await ClassroomStaffService(session, user).list(classroom_id)


@router.post("/classrooms/{classroom_id}/staff", response_model=StaffResponse, status_code=201)
async def invite_staff(classroom_id: UUID, body: StaffInvite, user: CurrentUser, session: Session):
    return await ClassroomStaffService(session, user).invite(classroom_id, body)


@router.patch("/classrooms/{classroom_id}/staff/{staff_id}", response_model=StaffResponse)
async def update_staff(
    classroom_id: UUID, staff_id: UUID, body: StaffUpdate, user: CurrentUser, session: Session
):
    return await ClassroomStaffService(session, user).change(classroom_id, staff_id, data=body)


@router.delete("/classrooms/{classroom_id}/staff/{staff_id}", response_model=StaffResponse)
async def revoke_staff(classroom_id: UUID, staff_id: UUID, user: CurrentUser, session: Session):
    return await ClassroomStaffService(session, user).change(classroom_id, staff_id, revoke=True)


@router.post("/classrooms/{classroom_id}/staff/{staff_id}/{action}", response_model=StaffResponse)
async def respond_staff(
    classroom_id: UUID,
    staff_id: UUID,
    action: Literal["accept", "decline"],
    user: CurrentUser,
    session: Session,
):
    return await ClassroomStaffService(session, user).change(
        classroom_id, staff_id, response=action == "accept"
    )


class GradeFilters:
    def __init__(
        self,
        search: str = Query("", max_length=100),
        assignment_id: UUID | None = None,
        skill: Literal["READING", "LISTENING", "WRITING", "SPEAKING", "FULL_MOCK"] | None = None,
        status: Literal[
            "ALL",
            "NOT_STARTED",
            "IN_PROGRESS",
            "SUBMITTED",
            "SUBMITTED_ON_TIME",
            "SUBMITTED_LATE",
            "SUBMITTED_NOT_ACCEPTED",
            "MISSED",
        ] = "ALL",
        sort: Literal["name", "score_asc", "score_desc"] = "name",
        offset: int = Query(0, ge=0),
        assignment_offset: int = Query(0, ge=0),
    ):
        self.values = dict(
            search=search,
            assignment_id=assignment_id,
            skill=skill,
            status=status,
            sort=sort,
            offset=offset,
            assignment_offset=assignment_offset,
        )


@router.get("/classrooms/{classroom_id}/gradebook", response_model=GradebookPage)
async def gradebook(
    classroom_id: UUID,
    user: CurrentUser,
    session: Session,
    filters: Annotated[GradeFilters, Depends()],
    limit: int = Query(30, ge=1, le=100),
):
    return await ClassroomGradeService(session, user).page(
        classroom_id, limit=limit, **filters.values
    )


@router.get("/classrooms/{classroom_id}/gradebook/export")
async def export_gradebook(
    classroom_id: UUID,
    user: CurrentUser,
    session: Session,
    filters: Annotated[GradeFilters, Depends()],
):
    content = await ClassroomGradeService(session, user).export(classroom_id, **filters.values)
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="classroom-gradebook.csv"',
            "Cache-Control": "private, no-store",
        },
    )


@router.patch(
    "/classrooms/{classroom_id}/assignments/{assignment_id}/grade-policy",
    response_model=GradeColumn,
)
async def grade_policy(
    classroom_id: UUID,
    assignment_id: UUID,
    body: GradePolicyUpdate,
    user: CurrentUser,
    session: Session,
):
    return await ClassroomGradeService(session, user).policy(classroom_id, assignment_id, body)


@router.get(
    "/classrooms/{classroom_id}/students/{student_id}/academic-profile",
    response_model=AcademicProfile,
)
async def academic_profile(
    classroom_id: UUID,
    student_id: UUID,
    user: CurrentUser,
    session: Session,
    assignment_offset: int = Query(0, ge=0),
    history_offset: int = Query(0, ge=0),
):
    return await ClassroomGradeService(session, user).profile(
        classroom_id, student_id, assignment_offset=assignment_offset, history_offset=history_offset
    )
