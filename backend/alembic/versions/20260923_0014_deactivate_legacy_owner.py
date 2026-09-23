"""keep the historical ownership backfill account non-privileged

Revision ID: 20260923_0014
Revises: 20260923_0013
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260923_0014"
down_revision: str | None = "20260923_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE users SET role = 'USER', is_active = false, email_verified = false "
            "WHERE email = 'legacy-admin@local.invalid' AND password_hash IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM oauth_accounts WHERE user_id = users.id)"
        )
    )


def downgrade() -> None:
    # Deliberately do not promote a credentialless data-owner account on downgrade.
    pass
