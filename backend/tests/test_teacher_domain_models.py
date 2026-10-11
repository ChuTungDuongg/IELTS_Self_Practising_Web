from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.models import (
    Attempt,
    Classroom,
    ClassroomAssignment,
    ClassroomInvitation,
    ClassroomMembership,
    Notification,
    TestVersionModeration,
)
from app.models import Test as TestModel
from app.models import TestSession as SessionModel
from app.models.enums import TestOrigin, UserRole, VersionStatus


def test_roles_ownership_and_legacy_contract():
    assert UserRole.TEACHER.value == "TEACHER"
    assert set(VersionStatus) == {
        VersionStatus.DRAFT,
        VersionStatus.PUBLISHED,
        VersionStatus.ARCHIVED,
    }
    legacy = TestModel(title="Fictional legacy", origin=TestOrigin.ADMIN)
    assert legacy.owner_user_id is None
    assert TestModel.__table__.c.owner_user_id.nullable
    assert TestModel.__table__.c.origin.nullable is False


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
        TestVersionModeration,
    ):
        assert all(fk.ondelete == "RESTRICT" for fk in model.__table__.foreign_keys)


def test_partial_uniqueness_and_notification_contract():
    expected = [
        (ClassroomMembership, "left_at IS NULL"),
        (ClassroomInvitation, "status = 'PENDING'"),
        (TestVersionModeration, "status = 'PENDING'"),
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
