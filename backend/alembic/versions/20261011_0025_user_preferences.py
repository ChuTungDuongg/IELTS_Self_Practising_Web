"""Add lazy account personalization preferences.

Revision ID: 20261011_0025
Revises: 20261011_0024
"""

import sqlalchemy as sa

from alembic import op

revision = "20261011_0025"
down_revision = "20261011_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "accent_color",
            sa.Enum(
                "PURPLE",
                "INDIGO",
                "BLUE",
                "CYAN",
                "EMERALD",
                "GREEN",
                "AMBER",
                "ORANGE",
                "RED",
                "PINK",
                name="preference_accent_color",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="PURPLE",
            nullable=False,
        ),
        sa.Column(
            "appearance",
            sa.Enum(
                "LIGHT",
                "DARK",
                name="preference_appearance",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="LIGHT",
            nullable=False,
        ),
        sa.Column(
            "locale",
            sa.Enum(
                "EN", "VI", name="preference_locale", native_enum=False, create_constraint=True
            ),
            server_default="EN",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
