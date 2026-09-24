"""Add per-resource Builder revision tokens.

Revision ID: 20260924_0017
Revises: 20260924_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0017"
down_revision: str | None = "20260924_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "test_modules",
    "reading_passages",
    "listening_parts",
    "question_groups",
    "writing_tasks",
)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        )
        op.alter_column(table, "revision", server_default=None)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_column(table, "revision")
