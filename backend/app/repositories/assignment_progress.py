"""Root-only SQL aggregation, including policy effective at completion time."""

from sqlalchemy import Boolean, and_, case, func, literal, or_, select, true, type_coerce, union_all
from sqlalchemy.dialects.postgresql import aggregate_order_by

from app.models import Attempt, ClassroomAssignment, ClassroomMembership, TestSession, User
from app.models.assignment_scheduling import AssignmentPolicyEvent, ClassroomAssignmentExtension


def roots_query():
    submitted = ["SUBMITTED", "AUTO_SUBMITTED"]
    attempts = select(
        Attempt.id.label("root_id"),
        Attempt.classroom_assignment_id.label("assignment_id"),
        Attempt.user_id,
        Attempt.started_at,
        Attempt.finished_at,
        literal("ATTEMPT").label("kind"),
        Attempt.id.label("result_attempt_id"),
        Attempt.status.in_(submitted).label("successful"),
        Attempt.status.in_(["IN_PROGRESS", "PAUSED"]).label("active"),
    ).where(Attempt.classroom_assignment_id.is_not(None), Attempt.test_session_id.is_(None))
    child_count = (
        select(func.count())
        .where(Attempt.test_session_id == TestSession.id)
        .correlate(TestSession)
        .scalar_subquery()
    )
    bad_child = (
        select(Attempt.id)
        .where(Attempt.test_session_id == TestSession.id, Attempt.status.not_in(submitted))
        .correlate(TestSession)
        .exists()
    )
    result_id = (
        select(Attempt.id)
        .where(Attempt.test_session_id == TestSession.id)
        .order_by(Attempt.started_at.desc(), Attempt.id.desc())
        .limit(1)
        .correlate(TestSession)
        .scalar_subquery()
    )
    sessions = select(
        TestSession.id,
        TestSession.classroom_assignment_id,
        TestSession.user_id,
        TestSession.started_at,
        TestSession.finished_at,
        literal("SESSION"),
        result_id,
        and_(
            TestSession.status == "COMPLETED",
            ~bad_child,
            child_count == func.jsonb_array_length(TestSession.module_order_json),
        ),
        TestSession.status == "IN_PROGRESS",
    ).where(TestSession.classroom_assignment_id.is_not(None))
    return union_all(attempts, sessions)


def decision_roots(assignment_ids, student_ids=None):
    r = roots_query().subquery("roots")
    base = (
        select(
            AssignmentPolicyEvent.due_at,
            AssignmentPolicyEvent.cutoff_at,
            AssignmentPolicyEvent.allow_late_submission,
        )
        .where(
            AssignmentPolicyEvent.assignment_id == r.c.assignment_id,
            AssignmentPolicyEvent.student_id.is_(None),
            AssignmentPolicyEvent.effective_at <= r.c.finished_at,
        )
        .order_by(AssignmentPolicyEvent.effective_at.desc(), AssignmentPolicyEvent.revision.desc())
        .limit(1)
        .lateral("base_policy")
    )
    ext = (
        select(
            AssignmentPolicyEvent.due_at,
            AssignmentPolicyEvent.cutoff_at,
            AssignmentPolicyEvent.override_due,
            AssignmentPolicyEvent.override_cutoff,
            AssignmentPolicyEvent.revoked,
        )
        .where(
            AssignmentPolicyEvent.assignment_id == r.c.assignment_id,
            AssignmentPolicyEvent.student_id == r.c.user_id,
            AssignmentPolicyEvent.effective_at <= r.c.finished_at,
        )
        .order_by(AssignmentPolicyEvent.effective_at.desc(), AssignmentPolicyEvent.revision.desc())
        .limit(1)
        .lateral("student_policy")
    )
    due = case((and_(ext.c.override_due, ~ext.c.revoked), ext.c.due_at), else_=base.c.due_at)
    cutoff = case(
        (and_(ext.c.override_cutoff, ~ext.c.revoked), ext.c.cutoff_at), else_=base.c.cutoff_at
    )
    late = and_(due.is_not(None), r.c.finished_at > due)
    accepted = and_(
        r.c.successful,
        r.c.finished_at.is_not(None),
        or_(cutoff.is_(None), r.c.finished_at <= cutoff),
        or_(~late, func.coalesce(base.c.allow_late_submission, true())),
    )
    final_status = case(
        (accepted & late, "SUBMITTED_LATE"),
        (accepted, "SUBMITTED_ON_TIME"),
        else_="SUBMITTED_NOT_ACCEPTED",
    )
    annotated = (
        select(
            r,
            accepted.label("accepted"),
            final_status.label("submission_status"),
            late.label("late"),
        )
        .select_from(r.outerjoin(base, true()).outerjoin(ext, true()))
        .where(r.c.assignment_id.in_(assignment_ids))
    )
    if student_ids is not None:
        annotated = annotated.where(r.c.user_id.in_(student_ids))
    return annotated


def aggregate_roots(assignment_ids, student_ids=None):
    a = decision_roots(assignment_ids, student_ids).subquery("decisions")

    def newest(column, predicate=None, *, by_completion=False):
        order = a.c.finished_at.desc() if by_completion else a.c.started_at.desc()
        expression = func.array_agg(aggregate_order_by(column, order, a.c.root_id.desc()))
        if predicate is not None:
            expression = expression.filter(predicate)
        return expression[1]

    success = and_(a.c.successful, a.c.finished_at.is_not(None))
    # A satisfied assignment remains satisfied if a subsequent retry is unfinished or rejected.
    return (
        select(
            a.c.assignment_id,
            a.c.user_id,
            func.count().label("used"),
            newest(a.c.root_id).label("latest_id"),
            newest(a.c.kind).label("latest_kind"),
            newest(a.c.root_id, a.c.active).label("active_id"),
            newest(a.c.kind, a.c.active).label("active_kind"),
            func.coalesce(
                newest(a.c.submission_status, a.c.accepted, by_completion=True),
                newest(a.c.submission_status, success, by_completion=True),
            ).label("decision"),
            func.coalesce(
                newest(a.c.finished_at, a.c.accepted, by_completion=True),
                newest(a.c.finished_at, success, by_completion=True),
            ).label("completed_at"),
            func.coalesce(
                newest(a.c.result_attempt_id, a.c.accepted, by_completion=True),
                newest(a.c.result_attempt_id, success, by_completion=True),
            ).label("result_attempt_id"),
            func.coalesce(
                newest(a.c.late, a.c.accepted, by_completion=True),
                newest(a.c.late, success, by_completion=True),
                literal(False),
            ).label("late"),
            func.bool_or(a.c.accepted).label("accepted"),
        )
        .group_by(a.c.assignment_id, a.c.user_id)
        .subquery("root_summary")
    )


def progress_expressions(assignment, summary, cohort, ext, now):
    """One P2 status/cohort policy for monitoring, Gradebook and learning analytics."""
    due = case(
        (and_(ext.c.override_due, ~ext.c.revoked), ext.c.due_at_override), else_=assignment.due_at
    )
    cutoff = case(
        (and_(ext.c.override_cutoff, ~ext.c.revoked), ext.c.cutoff_at_override),
        else_=assignment.cutoff_at,
    )
    closure = case(
        (~type_coerce(assignment.allow_late_submission, Boolean()), func.least(due, cutoff)),
        else_=cutoff,
    )
    missed = and_(closure.is_not(None), now > closure, cohort.c.joined_at <= closure)
    status = case(
        (summary.c.accepted, summary.c.decision),
        (summary.c.active_id.is_not(None), "IN_PROGRESS"),
        (summary.c.decision.is_not(None), summary.c.decision),
        (missed, "MISSED"),
        else_="NOT_STARTED",
    )
    eligible = and_(cohort.c.active_member, or_(closure.is_(None), cohort.c.joined_at <= closure))
    return status, eligible


class AssignmentProgressRepository:
    def __init__(self, session):
        self.session = session

    async def usage(self, assignment_id, user_id):
        r = roots_query().subquery()
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(r)
                .where(r.c.assignment_id == assignment_id, r.c.user_id == user_id)
            )
            or 0
        )

    async def extension(self, assignment_id, student_id):
        return await self.session.scalar(
            select(ClassroomAssignmentExtension)
            .where(
                ClassroomAssignmentExtension.assignment_id == assignment_id,
                ClassroomAssignmentExtension.student_id == student_id,
            )
            .execution_options(populate_existing=True)
        )

    async def student_summaries(self, assignment_ids, student_id):
        summary = aggregate_roots(assignment_ids, [student_id])
        return {
            row.assignment_id: row._mapping for row in await self.session.execute(select(summary))
        }

    def monitoring_query(self, assignment, now):
        from app.services.classroom_capabilities import active_staff_clause

        roots = roots_query().subquery()
        members = select(
            ClassroomMembership.user_id,
            ClassroomMembership.joined_at,
            ClassroomMembership.left_at.is_(None).label("active_member"),
        ).where(
            ClassroomMembership.classroom_id == assignment.classroom_id,
            ClassroomMembership.left_at.is_(None),
            ~active_staff_clause(assignment.classroom_id, ClassroomMembership.user_id),
        )
        historical = select(roots.c.user_id, roots.c.started_at, literal(False)).where(
            roots.c.assignment_id == assignment.id
        )
        cohort = union_all(members, historical).subquery()
        cohort = (
            select(
                cohort.c.user_id,
                func.min(cohort.c.joined_at).label("joined_at"),
                func.bool_or(cohort.c.active_member).label("active_member"),
            )
            .group_by(cohort.c.user_id)
            .subquery("cohort")
        )
        summary = aggregate_roots([assignment.id])
        ext = ClassroomAssignmentExtension.__table__.alias("extension")
        status, eligible = progress_expressions(assignment, summary, cohort, ext, now)
        return (
            select(
                User.id.label("student_id"),
                User.display_name,
                cohort.c.joined_at,
                cohort.c.active_member,
                eligible.label("eligible"),
                *[
                    summary.c[key]
                    for key in summary.c.keys()
                    if key not in {"assignment_id", "user_id"}
                ],
                status.label("status"),
                ext.c.id.label("extension_id"),
            )
            .join(cohort, cohort.c.user_id == User.id)
            .outerjoin(summary, summary.c.user_id == User.id)
            .outerjoin(ext, and_(ext.c.student_id == User.id, ext.c.assignment_id == assignment.id))
        )

    def classroom_progress(self, classroom_id, now):
        from app.services.classroom_capabilities import active_staff_clause

        a = ClassroomAssignment.__table__.alias("class_assignments")
        ids = select(a.c.id).where(a.c.classroom_id == classroom_id)
        roots = roots_query().subquery("class_roots")
        member = ClassroomMembership
        current = (
            select(
                a.c.id.label("assignment_id"),
                member.user_id,
                member.joined_at,
                literal(True).label("active_member"),
            )
            .select_from(member)
            .join(a, a.c.classroom_id == member.classroom_id)
            .join(User, User.id == member.user_id)
            .where(
                a.c.classroom_id == classroom_id,
                member.left_at.is_(None),
                User.is_active,
                ~active_staff_clause(classroom_id, member.user_id),
            )
        )
        history = select(
            roots.c.assignment_id, roots.c.user_id, roots.c.started_at, literal(False)
        ).where(roots.c.assignment_id.in_(ids))
        raw = union_all(current, history).subquery("class_cohort")
        cohort = (
            select(
                raw.c.assignment_id,
                raw.c.user_id,
                func.min(raw.c.joined_at).label("joined_at"),
                func.bool_or(raw.c.active_member).label("active_member"),
            )
            .group_by(raw.c.assignment_id, raw.c.user_id)
            .subquery("class_cohort_summary")
        )
        summary = aggregate_roots(ids)
        ext = ClassroomAssignmentExtension.__table__.alias("class_extensions")
        status, eligible = progress_expressions(a.c, summary, cohort, ext, now)
        return (
            select(
                cohort.c.assignment_id,
                cohort.c.user_id.label("student_id"),
                cohort.c.active_member,
                eligible.label("eligible"),
                status.label("status"),
                func.coalesce(summary.c.used, 0).label("used"),
            )
            .select_from(cohort)
            .join(a, a.c.id == cohort.c.assignment_id)
            .outerjoin(
                summary,
                and_(
                    summary.c.assignment_id == cohort.c.assignment_id,
                    summary.c.user_id == cohort.c.user_id,
                ),
            )
            .outerjoin(
                ext,
                and_(
                    ext.c.assignment_id == cohort.c.assignment_id,
                    ext.c.student_id == cohort.c.user_id,
                ),
            )
        )
