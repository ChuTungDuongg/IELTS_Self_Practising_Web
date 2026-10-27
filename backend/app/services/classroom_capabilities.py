"""Typed classroom capability matrix; never grants global Builder access."""

from enum import StrEnum

from sqlalchemy import exists, select

from app.core.exceptions import AppError
from app.models.classroom_staff import ClassroomStaff


class Capability(StrEnum):
    CLASSROOM = "classroom.manage"
    STAFF = "staff.manage"
    MEMBERS = "members.manage"
    CONTENT = "content.manage"
    DISCUSSION = "discussion.moderate"
    ASSIGNMENTS = "assignments.manage"
    EXTEND = "assignments.extend"
    GRADES_VIEW = "grades.view"
    GRADES_EDIT = "grades.edit"
    ANALYTICS = "analytics.view"
    PLANS = "learning_plans.manage"


ALL = frozenset(Capability)
CO_TEACHER = ALL - {Capability.CLASSROOM, Capability.STAFF}
TA = frozenset({Capability.GRADES_VIEW, Capability.GRADES_EDIT})
OPTIONAL = {
    "content_manage": Capability.CONTENT,
    "discussion_moderate": Capability.DISCUSSION,
    "analytics_view": Capability.ANALYTICS,
    "learning_plans_manage": Capability.PLANS,
}


def active_staff_clause(classroom_id, user_id):
    return exists(select(ClassroomStaff.id).where(
        ClassroomStaff.classroom_id == classroom_id, ClassroomStaff.user_id == user_id,
        ClassroomStaff.status == "ACCEPTED",
    ))


async def resolve_capabilities(session, actor, room):
    if not actor.is_active:
        raise AppError("ACCOUNT_INACTIVE", "This account is inactive.", 403)
    if actor.role == "ADMIN":
        # Preserve oversight/administration, without authorship of another teacher's content.
        return "ADMIN", ALL - {Capability.STAFF, Capability.CONTENT, Capability.DISCUSSION,
                               Capability.ASSIGNMENTS, Capability.EXTEND, Capability.PLANS}
    if actor.role == "TEACHER" and actor.id == room.teacher_id:
        return "OWNER", ALL
    staff = await session.scalar(select(ClassroomStaff).where(
        ClassroomStaff.classroom_id == room.id, ClassroomStaff.user_id == actor.id,
        ClassroomStaff.status == "ACCEPTED",
    ).execution_options(populate_existing=True))
    if staff and staff.staff_role == "CO_TEACHER" and actor.role == "TEACHER":
        return staff.staff_role, CO_TEACHER
    if staff and staff.staff_role == "TEACHING_ASSISTANT" and actor.role in {"USER", "TEACHER"}:
        return staff.staff_role, TA | {value for field, value in OPTIONAL.items() if getattr(staff, field)}
    return "STUDENT", frozenset()


async def require_capability(session, actor, room, capability):
    role, capabilities = await resolve_capabilities(session, actor, room)
    if capability not in capabilities:
        raise AppError("CLASSROOM_CAPABILITY_REQUIRED", "This classroom operation is not permitted.", 403)
    return role
