"""Add per-response revision tokens for learner saves.

Revision ID: 20260924_0018
Revises: 20260924_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0018"
down_revision: str | None = "20260924_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("attempt_answers", "attempt_writing_responses"):
        op.add_column(
            table, sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
        )
        op.alter_column(table, "revision", server_default=None)


def downgrade() -> None:
    for table in ("attempt_writing_responses", "attempt_answers"):
        op.drop_column(table, "revision")
