"""add full mock sessions and navigation event types

Revision ID: 20260921_0010
Revises: 20260920_0009
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260921_0010"
down_revision: str | None = "20260920_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    session_status_type = postgresql.ENUM(
        "IN_PROGRESS", "COMPLETED", "ABANDONED", name="test_session_status"
    )
    session_status_type.create(op.get_bind(), checkfirst=True)
    session_status = postgresql.ENUM(
        "IN_PROGRESS",
        "COMPLETED",
        "ABANDONED",
        name="test_session_status",
        create_type=False,
    )
    op.create_table(
        "test_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", session_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["test_version_id"], ["test_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_sessions_test_version_id", "test_sessions", ["test_version_id"])
    op.add_column("attempts", sa.Column("test_session_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_attempts_test_session_id_test_sessions",
        "attempts",
        "test_sessions",
        ["test_session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_attempts_test_session_id", "attempts", ["test_session_id"])
    op.create_index(
        "uq_attempts_test_session_module",
        "attempts",
        ["test_session_id", "module_type"],
        unique=True,
        postgresql_where=sa.text("test_session_id IS NOT NULL"),
    )
    op.create_index("ix_attempt_events_attempt_type", "attempt_events", ["attempt_id", "event_type"])
    op.execute("ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'LISTENING_PART_CHANGED'")
    op.execute("ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'WRITING_TASK_CHANGED'")


def downgrade() -> None:
    op.drop_index("ix_attempt_events_attempt_type", table_name="attempt_events")
    op.drop_index("uq_attempts_test_session_module", table_name="attempts")
    op.drop_index("ix_attempts_test_session_id", table_name="attempts")
    op.drop_constraint("fk_attempts_test_session_id_test_sessions", "attempts", type_="foreignkey")
    op.drop_column("attempts", "test_session_id")
    op.drop_index("ix_test_sessions_test_version_id", table_name="test_sessions")
    op.drop_table("test_sessions")
    postgresql.ENUM(name="test_session_status").drop(op.get_bind(), checkfirst=True)
