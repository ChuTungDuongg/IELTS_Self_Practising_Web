"""Add one optional, test-owned cover without changing historical versions."""

import sqlalchemy as sa

from alembic import op

revision = "20261028_0043"
down_revision = "20261028_0042"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "test_covers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "test_id",
            sa.Uuid(),
            sa.ForeignKey("tests.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("relative_path", sa.String(500), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    op.drop_table("test_covers")
