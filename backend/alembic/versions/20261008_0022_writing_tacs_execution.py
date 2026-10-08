"""Pin Task 1 execution without rewriting historical runs."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20261008_0022"
down_revision = "20261008_0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("writing_ai_grading_runs", sa.Column("scoring_architecture", sa.String(32)))
    op.add_column("writing_ai_grading_runs", sa.Column("anchor_set_id", sa.Uuid()))
    op.add_column("writing_ai_grading_runs", sa.Column("execution_config_json", JSONB()))
    op.add_column("writing_ai_grading_runs", sa.Column("scoring_diagnostics_json", JSONB()))
    op.create_foreign_key(
        "fk_writing_ai_anchor_set",
        "writing_ai_grading_runs",
        "writing_anchor_sets",
        ["anchor_set_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint("fk_writing_ai_anchor_set", "writing_ai_grading_runs", type_="foreignkey")
    for name in (
        "scoring_diagnostics_json",
        "execution_config_json",
        "anchor_set_id",
        "scoring_architecture",
    ):
        op.drop_column("writing_ai_grading_runs", name)
