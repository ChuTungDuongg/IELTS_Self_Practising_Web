"""add optional Writing criterion feedback

Revision ID: 20260921_0011
Revises: 20260921_0010
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0011"
down_revision: str | None = "20260921_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("ta_feedback", "cc_feedback", "lr_feedback", "gra_feedback"):
        op.add_column("attempt_writing_scores", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    for name in reversed(("ta_feedback", "cc_feedback", "lr_feedback", "gra_feedback")):
        op.drop_column("attempt_writing_scores", name)
