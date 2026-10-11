"""Add authored Speaking content only.

Revision ID: 20261012_0026
Revises: 20261011_0025
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0026"
down_revision = "20261011_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE module_type ADD VALUE IF NOT EXISTS 'SPEAKING'")
    op.create_table(
        "speaking_parts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("part_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["module_id"], ["test_modules.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("module_id", "part_number"),
        sa.CheckConstraint("part_number BETWEEN 1 AND 3", name="part_number"),
    )
    op.create_table(
        "speaking_prompts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("speaking_part_id", sa.Uuid(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column(
            "prompt_type",
            sa.Enum("SHORT_ANSWER", "LONG_TURN", "FOLLOW_UP", name="speaking_prompt_type"),
            nullable=False,
        ),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("preparation_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column(
            "config_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["speaking_part_id"], ["speaking_parts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "speaking_part_id", "order_index", deferrable=True, initially="DEFERRED"
        ),
    )


def downgrade() -> None:
    op.drop_table("speaking_prompts")
    op.drop_table("speaking_parts")
    sa.Enum(name="speaking_prompt_type").drop(op.get_bind())
    # Keep the added module enum label: removing PostgreSQL enum labels is unsafe
    # for retained historical data. No runtime/attempt enum is changed in P1.
