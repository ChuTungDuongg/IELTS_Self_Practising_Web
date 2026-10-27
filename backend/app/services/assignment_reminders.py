"""Bounded, idempotent reminders; invoked by an external one-shot scheduler."""

from datetime import timedelta

from sqlalchemy import String, and_, case, cast, func, or_, select

from app.domains.timers import TimerService
from app.models import Classroom, ClassroomAssignment, ClassroomMembership, Notification, User
from app.models.assignment_scheduling import ClassroomAssignmentExtension
from app.repositories.assignment_progress import AssignmentProgressRepository, aggregate_roots
from app.services.assignment_scheduling import effective_policy, notify_assignment


async def generate_reminders(session, *, limit=100, now=None):
    if not 1 <= limit <= 1000:
        raise ValueError("Reminder limit must be between 1 and 1000")
    now = now or TimerService.now()
    a, e = ClassroomAssignment, ClassroomAssignmentExtension
    active_ids = (
        select(a.id)
        .join(Classroom, Classroom.id == a.classroom_id)
        .where(a.status == "ACTIVE", Classroom.status == "ACTIVE")
    )
    summary = aggregate_roots(active_ids)
    due = case((and_(e.override_due, ~e.revoked), e.due_at_override), else_=a.due_at)
    kind = case((due < now, "ASSIGNMENT_OVERDUE"), else_="ASSIGNMENT_DUE_SOON")
    key = cast(func.extract("epoch", due), String)
    sent = (
        select(Notification.id)
        .where(
            Notification.user_id == ClassroomMembership.user_id,
            cast(Notification.type, String) == kind,
            Notification.payload_json["assignment_id"].astext == cast(a.id, String),
            Notification.payload_json["reminder_key"].astext == key,
        )
        .correlate(a, e, ClassroomMembership)
        .exists()
    )
    query = (
        select(a.id, ClassroomMembership.user_id)
        .join(Classroom, Classroom.id == a.classroom_id)
        .join(ClassroomMembership, ClassroomMembership.classroom_id == a.classroom_id)
        .join(User, User.id == ClassroomMembership.user_id)
        .outerjoin(e, and_(e.assignment_id == a.id, e.student_id == ClassroomMembership.user_id))
        .outerjoin(
            summary,
            and_(summary.c.assignment_id == a.id, summary.c.user_id == ClassroomMembership.user_id),
        )
        .where(
            a.status == "ACTIVE",
            Classroom.status == "ACTIVE",
            ClassroomMembership.left_at.is_(None),
            User.is_active.is_(True),
            due.is_not(None),
            due <= now + timedelta(hours=24),
            or_(a.available_from.is_(None), a.available_from <= now),
            ClassroomMembership.joined_at <= due,
            ~func.coalesce(summary.c.accepted, False),
            ~sent,
        )
        .order_by(a.classroom_id, a.id, ClassroomMembership.user_id)
        .limit(limit)
    )
    async with session.begin():
        candidates = (await session.execute(query)).all()
        emitted = 0
        for assignment_id, student_id in candidates:
            classroom_id = await session.scalar(select(a.classroom_id).where(a.id == assignment_id))
            room = await session.scalar(
                select(Classroom)
                .where(Classroom.id == classroom_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            assignment = await session.scalar(
                select(a)
                .where(a.id == assignment_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            member = await session.scalar(
                select(ClassroomMembership).where(
                    ClassroomMembership.classroom_id == classroom_id,
                    ClassroomMembership.user_id == student_id,
                    ClassroomMembership.left_at.is_(None),
                )
            )
            if room.status != "ACTIVE" or assignment.status != "ACTIVE" or not member:
                continue
            policy, _ = await effective_policy(session, assignment, student_id)
            if (
                policy.due_at is None
                or policy.due_at > now + timedelta(hours=24)
                or member.joined_at > policy.due_at
            ):
                continue
            current = (
                await AssignmentProgressRepository(session).student_summaries(
                    [assignment.id], student_id
                )
            ).get(assignment.id, {})
            if current.get("accepted"):
                continue
            event_kind = "ASSIGNMENT_OVERDUE" if now > policy.due_at else "ASSIGNMENT_DUE_SOON"
            event_key = f"{policy.due_at.timestamp():.6f}"
            await notify_assignment(
                session,
                assignment,
                event_kind,
                event_key,
                student_id=student_id,
                extra={"reminder_key": event_key, "due_at": policy.due_at.isoformat()},
            )
            emitted += 1
        return {
            "processed": len(candidates),
            "emitted": emitted,
            "batch_full": len(candidates) == limit,
        }
