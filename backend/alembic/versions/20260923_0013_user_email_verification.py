"""track verified user email identities

Revision ID: 20260923_0013
Revises: 20260923_0012
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260923_0013"
down_revision: str | None = "20260923_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE users SET email_verified = true "
        "WHERE role = 'ADMIN' OR id IN (SELECT user_id FROM oauth_accounts)"
    )
    op.alter_column("users", "email_verified", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "email_verified")
