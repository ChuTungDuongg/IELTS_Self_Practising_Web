"""Standalone curated sources and the base of a copy-on-write revision.

Revision ID: 20261009_0023
Revises: 20261008_0022
"""

import sqlalchemy as sa

from alembic import op

revision = "20261009_0023"
down_revision = "20261008_0022"
branch_labels = None
depends_on = None


def upgrade():
    # Adding a default backfills existing frozen rows without an UPDATE/trigger bypass.
    op.add_column(
        "writing_human_anchors",
        sa.Column("source_kind", sa.String(16), nullable=False, server_default="BUILDER_TASK"),
    )
    op.alter_column("writing_human_anchors", "writing_task_id", nullable=True)
    op.add_column("writing_human_anchors", sa.Column("task_number", sa.Integer()))
    op.add_column("writing_human_anchors", sa.Column("custom_prompt", sa.Text()))
    op.add_column("writing_human_anchors", sa.Column("custom_task_type", sa.String(64)))
    op.create_check_constraint(
        "valid_source",
        "writing_human_anchors",
        "(source_kind = 'BUILDER_TASK' AND writing_task_id IS NOT NULL AND task_number IS NULL AND custom_prompt IS NULL AND custom_task_type IS NULL) OR "
        "(source_kind = 'CUSTOM_TASK' AND writing_task_id IS NULL AND task_number IS NOT NULL AND task_number IN (1,2) AND custom_prompt IS NOT NULL AND length(btrim(custom_prompt)) > 0)",
    )
    op.add_column(
        "writing_anchor_sets",
        sa.Column(
            "based_on_set_id",
            sa.Uuid(),
            sa.ForeignKey("writing_anchor_sets.id", ondelete="RESTRICT"),
        ),
    )
    op.execute(
        "UPDATE writing_anchor_sets SET based_on_set_id=(SELECT id FROM writing_anchor_sets WHERE status='ACTIVE') WHERE status='DRAFT'"
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM writing_human_anchors WHERE source_kind='CUSTOM_TASK'")
    ):
        raise RuntimeError(
            "Cannot downgrade while custom anchors exist; preserve/export them first"
        )
    op.drop_column("writing_anchor_sets", "based_on_set_id")
    op.drop_constraint(
        op.f("ck_writing_human_anchors_valid_source"), "writing_human_anchors", type_="check"
    )
    for column in ("custom_task_type", "custom_prompt", "task_number", "source_kind"):
        op.drop_column("writing_human_anchors", column)
    op.alter_column("writing_human_anchors", "writing_task_id", nullable=False)
