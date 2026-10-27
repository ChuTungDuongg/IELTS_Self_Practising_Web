"""Reproducible IELTS analytics: selected accepted roots and human-final criteria."""

from datetime import timedelta

from sqlalchemy import and_, func, select

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import Attempt, ClassroomAssignment, QuestionGroup, TestModule, TestSession, User
from app.repositories.assignment_progress import AssignmentProgressRepository
from app.repositories.classroom_grades import classroom_cohort
from app.repositories.classroom_learning import (
    ClassroomLearningRepository,
    learning_attempts,
    learning_roots,
)
from app.schemas.classroom_learning import (
    AttentionStudent,
    CompletionActivity,
    CriterionPerformance,
    LearningDashboard,
    QuestionPerformance,
    Recommendation,
    SkillPerformance,
    SkillTrendPoint,
    Weakness,
)
from app.services.assignment_progress import AssignmentProgressService
from app.services.classroom_capabilities import Capability, require_capability
from app.services.classroom_grades import ClassroomGradeService
from app.services.learning_goals import present_goals

SKILLS = ("READING", "LISTENING", "WRITING", "SPEAKING")


def weakness_rules(questions, criteria, skills, goals=None):
    """Conservative evidence thresholds, not a diagnostic or band-prediction model."""
    result = []
    for q in questions:
        if (
            q.sample_size < 10
            or q.recent_sample_size < 5
            or q.recent_accuracy is None
            or q.recent_accuracy >= 60
        ):
            continue
        result.append(
            Weakness(
                weakness_type="QUESTION_TYPE",
                skill=q.skill,
                category=q.category,
                observed=q.recent_accuracy,
                baseline=60,
                sample_size=q.sample_size,
                evidence=f"{q.recent_accuracy:.1f}% recent accuracy; {q.sample_size} distinct learner/question pairs",
                severity="HIGH" if q.recent_accuracy < 40 else "MODERATE",
                confidence_level=q.confidence_level,
                recommendation_reason="LOW_RECENT_ACCURACY",
            )
        )
    for c in criteria:
        configured = getattr(goals, c.skill.lower()) if goals else None
        target = float(configured) if configured is not None else 6.0
        if c.recent_sample_size < 3 or c.recent_average is None or c.recent_average > target - 0.5:
            continue
        result.append(
            Weakness(
                weakness_type="CRITERION",
                skill=c.skill,
                category=f"{c.context}:{c.criterion}",
                observed=c.recent_average,
                baseline=target,
                sample_size=c.sample_size,
                evidence=f"{c.recent_average:.2f} recent human-final average; {c.sample_size} distinct assessments",
                severity="HIGH" if target - c.recent_average >= 1 else "MODERATE",
                confidence_level="HIGH" if c.recent_sample_size >= 8 else "MEDIUM",
                recommendation_reason="LOW_HUMAN_CRITERION",
            )
        )
    for skill in skills:
        target = getattr(goals, skill.skill.lower()) if goals else None
        if (
            target is None
            or skill.recent_independent_assessments < 3
            or skill.recent_average is None
            or skill.recent_average > float(target) - 0.5
        ):
            continue
        result.append(
            Weakness(
                weakness_type="SKILL_BAND",
                skill=skill.skill,
                category="FULL_MODULE",
                observed=skill.recent_average,
                baseline=float(target),
                sample_size=skill.independent_assessments,
                evidence=f"{skill.recent_average:.2f} recent final band average; {skill.independent_assessments} different versions",
                severity="MODERATE",
                confidence_level="MEDIUM",
                recommendation_reason="BELOW_SKILL_TARGET",
            )
        )
    return sorted(
        result,
        key=lambda row: (
            row.severity != "HIGH",
            row.confidence_level != "HIGH",
            -row.sample_size,
            row.skill,
            row.category,
        ),
    )[:20]


class ClassroomLearningService:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor
        self.grades = ClassroomGradeService(session, actor)
        self.repository = ClassroomLearningRepository(session)

    async def dashboard(
        self, classroom_id, *, student_id=None, own=False, start=None, end=None, completion_offset=0
    ):
        now = TimerService.now()
        end = end or now + timedelta(seconds=1)
        start = start or end - timedelta(days=90)
        if end <= start or end - start > timedelta(days=366):
            raise AppError(
                "ANALYTICS_RANGE_INVALID", "Choose an assessment range of at most 366 days.", 422
            )
        async with self.session.begin():
            room = await self.grades.access.room(classroom_id)
            if own:
                if student_id is not None and student_id != self.actor.id:
                    raise AppError(
                        "CLASSROOM_ANALYTICS_PRIVATE", "Only your own progress is available.", 403
                    )
                student_id = self.actor.id
            else:
                await require_capability(
                    self.session, self.grades.access.actor, room, Capability.ANALYTICS
                )
            cohort = classroom_cohort(room.id).subquery("analytics_cohort")
            if student_id:
                exists = await self.session.scalar(
                    select(cohort.c.student_id).where(cohort.c.student_id == student_id)
                )
                if not exists and not own:
                    raise AppError(
                        "CLASSROOM_STUDENT_NOT_FOUND",
                        "No classroom academic history for this student.",
                        404,
                    )
            current = select(func.count()).select_from(cohort).where(cohort.c.active_member)
            if student_id:
                current = current.where(cohort.c.student_id == student_id)
            active_students = await self.session.scalar(current) or 0
            progress = (
                AssignmentProgressRepository(self.session)
                .classroom_progress(room.id, now)
                .subquery("analytics_progress")
            )
            scope = progress.c.student_id == student_id if student_id else True
            counts = dict(
                (
                    await self.session.execute(
                        select(progress.c.status, func.count())
                        .where(progress.c.eligible, scope)
                        .group_by(progress.c.status)
                    )
                ).all()
            )
            eligible = sum(counts.values())
            completed = counts.get("SUBMITTED_ON_TIME", 0) + counts.get("SUBMITTED_LATE", 0)
            assigned = (
                await self.session.scalar(
                    select(func.count())
                    .select_from(ClassroomAssignment)
                    .where(ClassroomAssignment.classroom_id == room.id)
                )
                or 0
            )
            roots = learning_roots(room.id, student_id)
            in_range = and_(roots.c.finished_at >= start, roots.c.finished_at < end)
            pending = (
                await self.session.scalar(
                    select(func.count())
                    .select_from(roots)
                    .where(in_range, roots.c.provenance == "PENDING_HUMAN")
                )
                or 0
            )
            attempts = learning_attempts(room.id, start, end, student_id).subquery(
                "learning_attempts"
            )
            skill_rows, trend_rows = await self.repository.skills(attempts, end)
            skill_map = {row["skill"]: row for row in skill_rows}
            skills = [
                SkillPerformance(
                    skill=skill,
                    sample_size=skill_map.get(skill, {}).get("sample_size", 0),
                    independent_assessments=skill_map.get(skill, {}).get(
                        "independent_assessments", 0
                    ),
                    recent_independent_assessments=skill_map.get(skill, {}).get(
                        "recent_independent_assessments", 0
                    ),
                    average=skill_map.get(skill, {}).get("average"),
                    recent_average=skill_map.get(skill, {}).get("recent_average"),
                    latest=skill_map.get(skill, {}).get("latest"),
                    trends=[
                        SkillTrendPoint.model_validate(point)
                        for point in trend_rows
                        if point["skill"] == skill
                    ],
                )
                for skill in SKILLS
            ]
            questions = []
            for row in await self.repository.question_types(attempts, end):
                recent, old = row["recent_accuracy"], row["historical_accuracy"]
                evidence = row["sample_size"] >= 10 and row["recent_sample_size"] >= 5
                questions.append(
                    QuestionPerformance.model_validate(
                        {
                            **row,
                            "confidence_level": "HIGH"
                            if evidence
                            and row["sample_size"] >= 30
                            and row["recent_sample_size"] >= 10
                            else "MEDIUM"
                            if evidence
                            else "INSUFFICIENT",
                            "trend": float(recent - old)
                            if recent is not None
                            and old is not None
                            and row["recent_sample_size"] >= 5
                            and row["historical_sample_size"] >= 5
                            else None,
                        }
                    )
                )
            criterion_rows = await self.repository.criteria(attempts, end)
            criteria = [
                CriterionPerformance.model_validate(
                    {
                        **row,
                        "trend": float(row["recent_average"] - row["historical_average"])
                        if row["recent_average"] is not None
                        and row["historical_average"] is not None
                        and row["recent_sample_size"] >= 3
                        and row["historical_sample_size"] >= 3
                        else None,
                    }
                )
                for row in criterion_rows[:200]
            ]
            user = await self.session.get(User, student_id) if student_id else None
            goals = present_goals(user) if user else None
            weaknesses = weakness_rules(questions, criteria, skills, goals)
            recent_roots = (
                (
                    await self.session.execute(
                        select(roots)
                        .where(in_range)
                        .order_by(roots.c.finished_at.desc(), roots.c.root_id.desc())
                        .limit(20)
                    )
                )
                .mappings()
                .all()
            )
            titles = (
                await self.session.execute(
                    select(ClassroomAssignment.id, ClassroomAssignment.title)
                    .where(ClassroomAssignment.classroom_id == room.id)
                    .order_by(ClassroomAssignment.created_at, ClassroomAssignment.id)
                    .limit(20)
                    .offset(completion_offset)
                )
            ).all()
            completion_rows = (
                (
                    await self.session.execute(
                        select(
                            progress.c.assignment_id, progress.c.status, func.count().label("count")
                        )
                        .where(
                            progress.c.eligible,
                            scope,
                            progress.c.assignment_id.in_([row.id for row in titles]),
                        )
                        .group_by(progress.c.assignment_id, progress.c.status)
                    )
                )
                .mappings()
                .all()
            )
            # Aggregate only the displayed assignment page, never load an attempt per student.
            completion = {}
            for row in completion_rows:
                completion.setdefault(row["assignment_id"], {})[row["status"]] = row["count"]
            by_assignment = [
                CompletionActivity(
                    assignment_id=id,
                    title=title or "IELTS assignment",
                    counts=completion.get(id, {}),
                )
                for id, title in titles
            ]
            missing = (
                select(
                    progress.c.student_id,
                    func.count().filter(progress.c.status == "MISSED").label("missing"),
                )
                .where(progress.c.eligible)
                .group_by(progress.c.student_id)
                .subquery("missing_counts")
            )
            waiting = (
                select(
                    roots.c.user_id,
                    func.count().filter(roots.c.provenance == "PENDING_HUMAN").label("pending"),
                )
                .where(in_range)
                .group_by(roots.c.user_id)
                .subquery("waiting_counts")
            )
            attention = []
            if not own:
                rows = (
                    (
                        await self.session.execute(
                            select(
                                cohort.c.student_id,
                                cohort.c.display_name,
                                func.coalesce(missing.c.missing, 0).label("missing"),
                                func.coalesce(waiting.c.pending, 0).label("pending_human"),
                            )
                            .outerjoin(missing, missing.c.student_id == cohort.c.student_id)
                            .outerjoin(waiting, waiting.c.user_id == cohort.c.student_id)
                            .where(
                                cohort.c.active_member,
                                (
                                    func.coalesce(missing.c.missing, 0)
                                    + func.coalesce(waiting.c.pending, 0)
                                )
                                > 0,
                            )
                            .order_by(
                                func.coalesce(missing.c.missing, 0).desc(),
                                func.coalesce(waiting.c.pending, 0).desc(),
                                cohort.c.student_id,
                            )
                            .limit(50)
                        )
                    )
                    .mappings()
                    .all()
                )
                attention = [AttentionStudent.model_validate(row) for row in rows]
            recommendations = (
                await self._recommend(room, weaknesses, user or self.actor) if own else []
            )
            return LearningDashboard(
                start=start,
                end=end,
                active_students=active_students,
                assigned_activities=assigned,
                eligible_requirements=eligible,
                completion_rate=completed * 100 / eligible if eligible else None,
                on_time_rate=counts.get("SUBMITTED_ON_TIME", 0) * 100 / completed
                if completed
                else None,
                counts=counts,
                pending_human=pending,
                goals=goals,
                skills=skills,
                question_types=questions,
                criteria=criteria,
                weaknesses=weaknesses,
                recent_assessments=await self.grades.score_details(recent_roots),
                completion_by_assignment=by_assignment,
                total_completion_activities=assigned,
                attention_students=attention,
                recommendations=recommendations,
                criteria_truncated=len(criterion_rows) > 200,
            )

    async def _recommend(self, room, weaknesses, student):
        if not weaknesses or room.status != "ACTIVE":
            return []
        assignments = list(
            await self.session.scalars(
                select(ClassroomAssignment)
                .where(
                    ClassroomAssignment.classroom_id == room.id,
                    ClassroomAssignment.status == "ACTIVE",
                )
                .order_by(ClassroomAssignment.created_at.desc(), ClassroomAssignment.id)
                .limit(100)
            )
        )
        progress = await AssignmentProgressService(self.session, student)._student_rows(
            room, assignments, TimerService.now()
        )
        permitted = {
            row.assignment_id: row for row in progress if row.can_start and not row.accepted
        }
        versions = {a.test_version_id for a in assignments if a.id in permitted}
        modules = (
            await self.session.execute(
                select(
                    TestModule.test_version_id, TestModule.module_type, QuestionGroup.question_type
                )
                .outerjoin(QuestionGroup, QuestionGroup.module_id == TestModule.id)
                .where(TestModule.test_version_id.in_(versions))
            )
        ).all()
        grouped = {}
        for version, skill, category in modules:
            grouped.setdefault((version, skill), set()).add(category)
        roots = learning_roots(room.id, student.id)
        completed_versions = set(
            await self.session.scalars(
                select(func.coalesce(Attempt.test_version_id, TestSession.test_version_id))
                .select_from(roots)
                .outerjoin(Attempt, and_(roots.c.kind == "ATTEMPT", Attempt.id == roots.c.root_id))
                .outerjoin(
                    TestSession, and_(roots.c.kind == "SESSION", TestSession.id == roots.c.root_id)
                )
            )
        )
        ranked = []
        for index, weakness in enumerate(weaknesses):
            for assignment in assignments:
                if (
                    assignment.id not in permitted
                    or (assignment.test_version_id, weakness.skill) not in grouped
                ):
                    continue
                categories = grouped[(assignment.test_version_id, weakness.skill)]
                if (
                    weakness.weakness_type == "QUESTION_TYPE"
                    and weakness.category not in categories
                ):
                    continue
                ranked.append(
                    (
                        assignment.test_version_id in completed_versions,
                        index,
                        permitted[assignment.id].attempts_used > 0,
                        assignment.created_at,
                        str(assignment.id),
                        assignment,
                        weakness,
                    )
                )
        ranked.sort(key=lambda row: row[:5])
        selected, seen = [], set()
        for _, _, _, _, _, assignment, weakness in ranked:
            if assignment.id in seen:
                continue
            seen.add(assignment.id)
            selected.append(
                Recommendation(
                    assignment_id=assignment.id,
                    title=assignment.title or "IELTS assignment",
                    skill=weakness.skill,
                    category=weakness.category,
                    reason=weakness.recommendation_reason,
                    href=f"/classrooms/{room.id}?assignment={assignment.id}",
                )
            )
            if len(selected) == 6:
                break
        return selected
