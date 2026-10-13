"""Independent human final Speaking scores.

Revision ID: 20261013_0033
Revises: 20261012_0032
"""

import sqlalchemy as sa

from alembic import op

revision = "20261013_0033"
down_revision = "20261012_0032"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "attempt_speaking_scores",
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("attempts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        *(sa.Column(key, sa.Numeric(3, 1), nullable=False) for key in ("fc", "lr", "gra", "pr")),
        *(
            sa.Column(f"{key}_feedback", sa.Text(), nullable=True)
            for key in ("fc", "lr", "gra", "pr")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        *(
            sa.CheckConstraint(
                f"{key} BETWEEN 0 AND 9 AND {key} * 2 = floor({key} * 2)", name=f"{key}_half_band"
            )
            for key in ("fc", "lr", "gra", "pr")
        ),
    )


def downgrade():
    op.drop_table("attempt_speaking_scores")
