"""SQL-only aggregation of authorized selected roots, never raw private practice."""

from datetime import timedelta

from sqlalchemy import String, and_, case, cast, func, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import aggregate_order_by

from app.domains.questions.registry import question_registry
from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptWritingScore,
    ClassroomAssignment,
    Question,
    QuestionGroup,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.models.speaking import AttemptSpeakingScore
from app.repositories.classroom_grades import attempt_scores, selected_grades


def learning_roots(classroom_id, student_id=None):
    ids = select(ClassroomAssignment.id).where(ClassroomAssignment.classroom_id == classroom_id)
    return selected_grades(ids, [student_id] if student_id else None).subquery("learning_roots")


def learning_attempts(classroom_id, start, end, student_id=None):
    roots = learning_roots(classroom_id, student_id)
    facts = attempt_scores()
    return (
        select(
            facts, roots.c.assignment_id, roots.c.finished_at.label("at"), Attempt.test_version_id
        )
        .select_from(Attempt)
        .join(
            roots,
            or_(
                and_(roots.c.kind == "ATTEMPT", roots.c.root_id == Attempt.id),
                and_(roots.c.kind == "SESSION", roots.c.root_id == Attempt.test_session_id),
            ),
        )
        .join(facts, facts.c.attempt_id == Attempt.id)
        .join(TestVersion, TestVersion.id == Attempt.test_version_id)
        .where(
            roots.c.finished_at >= start,
            roots.c.finished_at < end,
            TestVersion.status.in_(["PUBLISHED", "ARCHIVED"]),
        )
    )


class ClassroomLearningRepository:
    def __init__(self, session):
        self.session = session

    async def skills(self, attempts, end):
        recent = end - timedelta(days=30)
        valid = and_(attempts.c.scope == "FULL_MODULE", attempts.c.band.is_not(None))
        summary = (
            select(
                attempts.c.skill,
                func.count().label("sample_size"),
                func.count(func.distinct(attempts.c.test_version_id)).label(
                    "independent_assessments"
                ),
                func.count(func.distinct(attempts.c.test_version_id))
                .filter(attempts.c.at >= recent)
                .label("recent_independent_assessments"),
                func.avg(attempts.c.band).label("average"),
                func.avg(attempts.c.band).filter(attempts.c.at >= recent).label("recent_average"),
                func.array_agg(
                    aggregate_order_by(
                        attempts.c.band, attempts.c.at.desc(), attempts.c.attempt_id.desc()
                    )
                )[1].label("latest"),
            )
            .where(valid)
            .group_by(attempts.c.skill)
        )
        rows = (await self.session.execute(summary)).mappings().all()
        ranked = (
            select(
                attempts,
                func.row_number()
                .over(
                    partition_by=attempts.c.skill,
                    order_by=[attempts.c.at.desc(), attempts.c.attempt_id.desc()],
                )
                .label("point_rank"),
            )
            .where(valid)
            .subquery("trend_points")
        )
        points = (
            (
                await self.session.execute(
                    select(
                        ranked.c.skill,
                        ranked.c.attempt_id,
                        ranked.c.assignment_id,
                        ranked.c.at,
                        ranked.c.band,
                    )
                    .where(ranked.c.point_rank <= 60)
                    .order_by(ranked.c.skill, ranked.c.at, ranked.c.attempt_id)
                )
            )
            .mappings()
            .all()
        )
        return rows, points

    async def question_types(self, attempts, end):
        a, answer, group = Attempt, AttemptAnswer, QuestionGroup
        scoped = or_(
            a.scope == "FULL_MODULE",
            group.passage_id == a.focused_reading_passage_id,
            group.listening_part_id == a.focused_listening_part_id,
        )
        exposures = (
            select(
                attempts.c.user_id,
                attempts.c.attempt_id,
                attempts.c.skill,
                attempts.c.at,
                Question.id.label("question_id"),
                group.question_type.label("category"),
                func.coalesce(answer.is_correct, False).label("correct"),
                answer.id.is_(None).label("unanswered"),
                func.row_number()
                .over(
                    partition_by=[attempts.c.user_id, Question.id],
                    order_by=[attempts.c.at.desc(), attempts.c.attempt_id.desc()],
                )
                .label("exposure_rank"),
            )
            .select_from(attempts)
            .join(a, a.id == attempts.c.attempt_id)
            .join(
                TestModule,
                and_(
                    TestModule.test_version_id == a.test_version_id,
                    cast(TestModule.module_type, String) == cast(a.module_type, String),
                ),
            )
            .join(group, group.module_id == TestModule.id)
            .join(Question, Question.question_group_id == group.id)
            .outerjoin(answer, and_(answer.attempt_id == a.id, answer.question_id == Question.id))
            .where(
                a.module_type.in_(["READING", "LISTENING"]),
                scoped,
                a.raw_score.is_not(None),
                a.max_score.is_not(None),
                group.question_type.in_(question_registry.names()),
                or_(answer.id.is_(None), answer.is_correct.is_not(None)),
            )
            .subquery("question_exposures")
        )
        recent = exposures.c.at >= end - timedelta(days=30)
        unique = exposures.c.exposure_rank == 1
        count = func.count().filter(unique)
        correct = func.count().filter(unique & exposures.c.correct)
        recent_count = func.count().filter(unique & recent)
        historic_count = func.count().filter(unique & ~recent)

        def ratio(numerator, denominator):
            return numerator * 100.0 / func.nullif(denominator, 0)

        query = (
            select(
                exposures.c.skill,
                exposures.c.category,
                count.label("sample_size"),
                count.label("questions_attempted"),
                correct.label("questions_correct"),
                func.count().filter(unique & exposures.c.unanswered).label("unanswered"),
                (func.count() - count).label("repeated_exposures"),
                ratio(correct, count).label("accuracy"),
                recent_count.label("recent_sample_size"),
                historic_count.label("historical_sample_size"),
                ratio(
                    func.count().filter(unique & recent & exposures.c.correct), recent_count
                ).label("recent_accuracy"),
                ratio(
                    func.count().filter(unique & ~recent & exposures.c.correct), historic_count
                ).label("historical_accuracy"),
            )
            .group_by(exposures.c.skill, exposures.c.category)
            .order_by(exposures.c.skill, exposures.c.category)
        )
        return (await self.session.execute(query)).mappings().all()

    async def criteria(self, attempts, end):
        branches = []
        for criterion in ("ta", "cc", "lr", "gra"):
            branches.append(
                select(
                    attempts.c.user_id,
                    attempts.c.attempt_id,
                    attempts.c.at,
                    literal("WRITING").label("skill"),
                    func.concat("TASK_", WritingTask.task_number).label("context"),
                    literal(criterion).label("criterion"),
                    cast(WritingTask.id, String).label("sample_key"),
                    getattr(AttemptWritingScore, criterion).label("score"),
                )
                .select_from(attempts)
                .join(AttemptWritingScore, AttemptWritingScore.attempt_id == attempts.c.attempt_id)
                .join(WritingTask, WritingTask.id == AttemptWritingScore.writing_task_id)
                .join(Attempt, Attempt.id == attempts.c.attempt_id)
                .where(
                    attempts.c.skill == "WRITING",
                    or_(
                        Attempt.scope == "FULL_MODULE",
                        Attempt.focused_writing_task_id == WritingTask.id,
                    ),
                )
            )
        for criterion in ("fc", "lr", "gra", "pr"):
            branches.append(
                select(
                    attempts.c.user_id,
                    attempts.c.attempt_id,
                    attempts.c.at,
                    literal("SPEAKING"),
                    case(
                        (attempts.c.scope == "FULL_MODULE", "FULL_MODULE"), else_=attempts.c.context
                    ),
                    literal(criterion),
                    cast(attempts.c.test_version_id, String),
                    getattr(AttemptSpeakingScore, criterion),
                )
                .select_from(attempts)
                .join(
                    AttemptSpeakingScore, AttemptSpeakingScore.attempt_id == attempts.c.attempt_id
                )
                .where(attempts.c.skill == "SPEAKING")
            )
        samples = union_all(*branches).subquery("criterion_samples")
        ranked = select(
            samples,
            func.row_number()
            .over(
                partition_by=[
                    samples.c.user_id,
                    samples.c.skill,
                    samples.c.context,
                    samples.c.criterion,
                    samples.c.sample_key,
                ],
                order_by=[samples.c.at.desc(), samples.c.attempt_id.desc()],
            )
            .label("sample_rank"),
        ).subquery("independent_criteria")
        recent = ranked.c.at >= end - timedelta(days=30)
        query = (
            select(
                ranked.c.skill,
                ranked.c.context,
                ranked.c.criterion,
                func.count().label("sample_size"),
                func.count().filter(recent).label("recent_sample_size"),
                func.count().filter(~recent).label("historical_sample_size"),
                func.avg(ranked.c.score).label("average"),
                func.avg(ranked.c.score).filter(recent).label("recent_average"),
                func.avg(ranked.c.score).filter(~recent).label("historical_average"),
            )
            .where(ranked.c.sample_rank == 1)
            .group_by(ranked.c.skill, ranked.c.context, ranked.c.criterion)
            .order_by(ranked.c.skill, ranked.c.context, ranked.c.criterion)
            .limit(201)
        )
        return (await self.session.execute(query)).mappings().all()
