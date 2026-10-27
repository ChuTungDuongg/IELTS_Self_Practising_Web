"""Authorized classroom deletion removes assessment data; DB-free query contracts."""

from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

from app.core.exceptions import AppError
from app.models import Attempt, ClassroomAssignment
from app.models.base import Base
from app.models.classroom_classwork import ClassroomResource
from app.models.enums import UserRole
from app.services.classroom_classwork import ClassworkService
from app.services.classroom_deletion import cancel_deleted_assignment_workers
from tests.test_classroom_archive_unit import assignment, services
from tests.test_classroom_classwork_unit import actor, classroom


def sql(statement):
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


async def test_assignment_delete_removes_attempts_sessions_references_and_notifications():
    owner = actor()
    room = classroom(owner)
    assigned = assignment(room)
    service, session = services(owner, room, assigned, protected=Attempt)
    await service.delete(room.id, assigned.id)
    statements = [sql(call.args[0]) for call in session.execute.call_args_list]
    for table in (
        "attempts",
        "test_sessions",
        "classroom_assignment_extensions",
        "classroom_assignment_policy_events",
        "classroom_learning_plan_items",
        "notifications",
        "classroom_content_items",
    ):
        deletion = next(
            statement for statement in statements if statement.startswith(f"DELETE FROM {table} ")
        )
        assert str(assigned.id) in deletion
    attempt_delete = next(
        statement for statement in statements if statement.startswith("DELETE FROM attempts ")
    )
    assert "attempts.classroom_assignment_id" in attempt_delete
    assert "attempts.test_session_id IN (SELECT test_sessions.id" in attempt_delete
    notifications = next(
        statement for statement in statements if statement.startswith("DELETE FROM notifications ")
    )
    assert "CLASSROOM_ASSIGNMENT" in notifications and "assignment_id" in notifications
    assert not any(statement.startswith("DELETE FROM test_versions") for statement in statements)
    session.delete.assert_awaited_once_with(assigned)
    assert room.content_revision == 8


async def test_resource_delete_detaches_posts_and_plans_before_removing_resource():
    owner = actor()
    room = classroom(owner)
    _, session = services(owner, room, None)
    resource = ClassroomResource(
        id=uuid4(), classroom_id=room.id, title="Fictional", kind="TEXT", body="Notes"
    )
    service = ClassworkService(session, owner)
    service.repository.resource = AsyncMock(return_value=resource)
    service._snapshot = AsyncMock(return_value="snapshot")
    # Old service incorrectly refuses either reference rather than deleting its link.
    original = session.scalar.side_effect

    async def scalar(statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity.__tablename__ in {"classroom_post_resources", "classroom_learning_plan_items"}:
            return resource.id
        return await original(statement)

    session.scalar.side_effect = scalar
    assert await service.delete_resource(room.id, resource.id) == "snapshot"
    statements = [sql(call.args[0]) for call in session.execute.call_args_list]
    for table in (
        "classroom_post_resources",
        "classroom_learning_plan_items",
        "classroom_content_items",
    ):
        assert any(
            statement.startswith(f"DELETE FROM {table} ") and str(resource.id) in statement
            for statement in statements
        )
    assert any(
        statement.startswith("UPDATE classroom_learning_plans") and "revision" in statement
        for statement in statements
    )
    assert not any(statement.startswith("DELETE FROM classroom_posts") for statement in statements)
    session.delete.assert_awaited_once_with(resource)


def test_attempt_and_full_mock_children_cascade_without_deleting_shared_exam_content():
    expected = {
        "attempt_answers",
        "attempt_events",
        "attempt_speaking_scores",
        "attempt_writing_responses",
        "attempt_writing_scores",
        "highlights",
        "question_flags",
        "speaking_ai_grading_runs",
        "speaking_responses",
        "speaking_transcript_runs",
        "writing_ai_grading_runs",
        "writing_ai_practice_feedback",
        "speaking_prompt_progress",
    }
    actual = set()
    for table in Base.metadata.tables.values():
        for fk in table.foreign_key_constraints:
            if fk.referred_table.name == "attempts":
                assert fk.ondelete == "CASCADE"
                actual.add(table.name)
    assert expected <= actual
    attempt = Base.metadata.tables["attempts"]
    assert (
        next(
            fk
            for fk in attempt.foreign_key_constraints
            if fk.referred_table.name == "test_sessions"
        ).ondelete
        == "CASCADE"
    )
    assert (
        next(
            fk
            for fk in ClassroomAssignment.__table__.foreign_key_constraints
            if fk.referred_table.name == "test_versions"
        ).ondelete
        == "RESTRICT"
    )


def test_migration_allows_policy_deletion_while_policy_updates_remain_immutable():
    path = Path(__file__).parents[1] / "alembic/versions/20261028_0042_classroom_hard_delete.py"
    spec = spec_from_file_location("classroom_hard_delete_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "20261027_0041"
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        migration.upgrade()
    emitted = output.getvalue()
    assert "DROP TRIGGER assignment_policy_events_immutable" in emitted
    assert "BEFORE UPDATE ON classroom_assignment_policy_events" in emitted
    assert "BEFORE UPDATE OR DELETE" not in emitted
    assert "DELETE FROM" not in emitted
    output.truncate(0)
    output.seek(0)
    with Operations.context(context):
        migration.downgrade()
    assert "BEFORE UPDATE OR DELETE" in output.getvalue()


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.USER, UserRole.TEACHER])
async def test_hard_delete_denies_admin_student_and_unrelated_teacher_before_cleanup(
    role, monkeypatch
):
    owner = actor()
    room = classroom(owner)
    assigned = assignment(room)
    service, session = services(actor(role), room, assigned)
    cleanup = AsyncMock()
    monkeypatch.setattr("app.services.classroom_deletion.delete_assignment_data", cleanup)
    with pytest.raises(AppError):
        await service.delete(room.id, assigned.id)
    cleanup.assert_not_awaited()
    session.delete.assert_not_awaited()
    session.execute.assert_not_awaited()


async def test_failed_delete_does_not_cancel_workers_before_transaction_commit(monkeypatch):
    owner = actor()
    room = classroom(owner)
    assigned = assignment(room)
    service, session = services(owner, room, assigned)
    session.flush.side_effect = RuntimeError("rollback")
    cancel = Mock()
    monkeypatch.setattr("app.services.classroom_deletion.cancel_deleted_assignment_workers", cancel)
    with pytest.raises(RuntimeError, match="rollback"):
        await service.delete(room.id, assigned.id)
    cancel.assert_not_called()


def test_after_commit_cancellation_is_limited_to_deleted_assignment_runs(monkeypatch):
    writing, speaking, transcript = Mock(), Mock(), Mock()
    monkeypatch.setattr("app.services.writing_ai_worker.cancel_writing_ai_worker", writing)
    monkeypatch.setattr("app.services.speaking_ai_worker.cancel_speaking_ai_worker", speaking)
    monkeypatch.setattr(
        "app.services.speaking_transcript_worker.cancel_speaking_transcript_worker", transcript
    )
    ids = [uuid4(), uuid4(), uuid4()]
    cancel_deleted_assignment_workers(
        dict(zip(["writing", "speaking", "transcript"], ([id] for id in ids), strict=True))
    )
    writing.assert_called_once_with(ids[0], source="assignment_deletion")
    speaking.assert_called_once_with(ids[1])
    transcript.assert_called_once_with(ids[2])


async def test_private_media_keys_are_queued_before_attempt_rows_are_deleted():
    from app.models.speaking import SpeakingAudioChunk
    from app.models.speaking_ai import SpeakingAIGradingRun
    from app.models.speaking_transcript import SpeakingNormalizedAudio, SpeakingTranscriptRun
    from app.models.writing_ai import WritingAIGradingRun

    owner = actor()
    room = classroom(owner)
    assigned = assignment(room)
    service, session = services(owner, room, assigned)
    ids = {
        model: uuid4()
        for model in (WritingAIGradingRun, SpeakingAIGradingRun, SpeakingTranscriptRun)
    }

    async def rows(statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity in ids:
            return [ids[entity]]
        if entity == SpeakingAudioChunk:
            return ["raw-private-key"]
        if entity == SpeakingNormalizedAudio:
            return ["normalized-private-key"]
        return []

    session.scalars.side_effect = rows
    await service.delete(room.id, assigned.id)
    statements = [sql(call.args[0]) for call in session.execute.call_args_list]
    queued = [
        index
        for index, statement in enumerate(statements)
        if statement.startswith("INSERT INTO speaking_media_cleanup")
    ]
    assert len(queued) == 2
    assert "raw-private-key" in statements[queued[0]] or "raw-private-key" in statements[queued[1]]
    assert (
        "normalized-private-key" in statements[queued[0]]
        or "normalized-private-key" in statements[queued[1]]
    )
    assert max(queued) < next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("DELETE FROM attempts ")
    )
