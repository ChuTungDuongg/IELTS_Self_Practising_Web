"""Add optional Listening section ranges in the shared recording.

Revision ID: 20261010_0022
Revises: 20261010_0021
"""

import sqlalchemy as sa

from alembic import op

revision = "20261010_0022"
down_revision = "20261010_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listening_parts", sa.Column("audio_start_seconds", sa.Integer(), nullable=True))
    op.add_column("listening_parts", sa.Column("audio_end_seconds", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_listening_parts_audio_range"),
        "listening_parts",
        "(audio_start_seconds IS NULL AND audio_end_seconds IS NULL) OR "
        "(audio_start_seconds IS NOT NULL AND audio_end_seconds IS NOT NULL "
        "AND audio_start_seconds >= 0 AND audio_end_seconds > audio_start_seconds)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_listening_parts_audio_range"), "listening_parts", type_="check")
    op.drop_column("listening_parts", "audio_end_seconds")
    op.drop_column("listening_parts", "audio_start_seconds")
