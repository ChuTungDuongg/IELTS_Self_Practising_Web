"""support highlights on stable passage and question text targets

Revision ID: 20260919_0006
Revises: 20260919_0005
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0006"
down_revision: str | None = "20260919_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    cross_block = connection.execute(
        sa.text("SELECT id FROM highlights WHERE start_block_id <> end_block_id LIMIT 1")
    ).first()
    if cross_block:
        raise RuntimeError("Cannot migrate a legacy highlight spanning multiple passage blocks")
    op.add_column("highlights", sa.Column("target_kind", sa.String(length=40), nullable=True))
    op.add_column("highlights", sa.Column("target_id", sa.Uuid(), nullable=True))
    op.add_column("highlights", sa.Column("segment_id", sa.Uuid(), nullable=True))
    connection.execute(
        sa.text(
            "UPDATE highlights SET target_kind = 'PASSAGE_BLOCK', target_id = passage_id, segment_id = start_block_id"
        )
    )
    op.alter_column("highlights", "target_kind", nullable=False)
    op.alter_column("highlights", "target_id", nullable=False)
    op.alter_column("highlights", "passage_id", nullable=True)
    op.alter_column("highlights", "start_block_id", nullable=True)
    op.alter_column("highlights", "end_block_id", nullable=True)
    op.create_index(
        "ix_highlights_target", "highlights", ["target_kind", "target_id", "segment_id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    unsupported = connection.execute(
        sa.text("SELECT id FROM highlights WHERE target_kind <> 'PASSAGE_BLOCK' LIMIT 1")
    ).first()
    if unsupported:
        raise RuntimeError("Delete non-passage highlights before downgrading")
    op.drop_index("ix_highlights_target", table_name="highlights")
    op.alter_column("highlights", "end_block_id", nullable=False)
    op.alter_column("highlights", "start_block_id", nullable=False)
    op.alter_column("highlights", "passage_id", nullable=False)
    op.drop_column("highlights", "segment_id")
    op.drop_column("highlights", "target_id")
    op.drop_column("highlights", "target_kind")
