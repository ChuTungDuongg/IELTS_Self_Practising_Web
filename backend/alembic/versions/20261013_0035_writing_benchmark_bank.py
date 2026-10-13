"""Single admin Writing benchmark ground-truth bank.

Revision ID: 20261013_0035
Revises: 20261013_0034
"""

import sqlalchemy as sa

from alembic import op

revision = "20261013_0035"
down_revision = "20261013_0034"
branch_labels = None
depends_on = None

# Frozen contract: historical migrations do not import current registries/models.
SCORES = ("human_ta_tr", "human_cc", "human_lr", "human_gra")
TYPES = "'BAR_CHART','LINE_GRAPH','MAP_PLAN','MIXED_CHARTS','OBJECT_SYSTEM_DIAGRAM','OTHER_VISUAL','PIE_CHART','PROCESS','TABLE'"


def upgrade():
    op.create_table(
        "writing_benchmark_samples",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_number", sa.Integer(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "COMPLETE", name="writing_benchmark_status"),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column(
            "split",
            sa.Enum("DEV", "HOLDOUT", name="writing_benchmark_split"),
            server_default="DEV",
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("essay", sa.Text(), server_default="", nullable=False),
        sa.Column("task1_task_type", sa.String(40)),
        sa.Column("task1_image_key", sa.String(512)),
        *(sa.Column(field, sa.Numeric()) for field in SCORES),
        sa.Column("source_note", sa.Text()),
        sa.Column("redistributable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "task_number",
            "sequence_number",
            name="uq_writing_benchmark_samples_task_number_sequence_number",
        ),
        sa.CheckConstraint("task_number IN (1,2)", name="task_number"),
        sa.CheckConstraint("sequence_number BETWEEN 1 AND 100", name="sequence_number"),
        sa.CheckConstraint("revision >= 0", name="revision"),
        sa.CheckConstraint(
            f"task1_task_type IS NULL OR task1_task_type IN ({TYPES})", name="task1_type"
        ),
        sa.CheckConstraint(
            "task_number = 1 OR (task1_task_type IS NULL AND task1_image_key IS NULL)",
            name="task2_text_only",
        ),
        sa.CheckConstraint(
            "length(prompt) <= 20000 AND length(essay) <= 100000", name="content_length"
        ),
        sa.CheckConstraint(
            "source_note IS NULL OR length(source_note) <= 2000", name="source_length"
        ),
        *(
            sa.CheckConstraint(
                f"{field} IS NULL OR ({field} BETWEEN 0 AND 9 AND {field} * 2 = floor({field} * 2))",
                name=f"{field}_half_band",
            )
            for field in SCORES
        ),
        sa.CheckConstraint(
            "status != 'COMPLETE' OR (prompt ~ '[^[:space:]]' AND essay ~ '[^[:space:]]' AND "
            + " AND ".join(f"{field} IS NOT NULL" for field in SCORES)
            + " AND (task_number = 2 OR (task1_task_type IS NOT NULL AND task1_image_key IS NOT NULL AND length(task1_image_key) > 0)))",
            name="complete",
        ),
    )


def downgrade():
    op.drop_table("writing_benchmark_samples")
    sa.Enum(name="writing_benchmark_split").drop(op.get_bind())
    sa.Enum(name="writing_benchmark_status").drop(op.get_bind())
