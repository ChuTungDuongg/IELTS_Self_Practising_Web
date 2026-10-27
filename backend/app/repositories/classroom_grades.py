"""Bounded Gradebook SQL, sharing P2's authoritative historical decisions."""

from sqlalchemy import String, and_, case, cast, func, literal, or_, select

from app.models import (
    Attempt,
    AttemptWritingScore,
    ClassroomAssignment,
    ClassroomMembership,
    TestSession,
    User,
)
from app.models.speaking import AttemptSpeakingScore
from app.repositories.assignment_progress import decision_roots
from app.services.classroom_capabilities import active_staff_clause


def attempt_scores():
    task_score = (
        select(
            (
                AttemptWritingScore.ta
                + AttemptWritingScore.cc
                + AttemptWritingScore.lr
                + AttemptWritingScore.gra
            )
            / 4
        )
        .where(
            AttemptWritingScore.attempt_id == Attempt.id,
            AttemptWritingScore.writing_task_id == Attempt.focused_writing_task_id,
        )
        .correlate(Attempt)
        .scalar_subquery()
    )
    writing_count = (
        select(func.count())
        .where(AttemptWritingScore.attempt_id == Attempt.id)
        .correlate(Attempt)
        .scalar_subquery()
    )
    speaking = (
        select(AttemptSpeakingScore.attempt_id)
        .where(AttemptSpeakingScore.attempt_id == Attempt.id)
        .correlate(Attempt)
        .exists()
    )
    final = case(
        (Attempt.module_type.in_(["READING", "LISTENING"]), Attempt.band_score),
        (and_(Attempt.module_type == "WRITING", writing_count >= 2), Attempt.band_score),
        (and_(Attempt.module_type == "SPEAKING", speaking), Attempt.band_score),
    )
    band = case((Attempt.scope == "FULL_MODULE", final))
    provenance = case(
        (Attempt.module_type.in_(["READING", "LISTENING"]), "OBJECTIVE"),
        (
            or_(
                and_(
                    Attempt.module_type == "WRITING",
                    writing_count >= case((Attempt.scope == "FOCUSED_UNIT", 1), else_=2),
                ),
                and_(Attempt.module_type == "SPEAKING", speaking),
            ),
            "HUMAN_FINAL",
        ),
        else_="PENDING_HUMAN",
    )
    unit = func.coalesce(
        cast(Attempt.focused_reading_passage_id, String),
        cast(Attempt.focused_listening_part_id, String),
        cast(Attempt.focused_writing_task_id, String),
        cast(Attempt.focused_speaking_part_id, String),
        cast(Attempt.focused_speaking_prompt_id, String),
        literal("module"),
    )
    return select(
        Attempt.id.label("attempt_id"),
        Attempt.user_id,
        Attempt.module_type.label("skill"),
        Attempt.scope,
        Attempt.test_session_id,
        Attempt.band_score.label("stored_band"),
        band.label("band"),
        Attempt.raw_score,
        Attempt.max_score,
        provenance.label("provenance"),
        case(
            (
                Attempt.module_type.in_(["READING", "LISTENING"]),
                func.coalesce(band, Attempt.raw_score),
            ),
            (Attempt.scope == "FOCUSED_UNIT", task_score),
            else_=band,
        ).label("rank_value"),
        func.concat(Attempt.module_type, ":", Attempt.scope, ":", unit).label("context"),
    ).subquery("attempt_scores")


def graded_roots(assignment_ids, student_ids=None, *, skill=None):
    d = decision_roots(assignment_ids, student_ids).subquery("decisions")
    scores = attempt_scores()
    # Persisted module bands are written by the native human-final/objective graders.
    # Four-skill overall uses native IELTS rounding; legacy three-skill mocks expose only breakdowns.
    session_scores = (
        select(
            scores.c.test_session_id,
            case(
                (func.count(scores.c.band) == 4, func.round(func.avg(scores.c.band) * 2) / 2)
            ).label("band"),
            case(
                (func.count().filter(scores.c.provenance == "PENDING_HUMAN") > 0, "PENDING_HUMAN"),
                (func.count(scores.c.band) == 4, "HUMAN_FINAL"),
                else_="UNAVAILABLE",
            ).label("provenance"),
        )
        .where(scores.c.test_session_id.is_not(None))
        .group_by(scores.c.test_session_id)
        .subquery("mock_scores")
    )
    is_session = d.c.kind == "SESSION"
    query = select(
        d,
        case((is_session, "FULL_MOCK"), else_=cast(scores.c.skill, String)).label("skill"),
        case((is_session, "FULL_MOCK"), else_=cast(scores.c.scope, String)).label("scope"),
        case((is_session, session_scores.c.band), else_=scores.c.band).label("band"),
        case((is_session, session_scores.c.band), else_=scores.c.rank_value).label("rank_value"),
        case((is_session, session_scores.c.provenance), else_=scores.c.provenance).label(
            "provenance"
        ),
        case((~is_session, scores.c.raw_score)).label("raw_score"),
        case((~is_session, scores.c.max_score)).label("max_score"),
        case(
            (is_session, func.concat("FULL_MOCK:", cast(TestSession.module_order_json, String))),
            else_=scores.c.context,
        ).label("context"),
    ).select_from(
        d.outerjoin(scores, and_(~is_session, scores.c.attempt_id == d.c.root_id))
        .outerjoin(TestSession, and_(is_session, TestSession.id == d.c.root_id))
        .outerjoin(session_scores, session_scores.c.test_session_id == TestSession.id)
    )
    if skill:
        query = query.where(
            is_session if skill == "FULL_MOCK" else and_(~is_session, scores.c.skill == skill)
        )
    return query


def selected_grades(assignment_ids, student_ids=None, *, skill=None):
    g = graded_roots(assignment_ids, student_ids, skill=skill).subquery("grades")
    # Only accepted successful roots may supply scores. Mixed modes fall back to latest completion.
    comparable = (
        select(
            g.c.assignment_id,
            g.c.user_id,
            (func.min(g.c.context) == func.max(g.c.context)).label("comparable"),
        )
        .where(g.c.accepted)
        .group_by(g.c.assignment_id, g.c.user_id)
        .subquery("contexts")
    )
    first = ClassroomAssignment.grade_selection == "FIRST_ACCEPTED"
    best = and_(ClassroomAssignment.grade_selection == "BEST_ACCEPTED", comparable.c.comparable)
    ranked = (
        select(
            g,
            ClassroomAssignment.grade_selection,
            and_(
                ClassroomAssignment.grade_selection == "BEST_ACCEPTED", ~comparable.c.comparable
            ).label("mixed_context_fallback"),
            func.row_number()
            .over(
                partition_by=[g.c.assignment_id, g.c.user_id],
                order_by=[
                    case((best, g.c.rank_value)).desc().nulls_last(),
                    case((first, g.c.finished_at)).asc().nulls_last(),
                    g.c.finished_at.desc(),
                    g.c.root_id.desc(),
                ],
            )
            .label("rank"),
        )
        .join(ClassroomAssignment, ClassroomAssignment.id == g.c.assignment_id)
        .join(
            comparable,
            and_(
                comparable.c.assignment_id == g.c.assignment_id, comparable.c.user_id == g.c.user_id
            ),
        )
        .where(g.c.accepted)
        .subquery("ranked_grades")
    )
    return select(ranked).where(ranked.c.rank == 1)


def classroom_cohort(classroom_id):
    from app.repositories.assignment_progress import roots_query

    roots = roots_query().subquery()
    history = (
        select(roots.c.user_id)
        .join(ClassroomAssignment, ClassroomAssignment.id == roots.c.assignment_id)
        .where(ClassroomAssignment.classroom_id == classroom_id)
    )
    membership = select(ClassroomMembership.user_id).where(
        ClassroomMembership.classroom_id == classroom_id, ClassroomMembership.left_at.is_(None)
    )
    active = (
        select(ClassroomMembership.id)
        .where(
            ClassroomMembership.classroom_id == classroom_id,
            ClassroomMembership.user_id == User.id,
            ClassroomMembership.left_at.is_(None),
        )
        .exists()
    )
    return select(
        User.id.label("student_id"),
        User.display_name,
        User.email,
        and_(active, User.is_active, ~active_staff_clause(classroom_id, User.id)).label(
            "active_member"
        ),
    ).where(or_(User.id.in_(membership), User.id.in_(history)))
