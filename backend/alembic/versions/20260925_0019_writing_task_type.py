"""Add optional structured Writing task type.

Revision ID: 20260925_0019
Revises: 20260924_0018
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_0019"
down_revision: str | None = "20260924_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("writing_tasks", sa.Column("task_type", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("writing_tasks", "task_type")
