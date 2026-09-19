"""enforce one draft and one current published version per test

Revision ID: 20260919_0005
Revises: 20260919_0004
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0005"
down_revision: str | None = "20260919_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicate_drafts = connection.execute(
        sa.text(
            "SELECT test_id FROM test_versions WHERE status = 'DRAFT' "
            "GROUP BY test_id HAVING COUNT(*) > 1"
        )
    ).scalars().all()
    if duplicate_drafts:
        raise RuntimeError(
            "Cannot enforce the single-Draft invariant. Resolve tests with multiple Drafts: "
            + ", ".join(str(item) for item in duplicate_drafts)
        )

    connection.execute(
        sa.text(
            "WITH ranked AS ("
            " SELECT id, ROW_NUMBER() OVER (PARTITION BY test_id "
            " ORDER BY version_number DESC, created_at DESC, id DESC) AS position"
            " FROM test_versions WHERE status = 'PUBLISHED'"
            ") UPDATE test_versions SET status = 'ARCHIVED' "
            "FROM ranked WHERE test_versions.id = ranked.id AND ranked.position > 1"
        )
    )
    op.create_index(
        "uq_test_versions_one_draft_per_test",
        "test_versions",
        ["test_id"],
        unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"),
    )
    op.create_index(
        "uq_test_versions_one_published_per_test",
        "test_versions",
        ["test_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_test_versions_one_published_per_test", table_name="test_versions")
    op.drop_index("uq_test_versions_one_draft_per_test", table_name="test_versions")
