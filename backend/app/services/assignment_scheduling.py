"""Scheduling mutations and private exceptions; no exam lifecycle or scoring changes."""

from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError
from sqlalchemy import select

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import ClassroomAssignment, ClassroomMembership, User
from app.models.assignment_scheduling import AssignmentPolicyEvent, ClassroomAssignmentExtension
from app.models.enums import NotificationEntityType, NotificationType
from app.repositories.assignment_progress import AssignmentProgressRepository
from app.schemas.assignment_scheduling import (
    AssignmentScheduleUpdate,
    ExtensionResponse,
    ExtensionWrite,
    SchedulePolicy,
)
from app.services.assignment_policy import resolve_policy, start_denial
from app.services.classroom_content_access import ContentAccess
from app.services.notifications import NotificationService


async def effective_policy(session, assignment, student_id):
    extension = await AssignmentProgressRepository(session).extension(assignment.id, student_id)
    return resolve_policy(SchedulePolicy.model_validate(assignment), extension), extension


async def enforce_schedule_start(session, assignment, student_id):
    policy, _ = await effective_policy(session, assignment, student_id)
    used = await AssignmentProgressRepository(session).usage(assignment.id, student_id)
    code = start_denial(policy, TimerService.now(), used)
    if code:
        raise AppError(
            code,
            {
                "ASSIGNMENT_SCHEDULED": "This assignment is not open yet.",
                "ASSIGNMENT_CLOSED": "The assignment cut-off has passed.",
                "ASSIGNMENT_LATE_DISABLED": "The due date has passed and late submissions are disabled.",
                "ASSIGNMENT_ATTEMPT_LIMIT": "All assignment starts have been used. You may resume existing work.",
            }[code],
            409,
        )


async def policy_event(session, assignment, actor_id, *, extension=None, kind, reason=None):
    assignment.policy_revision += 1
    data = SchedulePolicy.model_validate(assignment).model_dump()
    if extension:
        data.update(
            due_at=extension.due_at_override,
            cutoff_at=extension.cutoff_at_override,
            override_due=extension.override_due,
            override_cutoff=extension.override_cutoff,
            additional_attempts=extension.additional_attempts,
            revoked=extension.revoked,
        )
    event = AssignmentPolicyEvent(
        assignment_id=assignment.id,
        student_id=extension.student_id if extension else None,
        actor_id=actor_id,
        revision=assignment.policy_revision,
        kind=kind,
        reason=reason,
        **data,
    )
    session.add(event)
    await session.flush()
    return event


async def notify_assignment(session, assignment, kind, event_key, *, student_id=None, extra=None):
    recipients = (
        select(ClassroomMembership.user_id)
        .join(User, User.id == ClassroomMembership.user_id)
        .where(
            ClassroomMembership.classroom_id == assignment.classroom_id,
            ClassroomMembership.left_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if student_id is not None:
        recipients = recipients.where(ClassroomMembership.user_id == student_id)
    for recipient in await session.scalars(recipients.order_by(ClassroomMembership.user_id)):
        await NotificationService(session).create_once(
            user_id=recipient,
            type=NotificationType(kind),
            entity_type=NotificationEntityType.CLASSROOM_ASSIGNMENT,
            entity_id=uuid5(NAMESPACE_URL, f"assignment:{assignment.id}:{kind}:{event_key}"),
            payload={
                "classroom_id": str(assignment.classroom_id),
                "assignment_id": str(assignment.id),
                "assignment_title": assignment.title or "",
                "event": kind,
                **(extra or {}),
            },
        )


class AssignmentSchedulingService:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor
        self.access = ContentAccess(session, actor)

    async def assignment(self, classroom_id, assignment_id, *, mutation=False):
        room = await self.access.room(classroom_id, mutation=mutation, owner=mutation)
        query = (
            select(ClassroomAssignment)
            .where(
                ClassroomAssignment.classroom_id == room.id, ClassroomAssignment.id == assignment_id
            )
            .execution_options(populate_existing=True)
        )
        if mutation:
            query = query.with_for_update()
        assignment = await self.session.scalar(query)
        if assignment is None:
            raise AppError(
                "ASSIGNMENT_NOT_ACCESSIBLE", "Assignment not found in this classroom.", 404
            )
        if mutation and assignment.status != "ACTIVE":
            raise AppError("ASSIGNMENT_ARCHIVED", "The assignment is archived and read-only.", 409)
        return room, assignment

    @staticmethod
    def validate_extension(base, extension):
        try:
            result = resolve_policy(base, extension)
            if not extension.revoked:
                for field, override in (
                    ("due_at", "override_due"),
                    ("cutoff_at", "override_cutoff"),
                ):
                    original, changed = getattr(base, field), getattr(result, field)
                    if getattr(extension, override) and original is None and changed is not None:
                        raise ValueError(
                            "An extension cannot introduce a deadline where the base policy has none"
                        )
                    if getattr(extension, override) and original and changed and changed < original:
                        raise ValueError("Extensions may not shorten the base deadline")
            return result
        except (ValidationError, ValueError) as error:
            raise AppError(
                "ASSIGNMENT_POLICY_INVALID",
                "The effective extension dates are invalid or shorten the base policy.",
                422,
            ) from error

    async def update(self, classroom_id, assignment_id, data: AssignmentScheduleUpdate):
        from app.schemas.classroom_assignments import AssignmentResponse

        async with self.session.begin():
            _, assignment = await self.assignment(classroom_id, assignment_id, mutation=True)
            if assignment.policy_revision != data.expected_revision:
                raise AppError(
                    "ASSIGNMENT_CHANGED", "Assignment changed; reload before saving.", 409
                )
            values = data.model_dump(exclude_unset=True, exclude={"expected_revision", "reason"})
            merged = {
                **SchedulePolicy.model_validate(assignment).model_dump(),
                **{
                    key: value
                    for key, value in values.items()
                    if key in SchedulePolicy.model_fields
                },
            }
            try:
                base = SchedulePolicy.model_validate(merged)
            except ValidationError as error:
                raise AppError(
                    "ASSIGNMENT_POLICY_INVALID", "The combined schedule is invalid.", 422
                ) from error
            extensions = list(
                await self.session.scalars(
                    select(ClassroomAssignmentExtension).where(
                        ClassroomAssignmentExtension.assignment_id == assignment.id,
                        ClassroomAssignmentExtension.revoked.is_(False),
                    )
                )
            )
            for extension in extensions:
                self.validate_extension(base, extension)
            if all(getattr(assignment, key) == value for key, value in values.items()):
                return AssignmentResponse.model_validate(assignment)
            schedule_changed = any(
                key in SchedulePolicy.model_fields and getattr(assignment, key) != value
                for key, value in values.items()
            )
            for key, value in values.items():
                setattr(assignment, key, value)
            event = await policy_event(
                self.session, assignment, self.actor.id, kind="SCHEDULE_CHANGED", reason=data.reason
            )
            if schedule_changed:
                await notify_assignment(
                    self.session, assignment, "ASSIGNMENT_SCHEDULE_CHANGED", str(event.id)
                )
            return AssignmentResponse.model_validate(assignment)

    async def extensions(self, classroom_id, assignment_id):
        async with self.session.begin():
            room, assignment = await self.assignment(classroom_id, assignment_id)
            if not self.access.staff(room):
                raise AppError("CLASSROOM_OWNERSHIP_REQUIRED", "Staff oversight is required.", 403)
            rows = await self.session.scalars(
                select(ClassroomAssignmentExtension)
                .where(ClassroomAssignmentExtension.assignment_id == assignment.id)
                .order_by(ClassroomAssignmentExtension.student_id)
            )
            return [ExtensionResponse.model_validate(row) for row in rows]

    async def write_extension(
        self, classroom_id, assignment_id, student_id, data: ExtensionWrite | None
    ):
        async with self.session.begin():
            _, assignment = await self.assignment(classroom_id, assignment_id, mutation=True)
            extension = await AssignmentProgressRepository(self.session).extension(
                assignment.id, student_id
            )
            if data is not None:
                member = await self.session.scalar(
                    select(ClassroomMembership.id).where(
                        ClassroomMembership.classroom_id == classroom_id,
                        ClassroomMembership.user_id == student_id,
                        ClassroomMembership.left_at.is_(None),
                    )
                )
                if member is None:
                    raise AppError(
                        "ACTIVE_MEMBERSHIP_REQUIRED", "Choose an active enrolled student.", 422
                    )
                values = data.model_dump()
                if extension is None:
                    extension = ClassroomAssignmentExtension(
                        assignment_id=assignment.id,
                        student_id=student_id,
                        created_by_user_id=self.actor.id,
                        revision=0,
                        revoked=False,
                        **values,
                    )
                    self.session.add(extension)
                else:
                    if not extension.revoked and all(
                        getattr(extension, key) == value for key, value in values.items()
                    ):
                        return ExtensionResponse.model_validate(extension)
                    for key, value in values.items():
                        setattr(extension, key, value)
                    extension.revoked = False
                self.validate_extension(SchedulePolicy.model_validate(assignment), extension)
            else:
                if extension is None:
                    raise AppError("EXTENSION_NOT_FOUND", "The extension does not exist.", 404)
                if extension.revoked:
                    return ExtensionResponse.model_validate(extension)
                extension.revoked = True
            extension.revision += 1
            event = await policy_event(
                self.session,
                assignment,
                self.actor.id,
                extension=extension,
                kind="EXTENSION_REVOKED" if data is None else "EXTENSION_GRANTED",
                reason=extension.reason,
            )
            await notify_assignment(
                self.session,
                assignment,
                "ASSIGNMENT_EXTENSION_GRANTED",
                str(event.id),
                student_id=student_id,
            )
            await self.session.refresh(extension)
            return ExtensionResponse.model_validate(extension)

    async def history(self, classroom_id, assignment_id, *, offset=0, limit=50):
        async with self.session.begin():
            room, assignment = await self.assignment(classroom_id, assignment_id)
            if not self.access.staff(room):
                raise AppError("CLASSROOM_OWNERSHIP_REQUIRED", "Staff oversight is required.", 403)
            rows = await self.session.scalars(
                select(AssignmentPolicyEvent)
                .where(AssignmentPolicyEvent.assignment_id == assignment.id)
                .order_by(AssignmentPolicyEvent.revision.desc())
                .offset(offset)
                .limit(limit)
            )
            return [
                {
                    "id": row.id,
                    "revision": row.revision,
                    "student_id": row.student_id,
                    "actor_id": row.actor_id,
                    "kind": row.kind,
                    "effective_at": row.effective_at,
                    "reason": row.reason,
                    "policy": {key: getattr(row, key) for key in SchedulePolicy.model_fields},
                    "override_due": row.override_due,
                    "override_cutoff": row.override_cutoff,
                    "additional_attempts": row.additional_attempts,
                    "revoked": row.revoked,
                }
                for row in rows
            ]
