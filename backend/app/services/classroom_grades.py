"""Gradebook read models; all scores come from existing native final graders."""

import csv
import io
from collections import Counter

from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.domains.scoring import calculate_task_overall, project_overall_band
from app.domains.timers import TimerService
from app.models import AttemptWritingScore, ClassroomAssignment, TestVersion
from app.repositories.assignment_progress import AssignmentProgressRepository
from app.repositories.classroom_grades import (
    attempt_scores,
    classroom_cohort,
    graded_roots,
    selected_grades,
)
from app.schemas.classroom_grades import (
    AcademicProfile,
    GradebookPage,
    GradeCell,
    GradeColumn,
    GradeComponent,
    GradeScore,
    GradeStudent,
)
from app.services.classroom_capabilities import Capability, require_capability
from app.services.classroom_content_access import ContentAccess


def csv_safe(value):
    value = "" if value is None else str(value)
    return "'" + value if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@")) else value


class ClassroomGradeService:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor
        self.access = ContentAccess(session, actor)

    async def authorize(self, classroom_id, capability=Capability.GRADES_VIEW, *, mutation=False):
        room = await self.access.room(classroom_id, mutation=mutation)
        await require_capability(self.session, self.access.actor, room, capability)
        return room

    async def _columns(self, classroom_id, *, assignment_id=None, assignment_offset=0, limit=20):
        from app.models import Test
        query = select(ClassroomAssignment, Test.title).join(TestVersion, TestVersion.id == ClassroomAssignment.test_version_id)\
            .join(Test, Test.id == TestVersion.test_id).where(ClassroomAssignment.classroom_id == classroom_id)
        if assignment_id:
            query = query.where(ClassroomAssignment.id == assignment_id)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = (await self.session.execute(query.order_by(ClassroomAssignment.created_at, ClassroomAssignment.id)
                                          .limit(limit).offset(assignment_offset))).all()
        if assignment_id and not rows:
            raise AppError("ASSIGNMENT_NOT_ACCESSIBLE", "Assignment not found in this classroom.", 404)
        return rows, total

    async def score_details(self, rows):
        if not rows:
            return []
        roots = [dict(row) for row in rows]
        attempt_ids = [row["root_id"] for row in roots if row["kind"] == "ATTEMPT"]
        session_ids = [row["root_id"] for row in roots if row["kind"] == "SESSION"]
        facts = attempt_scores()
        from sqlalchemy import or_
        components = (await self.session.execute(select(facts).where(or_(
            facts.c.attempt_id.in_(attempt_ids), facts.c.test_session_id.in_(session_ids))))).mappings().all()
        focused = [row["attempt_id"] for row in components if row["scope"] == "FOCUSED_UNIT"]
        task_scores = (await self.session.execute(select(AttemptWritingScore).where(
            AttemptWritingScore.attempt_id.in_(focused)))).scalars().all() if focused else []
        task_values = {row.attempt_id: float(calculate_task_overall(row.ta, row.cc, row.lr, row.gra)) for row in task_scores}
        grouped = {}
        for row in components:
            key = row["test_session_id"] or row["attempt_id"]
            grouped.setdefault(key, []).append(GradeComponent(**{field: row[field] for field in
                ("attempt_id", "skill", "band", "raw_score", "max_score", "provenance")},
                task_score=task_values.get(row["attempt_id"])))
        result = []
        for row in roots:
            breakdown = sorted(grouped.get(row["root_id"], []), key=lambda item: item.skill)
            if row["kind"] == "SESSION":
                bands = {item.skill: item.band for item in breakdown}
                row["band"] = project_overall_band(*(bands.get(key) for key in ("READING", "LISTENING", "WRITING", "SPEAKING")))
            result.append(GradeScore.model_validate({**row, "breakdown": breakdown}))
        return result

    async def page(self, classroom_id, *, search="", assignment_id=None, skill=None, status="ALL",
                   sort="name", limit=30, offset=0, assignment_offset=0):
        async with self.session.begin():
            await self.authorize(classroom_id)
            return await self._page(classroom_id, search=search, assignment_id=assignment_id, skill=skill,
                                    status=status, sort=sort, limit=limit, offset=offset, assignment_offset=assignment_offset)

    async def _page(self, classroom_id, *, search="", assignment_id=None, skill=None, status="ALL",
                    sort="name", limit=30, offset=0, assignment_offset=0, student_id=None):
        columns, total_assignments = await self._columns(classroom_id, assignment_id=assignment_id, assignment_offset=assignment_offset)
        assignments = [a for a, _ in columns]
        ids = [a.id for a in assignments]
        cohort = classroom_cohort(classroom_id).subquery("students")
        students = select(cohort)
        if student_id:
            students = students.where(cohort.c.student_id == student_id)
        if search.strip():
            students = students.where(cohort.c.display_name.ilike("%" + search.strip().replace("%", r"\%").replace("_", r"\_") + "%", escape="\\"))
        repo = AssignmentProgressRepository(self.session)
        progress = repo.classroom_progress(classroom_id, TimerService.now()).subquery("progress") if assignments else None
        if status != "ALL" and progress is not None:
            predicate = (progress.c.status.in_(["SUBMITTED_ON_TIME", "SUBMITTED_LATE"]) if status == "SUBMITTED" else progress.c.status == status) & progress.c.assignment_id.in_(ids)
            students = students.where(cohort.c.student_id.in_(select(progress.c.student_id).where(predicate)))
        grades = selected_grades(ids, skill=skill).subquery("selected")
        if sort != "name":
            if not assignment_id or not skill:
                raise AppError("GRADE_SORT_CONTEXT_REQUIRED", "Score sorting requires one assignment and one assessment context.", 422)
            students = students.outerjoin(grades, grades.c.user_id == cohort.c.student_id)
            students = students.order_by((grades.c.band.asc() if sort == "score_asc" else grades.c.band.desc()).nulls_last())
        total = await self.session.scalar(select(func.count()).select_from(students.order_by(None).subquery()))
        people = (await self.session.execute(students.order_by(cohort.c.display_name, cohort.c.student_id).limit(limit).offset(offset))).mappings().all()
        student_ids = [row["student_id"] for row in people]
        selected = (await self.session.execute(select(grades).where(grades.c.user_id.in_(student_ids)))).mappings().all()
        details = await self.score_details(selected)
        selected_map = {(row["assignment_id"], row["user_id"]): value for row, value in zip(selected, details, strict=True)}
        statuses = {(row["assignment_id"], row["student_id"]): row for row in
                    (await self.session.execute(select(progress).where(progress.c.student_id.in_(student_ids), progress.c.assignment_id.in_(ids)))).mappings().all()} if progress is not None else {}
        result = []
        for student in people:
            cells = []
            for assignment in assignments:
                row = statuses.get((assignment.id, student["student_id"]), {})
                cells.append(GradeCell(assignment_id=assignment.id, submission_status=row.get("status", "NOT_STARTED"),
                    attempts_used=row.get("used") or 0, eligible=bool(row.get("eligible")),
                    score=selected_map.get((assignment.id, student["student_id"]))))
            result.append(GradeStudent(student_id=student["student_id"], display_name=student["display_name"],
                                       active_member=student["active_member"], cells=cells))
        return GradebookPage(assignments=[GradeColumn(id=a.id, title=a.title or title, grade_selection=a.grade_selection,
                                                     policy_revision=a.policy_revision) for a, title in columns],
                             students=result, total_students=total, total_assignments=total_assignments)

    async def profile(self, classroom_id, student_id, *, assignment_offset=0, history_offset=0):
        async with self.session.begin():
            await self.authorize(classroom_id)
            page = await self._page(classroom_id, student_id=student_id, assignment_offset=assignment_offset)
            if not page.students:
                raise AppError("CLASSROOM_STUDENT_NOT_FOUND", "No authorized academic history for this student.", 404)
            student = page.students[0]
            assignment_ids = select(ClassroomAssignment.id).where(ClassroomAssignment.classroom_id == classroom_id)
            all_roots = graded_roots(assignment_ids, [student_id]).subquery("history")
            successful = select(all_roots).where(all_roots.c.successful, all_roots.c.finished_at.is_not(None))
            total = await self.session.scalar(select(func.count()).select_from(successful.subquery()))
            rows = (await self.session.execute(successful.order_by(all_roots.c.finished_at.desc(), all_roots.c.root_id.desc())
                                               .limit(50).offset(history_offset))).mappings().all()
            return AcademicProfile(student_id=student_id, display_name=student.display_name, active_member=student.active_member,
                counts=dict(Counter(cell.submission_status for cell in student.cells)), assignments=student.cells,
                history=await self.score_details(rows), total_assignments=page.total_assignments, total_history=total,
                assignment_offset=assignment_offset, history_offset=history_offset)

    async def export(self, classroom_id, **filters):
        # Same authorization, filters and canonical cells as JSON. Explicitly bounded page export.
        page = await self.page(classroom_id, limit=200, **filters)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        columns = ["Student ID", "Student", "Membership"]
        for a in page.assignments:
            columns.extend(f"{a.title} | {field}" for field in ("Selection", "Skill", "Band", "Raw", "Submission", "Grading"))
        writer.writerow([csv_safe(value) for value in columns])
        for student in page.students:
            row = [student.student_id, student.display_name, "ACTIVE" if student.active_member else "HISTORICAL"]
            for a, cell in zip(page.assignments, student.cells, strict=True):
                score = cell.score
                row.extend([a.grade_selection, score.skill if score else "", score.band if score else "", score.raw_score if score else "",
                            cell.submission_status, score.provenance if score else "UNAVAILABLE"])
            writer.writerow([csv_safe(value) for value in row])
        return "\ufeff" + output.getvalue()

    async def policy(self, classroom_id, assignment_id, data):
        from app.services.assignment_scheduling import policy_event
        async with self.session.begin():
            await self.authorize(classroom_id, Capability.ASSIGNMENTS, mutation=True)
            assignment = await self.session.scalar(select(ClassroomAssignment).where(
                ClassroomAssignment.id == assignment_id, ClassroomAssignment.classroom_id == classroom_id).with_for_update())
            if not assignment:
                raise AppError("ASSIGNMENT_NOT_ACCESSIBLE", "Assignment not found.", 404)
            if assignment.status != "ACTIVE":
                raise AppError("ASSIGNMENT_ARCHIVED", "Archived assignments are read-only.", 409)
            if assignment.policy_revision != data.expected_revision:
                raise AppError("ASSIGNMENT_CHANGED", "Reload the assignment before saving.", 409)
            if assignment.grade_selection != data.grade_selection:
                assignment.grade_selection = data.grade_selection
                await policy_event(self.session, assignment, self.actor.id, kind="GRADE_SELECTION_CHANGED")
            return GradeColumn(id=assignment.id, title=assignment.title or "Assignment", grade_selection=assignment.grade_selection,
                               policy_revision=assignment.policy_revision)
