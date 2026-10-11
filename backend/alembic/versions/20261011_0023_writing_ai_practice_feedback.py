"""Latest advisory AI feedback for focused Writing practice.

Revision ID: 20261011_0023
Revises: 20261010_0022
"""

import sqlalchemy as sa

from alembic import op

revision = "20261011_0023"
down_revision = "20261010_0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "writing_ai_practice_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
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
            "source_ai_run_id",
            sa.Uuid(),
            sa.ForeignKey("writing_ai_grading_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *(
            column
            for trait in ("ta", "cc", "lr", "gra")
            for column in (
                sa.Column(f"{trait}_score", sa.Numeric(2, 1), nullable=False),
                sa.Column(f"{trait}_feedback", sa.String(2000), nullable=False),
            )
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "attempt_id",
            "writing_task_id",
            name="uq_writing_ai_practice_feedback_owner_task",
        ),
        *(
            sa.CheckConstraint(
                f"{trait}_score >= 0 AND {trait}_score <= 9 AND mod({trait}_score * 2, 1) = 0",
                name=f"{trait}_half_band",
            )
            for trait in ("ta", "cc", "lr", "gra")
        ),
    )


def downgrade():
    op.drop_table("writing_ai_practice_feedback")
