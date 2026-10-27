"""Classroom-owned hard deletion; shared immutable exam content is never a target."""

from sqlalchemy import delete, or_, select, update

from app.domains.timers import TimerService
from app.models import Attempt, Notification, TestSession
from app.models.assignment_scheduling import AssignmentPolicyEvent, ClassroomAssignmentExtension
from app.models.classroom_classwork import ClassroomContentItem
from app.models.classroom_learning import ClassroomLearningPlan, ClassroomLearningPlanItem
from app.models.enums import NotificationEntityType
from app.models.speaking import SpeakingResponse
from app.models.speaking_ai import SpeakingAIGradingRun
from app.models.speaking_transcript import SpeakingTranscriptRun
from app.models.writing_ai import WritingAIGradingRun
from app.services.speaking_media import queue_media_cleanup


async def remove_plan_references(
    session, room_id, actor_id, *, assignment_id=None, resource_id=None
):
    target = (
        ClassroomLearningPlanItem.assignment_id == assignment_id
        if assignment_id is not None
        else ClassroomLearningPlanItem.resource_id == resource_id
    )
    scope = (ClassroomLearningPlanItem.classroom_id == room_id, target)
    # Invalidate outstanding plan edits before removing only the affected activities.
    await session.execute(
        update(ClassroomLearningPlan)
        .where(
            ClassroomLearningPlan.classroom_id == room_id,
            ClassroomLearningPlan.id.in_(select(ClassroomLearningPlanItem.plan_id).where(*scope)),
        )
        .values(
            revision=ClassroomLearningPlan.revision + 1,
            updated_by_user_id=actor_id,
            updated_at=TimerService.now(),
        )
        .execution_options(synchronize_session=False)
    )
    await session.execute(delete(ClassroomLearningPlanItem).where(*scope))


async def delete_assignment_data(session, room, assignment, actor_id):
    """Caller holds actor -> classroom -> assignment locks inside its transaction."""
    session_scope = select(TestSession.id).where(
        TestSession.classroom_assignment_id == assignment.id
    )
    await session.scalars(session_scope.order_by(TestSession.id).with_for_update())
    attempt_scope = or_(
        Attempt.classroom_assignment_id == assignment.id,
        Attempt.test_session_id.in_(session_scope),
    )
    attempt_ids = select(Attempt.id).where(attempt_scope)
    await session.scalars(attempt_ids.order_by(Attempt.id).with_for_update())
    workers = {}
    # Fence checkpoints before locking response rows: workers lock run -> response.
    for kind, model in (
        ("writing", WritingAIGradingRun),
        ("speaking", SpeakingAIGradingRun),
        ("transcript", SpeakingTranscriptRun),
    ):
        workers[kind] = list(
            await session.scalars(
                select(model.id)
                .where(model.attempt_id.in_(attempt_ids))
                .order_by(model.id)
                .with_for_update()
            )
        )
    # Prevent a decoder from committing a new derived file after its cleanup keys
    # were collected. Its FK insert then fails safely if the response was deleted.
    await session.scalars(
        select(SpeakingResponse.id)
        .where(SpeakingResponse.attempt_id.in_(attempt_ids))
        .order_by(SpeakingResponse.id)
        .with_for_update()
    )
    await queue_media_cleanup(session, attempt_ids)
    await remove_plan_references(session, room.id, actor_id, assignment_id=assignment.id)
    for model in (ClassroomAssignmentExtension, AssignmentPolicyEvent):
        await session.execute(delete(model).where(model.assignment_id == assignment.id))
    await session.execute(
        delete(Notification).where(
            Notification.entity_type == NotificationEntityType.CLASSROOM_ASSIGNMENT,
            or_(
                Notification.entity_id == assignment.id,
                Notification.payload_json["assignment_id"].astext == str(assignment.id),
            ),
        )
    )
    await session.execute(
        delete(ClassroomContentItem).where(
            ClassroomContentItem.classroom_id == room.id,
            ClassroomContentItem.assignment_id == assignment.id,
        )
    )
    # Existing FK CASCADE trees remove answers, final scores, events, flags,
    # Writing AI/adoption, Speaking responses/takes/chunks/transcripts/AI runs.
    await session.execute(
        delete(Attempt).where(attempt_scope).execution_options(synchronize_session=False)
    )
    await session.execute(
        delete(TestSession)
        .where(TestSession.classroom_assignment_id == assignment.id)
        .execution_options(synchronize_session=False)
    )
    return workers


def cancel_deleted_assignment_workers(workers):
    """After commit, interrupt local providers; other processes stop at DB fences."""
    if not any(workers.values()):
        return
    from app.services.speaking_ai_worker import cancel_speaking_ai_worker
    from app.services.speaking_transcript_worker import cancel_speaking_transcript_worker
    from app.services.writing_ai_worker import cancel_writing_ai_worker

    for run_id in workers["writing"]:
        cancel_writing_ai_worker(run_id, source="assignment_deletion")
    for run_id in workers["speaking"]:
        cancel_speaking_ai_worker(run_id)
    for run_id in workers["transcript"]:
        cancel_speaking_transcript_worker(run_id)
