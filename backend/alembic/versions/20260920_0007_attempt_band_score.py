"""add nullable IELTS band score to attempts

Revision ID: 20260920_0007
Revises: 20260919_0006
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260920_0007"
down_revision: str | None = "20260919_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "attempts",
        sa.Column("band_score", sa.Numeric(precision=2, scale=1), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attempts", "band_score")
