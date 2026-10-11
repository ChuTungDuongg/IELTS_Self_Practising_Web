"""teacher_classroom_governance

Revision ID: 20261011_0024
Revises: 20261011_0023
Create Date: 2026-10-11 17:17:37.923401
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261011_0024"
down_revision: str | None = "20261011_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL requires a commit before a new enum label can be used.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'TEACHER'")
    sa.Enum("ADMIN", "TEACHER", name="test_origin").create(op.get_bind(), checkfirst=True)
    op.create_table(
        "classrooms",
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("ACTIVE", "ARCHIVED", name="classroom_status"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["users.id"],
            name=op.f("fk_classrooms_teacher_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classrooms")),
    )
    op.create_index(op.f("ix_classrooms_teacher_id"), "classrooms", ["teacher_id"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "CLASSROOM_INVITED",
                "CLASSROOM_INVITATION_ACCEPTED",
                "CLASSROOM_INVITATION_DECLINED",
                "TEST_CLASSROOM_APPROVED",
                "TEST_CLASSROOM_REJECTED",
                "TEST_PUBLIC_APPROVED",
                "TEST_PUBLIC_REJECTED",
                "CLASSROOM_ARCHIVED",
                name="notification_type",
            ),
            nullable=False,
        ),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "entity_type",
            sa.Enum("INVITATION", "MODERATION", "CLASSROOM", name="notification_entity_type"),
            nullable=False,
        ),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "user_id", "type", "entity_type", "entity_id", name="uq_notification_event_recipient"
        ),
    )
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["user_id", "read_at", "created_at"],
        unique=False,
    )
    op.create_table(
        "classroom_invitations",
        sa.Column("classroom_id", sa.Uuid(), nullable=False),
        sa.Column("invited_email", sa.String(length=320), nullable=False),
        sa.Column("invited_email_normalized", sa.String(length=320), nullable=False),
        sa.Column("invited_user_id", sa.Uuid(), nullable=True),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ACCEPTED", "DECLINED", "CANCELLED", name="invitation_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name=op.f("fk_classroom_invitations_classroom_id_classrooms"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name=op.f("fk_classroom_invitations_invited_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invited_user_id"],
            ["users.id"],
            name=op.f("fk_classroom_invitations_invited_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classroom_invitations")),
    )
    op.create_index(
        op.f("ix_classroom_invitations_classroom_id"),
        "classroom_invitations",
        ["classroom_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_classroom_invitations_invited_email_normalized"),
        "classroom_invitations",
        ["invited_email_normalized"],
        unique=False,
    )
    op.create_index(
        op.f("ix_classroom_invitations_invited_user_id"),
        "classroom_invitations",
        ["invited_user_id"],
        unique=False,
    )
    op.create_index(
        "uq_classroom_pending_invitation",
        "classroom_invitations",
        ["classroom_id", "invited_email_normalized"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_table(
        "classroom_memberships",
        sa.Column("classroom_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name=op.f("fk_classroom_memberships_classroom_id_classrooms"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["removed_by_user_id"],
            ["users.id"],
            name=op.f("fk_classroom_memberships_removed_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_classroom_memberships_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classroom_memberships")),
    )
    op.create_index(
        op.f("ix_classroom_memberships_classroom_id"),
        "classroom_memberships",
        ["classroom_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_classroom_memberships_user_id"), "classroom_memberships", ["user_id"], unique=False
    )
    op.create_index(
        "uq_classroom_active_membership",
        "classroom_memberships",
        ["classroom_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("left_at IS NULL"),
    )
    op.create_table(
        "classroom_assignments",
        sa.Column("classroom_id", sa.Uuid(), nullable=False),
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.Enum("ACTIVE", "ARCHIVED", name="assignment_status"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name=op.f("fk_classroom_assignments_classroom_id_classrooms"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_classroom_assignments_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["test_version_id"],
            ["test_versions.id"],
            name=op.f("fk_classroom_assignments_test_version_id_test_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classroom_assignments")),
    )
    op.create_index(
        op.f("ix_classroom_assignments_classroom_id"),
        "classroom_assignments",
        ["classroom_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_classroom_assignments_test_version_id"),
        "classroom_assignments",
        ["test_version_id"],
        unique=False,
    )
    op.create_table(
        "test_version_moderation",
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.Enum("CLASSROOM", "PUBLIC", name="moderation_scope"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "APPROVED", "REJECTED", "REVOKED", "CANCELLED", name="moderation_status"
            ),
            nullable=False,
        ),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("submit_note", sa.String(length=2000), nullable=True),
        sa.Column("review_note", sa.String(length=2000), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoke_reason", sa.String(length=2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name=op.f("fk_test_version_moderation_reviewed_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"],
            ["users.id"],
            name=op.f("fk_test_version_moderation_revoked_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            name=op.f("fk_test_version_moderation_submitted_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["test_version_id"],
            ["test_versions.id"],
            name=op.f("fk_test_version_moderation_test_version_id_test_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_version_moderation")),
    )
    op.create_index(
        op.f("ix_test_version_moderation_status"),
        "test_version_moderation",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_test_version_moderation_test_version_id"),
        "test_version_moderation",
        ["test_version_id"],
        unique=False,
    )
    op.create_index(
        "uq_moderation_pending_scope",
        "test_version_moderation",
        ["test_version_id", "scope"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.add_column("attempts", sa.Column("classroom_assignment_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        op.f("ck_attempts_classroom_provenance_standalone"),
        "attempts",
        "classroom_assignment_id IS NULL OR test_session_id IS NULL",
    )
    op.create_index(
        op.f("ix_attempts_classroom_assignment_id"),
        "attempts",
        ["classroom_assignment_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_attempts_classroom_assignment_id_classroom_assignments"),
        "attempts",
        "classroom_assignments",
        ["classroom_assignment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("test_sessions", sa.Column("classroom_assignment_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_test_sessions_classroom_assignment_id"),
        "test_sessions",
        ["classroom_assignment_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_test_sessions_classroom_assignment_id_classroom_assignments"),
        "test_sessions",
        "classroom_assignments",
        ["classroom_assignment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("tests", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "tests",
        sa.Column(
            "origin",
            sa.Enum("ADMIN", "TEACHER", name="test_origin"),
            server_default="ADMIN",
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_tests_owner_user_id"), "tests", ["owner_user_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_tests_owner_user_id_users"),
        "tests",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # Refuse to erase classroom/moderation history or strand teacher accounts.
    bind = op.get_bind()
    for table in ("classrooms", "notifications", "test_version_moderation"):
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Teacher governance downgrade requires an empty feature domain")
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM users WHERE role = 'TEACHER')")).scalar():
        raise RuntimeError("Resolve teacher roles before downgrading")
    if bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM tests WHERE origin = 'TEACHER')")
    ).scalar():
        raise RuntimeError("Preserve teacher-origin content before downgrading")
    op.drop_constraint(op.f("fk_tests_owner_user_id_users"), "tests", type_="foreignkey")
    op.drop_index(op.f("ix_tests_owner_user_id"), table_name="tests")
    op.drop_column("tests", "origin")
    op.drop_column("tests", "owner_user_id")
    op.drop_constraint(
        op.f("fk_test_sessions_classroom_assignment_id_classroom_assignments"),
        "test_sessions",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_test_sessions_classroom_assignment_id"), table_name="test_sessions")
    op.drop_column("test_sessions", "classroom_assignment_id")
    op.drop_constraint(
        op.f("fk_attempts_classroom_assignment_id_classroom_assignments"),
        "attempts",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_attempts_classroom_assignment_id"), table_name="attempts")
    op.drop_constraint(
        op.f("ck_attempts_classroom_provenance_standalone"), "attempts", type_="check"
    )
    op.drop_column("attempts", "classroom_assignment_id")
    op.drop_index(
        "uq_moderation_pending_scope",
        table_name="test_version_moderation",
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.drop_index(
        op.f("ix_test_version_moderation_test_version_id"), table_name="test_version_moderation"
    )
    op.drop_index(op.f("ix_test_version_moderation_status"), table_name="test_version_moderation")
    op.drop_table("test_version_moderation")
    op.drop_index(
        op.f("ix_classroom_assignments_test_version_id"), table_name="classroom_assignments"
    )
    op.drop_index(op.f("ix_classroom_assignments_classroom_id"), table_name="classroom_assignments")
    op.drop_table("classroom_assignments")
    op.drop_index(
        "uq_classroom_active_membership",
        table_name="classroom_memberships",
        postgresql_where=sa.text("left_at IS NULL"),
    )
    op.drop_index(op.f("ix_classroom_memberships_user_id"), table_name="classroom_memberships")
    op.drop_index(op.f("ix_classroom_memberships_classroom_id"), table_name="classroom_memberships")
    op.drop_table("classroom_memberships")
    op.drop_index(
        "uq_classroom_pending_invitation",
        table_name="classroom_invitations",
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.drop_index(
        op.f("ix_classroom_invitations_invited_user_id"), table_name="classroom_invitations"
    )
    op.drop_index(
        op.f("ix_classroom_invitations_invited_email_normalized"),
        table_name="classroom_invitations",
    )
    op.drop_index(op.f("ix_classroom_invitations_classroom_id"), table_name="classroom_invitations")
    op.drop_table("classroom_invitations")
    op.drop_index("ix_notifications_recipient_unread", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_classrooms_teacher_id"), table_name="classrooms")
    op.drop_table("classrooms")
    for name in (
        "test_origin",
        "classroom_status",
        "notification_type",
        "notification_entity_type",
        "invitation_status",
        "assignment_status",
        "moderation_scope",
        "moderation_status",
    ):
        sa.Enum(name=name).drop(bind, checkfirst=True)
    # Keep the additive user_role label: PostgreSQL cannot safely remove it in place.
