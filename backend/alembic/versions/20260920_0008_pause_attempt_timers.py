"""add paused attempts and timer bookkeeping

Revision ID: 20260920_0008
Revises: 20260920_0007
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260920_0008"
down_revision: str | None = "20260920_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_STATUSES = (
    "IN_PROGRESS",
    "SUBMITTED",
    "AUTO_SUBMITTED",
    "INTERRUPTED",
    "ABANDONED",
)


def upgrade() -> None:
    op.execute("ALTER TYPE attempt_status ADD VALUE IF NOT EXISTS 'PAUSED' AFTER 'IN_PROGRESS'")
    op.add_column("attempts", sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "attempts",
        sa.Column(
            "total_paused_seconds",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.execute("UPDATE attempts SET status = 'IN_PROGRESS' WHERE status = 'PAUSED'")
    op.drop_column("attempts", "total_paused_seconds")
    op.drop_column("attempts", "paused_at")
    op.execute("ALTER TYPE attempt_status RENAME TO attempt_status_with_paused")
    old_status = postgresql.ENUM(*_OLD_STATUSES, name="attempt_status", create_type=False)
    old_status.create(op.get_bind(), checkfirst=False)
    op.execute(
        "ALTER TABLE attempts ALTER COLUMN status TYPE attempt_status "
        "USING status::text::attempt_status"
    )
    op.execute("DROP TYPE attempt_status_with_paused")
