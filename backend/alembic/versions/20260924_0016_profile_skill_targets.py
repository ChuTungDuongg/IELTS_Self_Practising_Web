"""add optional IELTS skill target bands

Revision ID: 20260924_0016
Revises: 20260924_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0016"
down_revision: str | None = "20260924_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SKILL_TARGETS = (
    "target_listening_band",
    "target_reading_band",
    "target_writing_band",
    "target_speaking_band",
)


def upgrade() -> None:
    for name in SKILL_TARGETS:
        op.add_column("users", sa.Column(name, sa.Numeric(3, 1), nullable=True))
        op.create_check_constraint(
            f"ck_users_{name}_half_step",
            "users",
            f"{name} IS NULL OR ({name} >= 0 AND {name} <= 9 AND {name} * 2 = floor({name} * 2))",
        )


def downgrade() -> None:
    for name in reversed(SKILL_TARGETS):
        op.drop_constraint(f"ck_users_{name}_half_step", "users", type_="check")
        op.drop_column("users", name)
