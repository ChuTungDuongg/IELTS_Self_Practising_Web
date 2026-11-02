"""Add fenced Writing dispatch leases and bounded scanner indexes.

Stop Writing consumers before downgrade; pending rows remain retryable by the
previous application and no feedback/event data is removed by either direction.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261102_0044"
down_revision = "20261028_0043"
branch_labels = depends_on = None


def upgrade():
    op.add_column("writing_ai_grading_runs", sa.Column("lease_token", sa.Uuid()))
    op.add_column(
        "writing_ai_grading_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True))
    )
    op.create_index(
        "ix_writing_ai_runs_dispatch", "writing_ai_grading_runs", ["status", "created_at", "id"]
    )
    op.create_index(
        "ix_writing_ai_runs_lease", "writing_ai_grading_runs", ["status", "lease_expires_at"]
    )


def downgrade():
    op.drop_index("ix_writing_ai_runs_lease", table_name="writing_ai_grading_runs")
    op.drop_index("ix_writing_ai_runs_dispatch", table_name="writing_ai_grading_runs")
    op.drop_column("writing_ai_grading_runs", "lease_expires_at")
    op.drop_column("writing_ai_grading_runs", "lease_token")
