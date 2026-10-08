"""Separate advisory Writing AI runs and replayable events.

Revision ID: 20261008_0020
Revises: 20260925_0019
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261008_0020"
down_revision = "20260925_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "writing_ai_grading_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "writing_task_id",
            sa.Uuid(),
            sa.ForeignKey("writing_tasks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("PENDING", "RUNNING", "COMPLETED", "FAILED", name="writing_ai_run_status"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("raw_mean", sa.Numeric(5, 3)),
        sa.Column("overall_band", sa.Numeric(2, 1)),
        sa.Column("result_json", postgresql.JSONB()),
        sa.Column("usage_json", postgresql.JSONB()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.String(300)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("raw_mean >= 0 AND raw_mean <= 9", name="raw_mean_range"),
        sa.CheckConstraint(
            "overall_band >= 0 AND overall_band <= 9 AND mod(overall_band * 2, 1) = 0",
            name="overall_half_band",
        ),
    )
    op.create_index(
        "ix_writing_ai_runs_cache",
        "writing_ai_grading_runs",
        ["attempt_id", "writing_task_id", "input_fingerprint", "status"],
    )
    op.create_table(
        "writing_ai_grading_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("writing_ai_grading_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("run_id", "sequence"),
        sa.CheckConstraint("sequence > 0", name="positive_sequence"),
    )


def downgrade() -> None:
    op.drop_table("writing_ai_grading_events")
    op.drop_table("writing_ai_grading_runs")
    sa.Enum(name="writing_ai_run_status").drop(op.get_bind())
