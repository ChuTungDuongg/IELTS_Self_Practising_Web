import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.models import (
    Attempt,
    Classroom,
    ClassroomAssignment,
    ClassroomInvitation,
    ClassroomMembership,
    Notification,
)
from app.models import Test as ContentTest
from app.models import TestSession as SessionModel
from app.models import TestVersionModeration as Moderation
from app.models.enums import TestOrigin as ContentOrigin
from app.models.enums import UserRole, VersionStatus


def test_roles_ownership_and_legacy_contract():
    assert UserRole.TEACHER.value == "TEACHER"
    assert set(VersionStatus) == {
        VersionStatus.DRAFT,
        VersionStatus.PUBLISHED,
        VersionStatus.ARCHIVED,
    }
    legacy = ContentTest(title="Fictional legacy", origin=ContentOrigin.ADMIN)
    assert legacy.owner_user_id is None
    assert ContentTest.__table__.c.owner_user_id.nullable
    assert ContentTest.__table__.c.origin.nullable is False


def test_provenance_foreign_keys_preserve_history():
    for model in (Attempt, SessionModel):
        column = model.__table__.c.classroom_assignment_id
        assert column.nullable
        assert next(iter(column.foreign_keys)).ondelete == "RESTRICT"
    for model in (
        Classroom,
        ClassroomAssignment,
        ClassroomInvitation,
        ClassroomMembership,
        Moderation,
    ):
        assert all(fk.ondelete == "RESTRICT" for fk in model.__table__.foreign_keys)


def test_full_mock_cannot_store_a_second_assignment_on_child_attempt():
    assert any(
        "classroom_assignment_id IS NULL OR test_session_id IS NULL"
        in str(getattr(constraint, "sqltext", ""))
        for constraint in Attempt.__table__.constraints
    )


def test_partial_uniqueness_and_notification_contract():
    expected = [
        (ClassroomMembership, "left_at IS NULL"),
        (ClassroomInvitation, "status = 'PENDING'"),
        (Moderation, "status = 'PENDING'"),
    ]
    for model, predicate in expected:
        indexes = [
            str(CreateIndex(idx).compile(dialect=postgresql.dialect()))
            for idx in model.__table__.indexes
            if idx.unique
        ]
        assert any(predicate in sql for sql in indexes)
    assert {
        "user_id",
        "type",
        "payload_json",
        "entity_type",
        "entity_id",
        "read_at",
        "created_at",
    } <= set(Notification.__table__.c.keys())
    assert any(
        constraint.__class__.__name__ == "UniqueConstraint"
        for constraint in Notification.__table__.constraints
    )


async def test_downgrade_preserves_teacher_origin_after_owner_role_changes(db_session, monkeypatch):
    migration_path = (
        Path(__file__).parents[1] / "alembic/versions/20261011_0024_teacher_classroom_governance.py"
    )
    spec = importlib.util.spec_from_file_location("teacher_governance_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with db_session.begin():
        db_session.add(
            ContentTest(
                title="Fictional former teacher contribution",
                owner_user_id=db_session.info["current_user_id"],
                origin=ContentOrigin.TEACHER,
            )
        )
        await db_session.flush()

        def downgrade(sync_session):
            monkeypatch.setattr(
                migration,
                "op",
                SimpleNamespace(
                    get_bind=sync_session.connection,
                    f=lambda name: name,
                    drop_constraint=lambda *args, **kwargs: pytest.fail(
                        "Downgrade must reject before deleting governance metadata"
                    ),
                ),
            )
            migration.downgrade()

        with pytest.raises(RuntimeError, match="teacher-origin content"):
            await db_session.run_sync(downgrade)
