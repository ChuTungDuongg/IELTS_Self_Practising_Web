"""add test archive lifecycle

Revision ID: 6a2152f127bc
Revises: 20260918_0001
Create Date: 2026-09-19 11:32:01.443212
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6a2152f127bc"
down_revision: str | None = "20260918_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tests", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_tests_archived_at"), "tests", ["archived_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tests_archived_at"), table_name="tests")
    op.drop_column("tests", "archived_at")
