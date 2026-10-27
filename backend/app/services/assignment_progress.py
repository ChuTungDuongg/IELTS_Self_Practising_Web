"""Private progress, SQL-paginated teacher cohort and assignment-derived agenda."""

from datetime import timedelta

from sqlalchemy import and_, case, func, literal, or_, select, union_all

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import (
    ClassroomAssignment,
    ClassroomMembership,
    Test,
    TestVersion,
    TestVersionModeration,
)
from app.models.assignment_scheduling import ClassroomAssignmentExtension
from app.models.enums import ModerationScope, ModerationStatus
from app.repositories.assignment_progress import AssignmentProgressRepository
from app.schemas.assignment_scheduling import (
    AssignmentProgress,
    CalendarEvent,
    CalendarPage,
    ExtensionResponse,
    MonitoringPage,
    MonitoringStudent,
    ProgressPage,
    SchedulePolicy,
)
from app.services.assignment_policy import resolve_policy, start_denial
from app.services.assignment_scheduling import AssignmentSchedulingService


def present_progress(
    assignment,
    policy,
    summary,
    *,
    now,
    classroom_active,
    member,
    joined_at=None,
    version_eligible=True,
):
    summary = summary or {}
    used = summary.get("used", 0) or 0
    denial = start_denial(policy, now, used)
    archived = not classroom_active or assignment.status != "ACTIVE"
    if archived:
        denial = "CLASSROOM_ARCHIVED" if not classroom_active else "ASSIGNMENT_ARCHIVED"
    elif not member:
        denial = "ACTIVE_MEMBERSHIP_REQUIRED"
    elif not version_eligible:
        denial = "VERSION_NOT_CLASSROOM_APPROVED"
    availability = (
        "ARCHIVED"
        if archived
        else "SCHEDULED"
        if policy.available_from and now < policy.available_from
        else "CLOSED"
        if (policy.cutoff_at and now > policy.cutoff_at)
        or (not policy.allow_late_submission and policy.due_at and now > policy.due_at)
        else "OVERDUE"
        if policy.due_at and now > policy.due_at
        else "OPEN"
    )
    closure = min(
        [
            value
            for value in [
                policy.cutoff_at,
                policy.due_at if not policy.allow_late_submission else None,
            ]
            if value
        ],
        default=None,
    )
    missed = closure is not None and now > closure and (joined_at is None or joined_at <= closure)
    status = (
        summary.get("decision")
        if summary.get("accepted")
        else "IN_PROGRESS"
        if summary.get("active_id")
        else summary.get("decision") or ("MISSED" if missed else "NOT_STARTED")
    )
    return AssignmentProgress(
        assignment_id=assignment.id,
        availability_status=availability,
        submission_status=status,
        available_from=policy.available_from,
        effective_due_at=policy.due_at,
        effective_cutoff_at=policy.cutoff_at,
        max_attempts=policy.max_attempts,
        attempts_used=used,
        attempts_remaining=max(0, policy.max_attempts - used)
        if policy.max_attempts is not None
        else None,
        can_start=denial is None,
        start_blocked_reason=denial,
        can_resume=summary.get("active_id") is not None,
        latest_attempt_id=summary.get("latest_id")
        if summary.get("latest_kind") == "ATTEMPT"
        else None,
        latest_session_id=summary.get("latest_id")
        if summary.get("latest_kind") == "SESSION"
        else None,
        resume_attempt_id=summary.get("active_id")
        if summary.get("active_kind") == "ATTEMPT"
        else None,
        resume_session_id=summary.get("active_id")
        if summary.get("active_kind") == "SESSION"
        else None,
        result_attempt_id=summary.get("result_attempt_id"),
        completed_at=summary.get("completed_at"),
        late=bool(summary.get("late")),
        accepted=bool(summary.get("accepted")),
        historical=not member,
    )


class AssignmentProgressService:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor
        self.scheduling = AssignmentSchedulingService(session, actor)
        self.repository = AssignmentProgressRepository(session)

    async def _student_rows(self, room, assignments, now):
        ids = [assignment.id for assignment in assignments]
        if not ids:
            return []
        summaries = await self.repository.student_summaries(ids, self.actor.id)
        extensions = {
            row.assignment_id: row
            for row in await self.session.scalars(
                select(ClassroomAssignmentExtension).where(
                    ClassroomAssignmentExtension.assignment_id.in_(ids),
                    ClassroomAssignmentExtension.student_id == self.actor.id,
                )
            )
        }
        membership = (
            await self.session.execute(
                select(
                    func.coalesce(
                        func.min(ClassroomMembership.joined_at).filter(
                            ClassroomMembership.left_at.is_(None)
                        ),
                        func.min(ClassroomMembership.joined_at),
                    ),
                    func.bool_or(ClassroomMembership.left_at.is_(None)),
                ).where(
                    ClassroomMembership.classroom_id == room.id,
                    ClassroomMembership.user_id == self.actor.id,
                )
            )
        ).one()
        approved = select(TestVersionModeration.test_version_id).where(
            TestVersionModeration.scope.in_([ModerationScope.PUBLIC, ModerationScope.CLASSROOM]),
            TestVersionModeration.status == ModerationStatus.APPROVED,
        )
        eligible = set(
            await self.session.scalars(
                select(TestVersion.id)
                .join(Test, Test.id == TestVersion.test_id)
                .where(
                    TestVersion.id.in_([a.test_version_id for a in assignments]),
                    TestVersion.status == "PUBLISHED",
                    Test.archived_at.is_(None),
                    or_(Test.origin == "ADMIN", TestVersion.id.in_(approved)),
                )
            )
        )
        return [
            present_progress(
                a,
                resolve_policy(SchedulePolicy.model_validate(a), extensions.get(a.id)),
                summaries.get(a.id),
                now=now,
                classroom_active=room.status == "ACTIVE",
                member=bool(membership[1]),
                joined_at=membership[0],
                version_eligible=a.test_version_id in eligible,
            )
            for a in assignments
        ]

    async def student(
        self, classroom_id, *, assignment_id=None, assignment_ids=None, limit=100, offset=0
    ):
        async with self.session.begin():
            room = await self.scheduling.access.room(classroom_id)
            query = select(ClassroomAssignment).where(ClassroomAssignment.classroom_id == room.id)
            if assignment_id is not None:
                query = query.where(ClassroomAssignment.id == assignment_id)
            if assignment_ids is not None:
                query = query.where(ClassroomAssignment.id.in_(assignment_ids))
            total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
            rows = list(
                await self.session.scalars(
                    query.order_by(ClassroomAssignment.created_at.desc(), ClassroomAssignment.id)
                    .limit(limit)
                    .offset(offset)
                )
            )
            if assignment_id is not None and not rows:
                raise AppError(
                    "ASSIGNMENT_NOT_ACCESSIBLE", "Assignment not found in this classroom.", 404
                )
            return ProgressPage(
                items=await self._student_rows(room, rows, TimerService.now()), total=total
            )

    async def monitor(
        self, classroom_id, assignment_id, *, limit=50, offset=0, status="ALL", search=""
    ):
        async with self.session.begin():
            room, assignment = await self.scheduling.assignment(classroom_id, assignment_id)
            if not self.scheduling.access.staff(room):
                raise AppError("CLASSROOM_OWNERSHIP_REQUIRED", "Staff oversight is required.", 403)
            now = TimerService.now()
            all_rows = self.repository.monitoring_query(assignment, now).subquery("monitor")
            summary = dict(
                (
                    await self.session.execute(
                        select(all_rows.c.status, func.count()).group_by(all_rows.c.status)
                    )
                ).all()
            )
            summary["eligible_students"] = (
                await self.session.scalar(
                    select(func.count()).select_from(all_rows).where(all_rows.c.eligible)
                )
                or 0
            )
            query = select(all_rows)
            if status == "SUBMITTED":
                query = query.where(
                    all_rows.c.status.in_(
                        ["SUBMITTED_ON_TIME", "SUBMITTED_LATE", "SUBMITTED_NOT_ACCEPTED"]
                    )
                )
            elif status != "ALL":
                query = query.where(all_rows.c.status == status)
            if search.strip():
                query = query.where(
                    all_rows.c.display_name.ilike(
                        "%" + search.strip().replace("%", r"\%").replace("_", r"\_") + "%",
                        escape="\\",
                    )
                )
            total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
            rows = (
                (
                    await self.session.execute(
                        query.order_by(all_rows.c.display_name, all_rows.c.student_id)
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .mappings()
                .all()
            )
            ext_ids = [row["extension_id"] for row in rows if row["extension_id"]]
            extensions = {
                row.id: row
                for row in await self.session.scalars(
                    select(ClassroomAssignmentExtension).where(
                        ClassroomAssignmentExtension.id.in_(ext_ids)
                    )
                )
            }
            items = []
            for row in rows:
                extension = extensions.get(row["extension_id"])
                progress = present_progress(
                    assignment,
                    resolve_policy(SchedulePolicy.model_validate(assignment), extension),
                    row,
                    now=now,
                    classroom_active=room.status == "ACTIVE",
                    member=row["active_member"],
                    joined_at=row["joined_at"],
                )
                items.append(
                    MonitoringStudent(
                        student_id=row["student_id"],
                        display_name=row["display_name"],
                        joined_at=row["joined_at"],
                        active_member=row["active_member"],
                        progress=progress,
                        extension=ExtensionResponse.model_validate(extension)
                        if extension
                        else None,
                    )
                )
            return MonitoringPage(items=items, total=total, summary=summary)

    async def calendar(self, classroom_id, start, end, *, limit=100, offset=0):
        if end <= start or end - start > timedelta(days=93):
            raise AppError("CALENDAR_RANGE_INVALID", "Choose a date range of at most 93 days.", 422)
        async with self.session.begin():
            room = await self.scheduling.access.room(classroom_id)
            staff = self.scheduling.access.staff(room)
            a = ClassroomAssignment
            e = ClassroomAssignmentExtension
            override = and_(e.id.is_not(None), ~e.revoked)
            dates = {
                "AVAILABLE": a.available_from,
                "DUE": a.due_at
                if staff
                else case((override & e.override_due, e.due_at_override), else_=a.due_at),
                "CUTOFF": a.cutoff_at
                if staff
                else case((override & e.override_cutoff, e.cutoff_at_override), else_=a.cutoff_at),
            }
            branches = []
            for kind, instant in dates.items():
                query = (
                    select(
                        a.id.label("assignment_id"),
                        a.title,
                        literal(kind).label("kind"),
                        instant.label("at"),
                    )
                    .outerjoin(e, and_(e.assignment_id == a.id, e.student_id == self.actor.id))
                    .where(
                        a.classroom_id == room.id,
                        a.status == "ACTIVE",
                        instant >= start,
                        instant < end,
                    )
                )
                branches.append(query)
            events = union_all(*branches).subquery("calendar")
            total = await self.session.scalar(select(func.count()).select_from(events))
            rows = (
                await self.session.execute(
                    select(events)
                    .order_by(events.c.at, events.c.assignment_id, events.c.kind)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            assignments = list(
                await self.session.scalars(
                    select(a).where(a.id.in_({row.assignment_id for row in rows}))
                )
            )
            progress = (
                {}
                if staff
                else {
                    row.assignment_id: row
                    for row in await self._student_rows(room, assignments, TimerService.now())
                }
            )
            return CalendarPage(
                items=[
                    CalendarEvent(
                        assignment_id=row.assignment_id,
                        title=row.title or "",
                        kind=row.kind,
                        at=row.at,
                        progress=progress.get(row.assignment_id),
                    )
                    for row in rows
                ],
                total=total,
            )
