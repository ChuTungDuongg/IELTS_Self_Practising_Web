from collections import defaultdict

from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import ClassroomAssignment, ClassroomMembership, ClassroomResource, User
from app.models.classroom_learning import ClassroomLearningPlan, ClassroomLearningPlanItem
from app.repositories.assignment_progress import aggregate_roots
from app.repositories.classroom_posts import ClassroomPostRepository
from app.schemas.classroom_learning import PlanItemResponse, PlanPage, PlanResponse
from app.services.classroom_capabilities import Capability, active_staff_clause, require_capability
from app.services.classroom_content_access import ContentAccess


class LearningPlanService:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor
        self.access = ContentAccess(session, actor)

    async def _present(self, room, plans):
        if not plans:
            return []
        items = list(
            await self.session.scalars(
                select(ClassroomLearningPlanItem)
                .where(
                    ClassroomLearningPlanItem.plan_id.in_([p.id for p in plans]),
                    ClassroomLearningPlanItem.active,
                )
                .order_by(ClassroomLearningPlanItem.position, ClassroomLearningPlanItem.id)
            )
        )
        assignment_ids = {i.assignment_id for i in items if i.assignment_id}
        resource_ids = {i.resource_id for i in items if i.resource_id}
        assignments = {
            a.id: a
            for a in await self.session.scalars(
                select(ClassroomAssignment).where(
                    ClassroomAssignment.id.in_(assignment_ids),
                    ClassroomAssignment.classroom_id == room.id,
                )
            )
        }
        resources = {
            r.id: r
            for r in await self.session.scalars(
                select(ClassroomResource).where(
                    ClassroomResource.id.in_(resource_ids),
                    ClassroomResource.classroom_id == room.id,
                )
            )
        }
        visible = {
            r[0]
            for r in await ClassroomPostRepository(self.session).resource_visibility(
                room.id, list(resource_ids)
            )
            if r[1] == "PUBLISHED" and r[2] in {None, "PUBLISHED"}
        }
        summaries = aggregate_roots(assignment_ids, {p.student_id for p in plans})
        accepted = {
            (row.assignment_id, row.user_id): row._mapping
            for row in await self.session.execute(select(summaries))
        }
        grouped = defaultdict(list)
        by_plan = {p.id: p for p in plans}
        for item in items:
            assignment, resource = (
                assignments.get(item.assignment_id),
                resources.get(item.resource_id),
            )
            summary = accepted.get((item.assignment_id, by_plan[item.plan_id].student_id), {})
            done = bool(summary.get("accepted")) if assignment else item.completed_at is not None
            available = (
                assignment is not None if item.assignment_id else item.resource_id in visible
            )
            title = (
                assignment.title or "IELTS assignment"
                if assignment
                else resource.title
                if resource and available
                else "Unavailable learning activity"
            )
            grouped[item.plan_id].append(
                PlanItemResponse(
                    id=item.id,
                    assignment_id=item.assignment_id,
                    resource_id=item.resource_id,
                    title=title,
                    available=available,
                    completed=done,
                    completed_at=summary.get("completed_at")
                    if assignment and done
                    else item.completed_at
                    if not assignment
                    else None,
                    completion_source="ACCEPTED_ASSIGNMENT"
                    if assignment and done
                    else "RESOURCE_MARKER"
                    if done
                    else "NONE",
                )
            )
        return [
            PlanResponse(
                **{
                    field: getattr(plan, field)
                    for field in PlanResponse.model_fields
                    if field not in {"items", "completed_items"}
                },
                items=grouped[plan.id],
                completed_items=sum(i.completed for i in grouped[plan.id]),
            )
            for plan in plans
        ]

    async def list(self, classroom_id, *, student_id=None, limit=30, offset=0):
        async with self.session.begin():
            room = await self.access.room(classroom_id)
            if Capability.GRADES_VIEW not in self.access.capabilities:
                if student_id is not None and student_id != self.actor.id:
                    raise AppError(
                        "LEARNING_PLAN_PRIVATE", "Only your own learning plans are available.", 403
                    )
                student_id = self.actor.id
            query = select(ClassroomLearningPlan).where(
                ClassroomLearningPlan.classroom_id == room.id
            )
            if student_id:
                query = query.where(ClassroomLearningPlan.student_id == student_id)
            total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
            plans = list(
                await self.session.scalars(
                    query.order_by(
                        ClassroomLearningPlan.created_at.desc(), ClassroomLearningPlan.id
                    )
                    .limit(limit)
                    .offset(offset)
                )
            )
            return PlanPage(items=await self._present(room, plans), total=total)

    async def write(self, classroom_id, student_id, data, *, plan_id=None):
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True)
            await require_capability(self.session, self.access.actor, room, Capability.PLANS)
            plan = (
                await self.session.scalar(
                    select(ClassroomLearningPlan)
                    .where(
                        ClassroomLearningPlan.id == plan_id,
                        ClassroomLearningPlan.classroom_id == room.id,
                        ClassroomLearningPlan.student_id == student_id,
                    )
                    .with_for_update()
                )
                if plan_id
                else None
            )
            if plan_id and not plan:
                raise AppError("LEARNING_PLAN_NOT_FOUND", "Learning plan not found.", 404)
            if plan and data.expected_revision != plan.revision:
                raise AppError("LEARNING_PLAN_CHANGED", "Reload the plan before saving.", 409)
            member = await self.session.scalar(
                select(ClassroomMembership.id)
                .join(User, User.id == ClassroomMembership.user_id)
                .where(
                    ClassroomMembership.classroom_id == room.id,
                    ClassroomMembership.user_id == student_id,
                    ClassroomMembership.left_at.is_(None),
                    User.is_active,
                    ~active_staff_clause(room.id, student_id),
                )
                .limit(1)
            )
            if not member and (not plan or data.status != "ARCHIVED"):
                raise AppError(
                    "ACTIVE_MEMBERSHIP_REQUIRED",
                    "An active student is required for a learning plan.",
                    409,
                )
            assignment_ids = {i.assignment_id for i in data.items if i.assignment_id}
            assignment_states = dict(
                (
                    await self.session.execute(
                        select(ClassroomAssignment.id, ClassroomAssignment.status).where(
                            ClassroomAssignment.classroom_id == room.id,
                            ClassroomAssignment.id.in_(assignment_ids),
                        )
                    )
                ).all()
            )
            resource_ids = {i.resource_id for i in data.items if i.resource_id}
            resource_states = await ClassroomPostRepository(self.session).resource_visibility(
                room.id, list(resource_ids)
            )
            visible = {
                r[0] for r in resource_states if r[1] == "PUBLISHED" and r[2] in {None, "PUBLISHED"}
            }
            if (
                set(assignment_states) != assignment_ids
                or {r[0] for r in resource_states} != resource_ids
            ):
                raise AppError(
                    "LEARNING_PLAN_TARGET_INVALID",
                    "Plan activities must belong to this classroom.",
                    422,
                )
            if data.status != "ARCHIVED" and (
                any(status != "ACTIVE" for status in assignment_states.values())
                or visible != resource_ids
            ):
                raise AppError(
                    "LEARNING_PLAN_TARGET_INVALID",
                    "Use published learning resources or active assignments in this classroom.",
                    422,
                )
            if not plan:
                plan = ClassroomLearningPlan(
                    classroom_id=room.id,
                    student_id=student_id,
                    created_by_user_id=self.actor.id,
                    updated_by_user_id=self.actor.id,
                    **data.model_dump(exclude={"items", "expected_revision"}),
                )
                self.session.add(plan)
                await self.session.flush()
            else:
                for key, value in data.model_dump(exclude={"items", "expected_revision"}).items():
                    setattr(plan, key, value)
                plan.revision += 1
                plan.updated_by_user_id = self.actor.id
                plan.updated_at = TimerService.now()
            existing = list(
                await self.session.scalars(
                    select(ClassroomLearningPlanItem).where(
                        ClassroomLearningPlanItem.plan_id == plan.id
                    )
                )
            )
            lookup = {(item.assignment_id, item.resource_id): item for item in existing}
            for item in existing:
                item.active = False
            for position, target in enumerate(data.items):
                item = lookup.get((target.assignment_id, target.resource_id))
                if item:
                    item.active, item.position = True, position
                else:
                    self.session.add(
                        ClassroomLearningPlanItem(
                            classroom_id=room.id,
                            plan_id=plan.id,
                            position=position,
                            **target.model_dump(),
                        )
                    )
            await self.session.flush()
            response = (await self._present(room, [plan]))[0]
            if data.status == "COMPLETED" and response.completed_items != len(response.items):
                raise AppError(
                    "LEARNING_PLAN_INCOMPLETE",
                    "Complete linked activities before closing the plan.",
                    409,
                )
            return response

    async def complete_resource(self, classroom_id, plan_id, item_id):
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True)
            plan = await self.session.scalar(
                select(ClassroomLearningPlan)
                .where(
                    ClassroomLearningPlan.id == plan_id,
                    ClassroomLearningPlan.classroom_id == room.id,
                    ClassroomLearningPlan.student_id == self.actor.id,
                )
                .with_for_update()
            )
            if not plan or plan.status != "ACTIVE":
                raise AppError(
                    "LEARNING_PLAN_NOT_FOUND", "Active personal learning plan not found.", 404
                )
            member = await self.session.scalar(
                select(ClassroomMembership.id)
                .where(
                    ClassroomMembership.classroom_id == room.id,
                    ClassroomMembership.user_id == self.actor.id,
                    ClassroomMembership.left_at.is_(None),
                    ~active_staff_clause(room.id, self.actor.id),
                )
                .limit(1)
            )
            if not member:
                raise AppError(
                    "ACTIVE_MEMBERSHIP_REQUIRED", "An active student membership is required.", 403
                )
            item = await self.session.scalar(
                select(ClassroomLearningPlanItem)
                .where(
                    ClassroomLearningPlanItem.id == item_id,
                    ClassroomLearningPlanItem.plan_id == plan.id,
                    ClassroomLearningPlanItem.active,
                    ClassroomLearningPlanItem.resource_id.is_not(None),
                )
                .with_for_update()
            )
            if not item:
                raise AppError(
                    "RESOURCE_TASK_REQUIRED",
                    "Only a non-assessment resource task can be marked manually.",
                    422,
                )
            visible = await ClassroomPostRepository(self.session).resource_visibility(
                room.id, [item.resource_id]
            )
            if (
                not visible
                or visible[0][1] != "PUBLISHED"
                or visible[0][2] not in {None, "PUBLISHED"}
            ):
                raise AppError("RESOURCE_NOT_ACCESSIBLE", "The resource is not available.", 404)
            if item.completed_at is None:
                item.completed_at, item.completed_by_user_id = TimerService.now(), self.actor.id
            await self.session.flush()
            return (await self._present(room, [plan]))[0]
