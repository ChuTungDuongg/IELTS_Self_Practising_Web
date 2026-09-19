"""add stable listening group ownership and visual assets

Revision ID: 20260919_0003
Revises: 6a2152f127bc
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0003"
down_revision: str | None = "6a2152f127bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("question_groups", sa.Column("listening_part_id", sa.Uuid(), nullable=True))
    op.add_column("question_groups", sa.Column("image_asset_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_question_groups_listening_part_id_listening_parts",
        "question_groups",
        "listening_parts",
        ["listening_part_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_question_groups_image_asset_id_assets",
        "question_groups",
        "assets",
        ["image_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_question_groups_listening_part_id"),
        "question_groups",
        ["listening_part_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_question_groups_listening_part_id"), table_name="question_groups")
    op.drop_constraint(
        "fk_question_groups_image_asset_id_assets", "question_groups", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_question_groups_listening_part_id_listening_parts",
        "question_groups",
        type_="foreignkey",
    )
    op.drop_column("question_groups", "image_asset_id")
    op.drop_column("question_groups", "listening_part_id")
