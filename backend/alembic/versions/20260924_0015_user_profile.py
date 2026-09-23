"""add optional user profile fields

Revision ID: 20260924_0015
Revises: 20260923_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0015"
down_revision: str | None = "20260923_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("country", sa.String(120), nullable=True))
    op.add_column("users", sa.Column("city", sa.String(120), nullable=True))
    op.add_column("users", sa.Column("occupation", sa.String(160), nullable=True))
    op.add_column("users", sa.Column("institution", sa.String(200), nullable=True))
    op.add_column("users", sa.Column("target_band", sa.Numeric(3, 1), nullable=True))
    op.add_column("users", sa.Column("target_test_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("bio", sa.String(1000), nullable=True))
    op.create_check_constraint(
        "ck_users_target_band_half_step",
        "users",
        "target_band IS NULL OR (target_band >= 0 AND target_band <= 9 AND target_band * 2 = floor(target_band * 2))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_target_band_half_step", "users", type_="check")
    for name in (
        "bio",
        "target_test_date",
        "target_band",
        "institution",
        "occupation",
        "city",
        "country",
        "date_of_birth",
        "phone_number",
    ):
        op.drop_column("users", name)
