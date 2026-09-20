"""add per-task Writing criterion scores

Revision ID: 20260920_0009
Revises: 20260920_0008
Create Date: 2026-09-20
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260920_0009"
down_revision: str | None = "20260920_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attempt_writing_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("writing_task_id", sa.Uuid(), nullable=False),
        sa.Column("ta", sa.Numeric(precision=2, scale=1), nullable=False),
        sa.Column("cc", sa.Numeric(precision=2, scale=1), nullable=False),
        sa.Column("lr", sa.Numeric(precision=2, scale=1), nullable=False),
        sa.Column("gra", sa.Numeric(precision=2, scale=1), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "ta >= 0 AND ta <= 9 AND mod(ta * 2, 1) = 0",
            name="ck_attempt_writing_scores_ta_half_band",
        ),
        sa.CheckConstraint(
            "cc >= 0 AND cc <= 9 AND mod(cc * 2, 1) = 0",
            name="ck_attempt_writing_scores_cc_half_band",
        ),
        sa.CheckConstraint(
            "lr >= 0 AND lr <= 9 AND mod(lr * 2, 1) = 0",
            name="ck_attempt_writing_scores_lr_half_band",
        ),
        sa.CheckConstraint(
            "gra >= 0 AND gra <= 9 AND mod(gra * 2, 1) = 0",
            name="ck_attempt_writing_scores_gra_half_band",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            ondelete="CASCADE",
            name="fk_attempt_writing_scores_attempt_id_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["writing_task_id"],
            ["writing_tasks.id"],
            ondelete="RESTRICT",
            name="fk_attempt_writing_scores_writing_task_id_writing_tasks",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attempt_writing_scores"),
        sa.UniqueConstraint(
            "attempt_id",
            "writing_task_id",
            name="uq_attempt_writing_scores_attempt_id_writing_task_id",
        ),
    )

    connection = op.get_bind()
    legacy_rows = connection.execute(
        sa.text(
            """
            SELECT a.id AS attempt_id, wt.id AS writing_task_id, a.band_score
            FROM attempts AS a
            JOIN test_modules AS tm
              ON tm.test_version_id = a.test_version_id
             AND tm.module_type = 'WRITING'
            JOIN writing_tasks AS wt
              ON wt.module_id = tm.id
             AND wt.task_number IN (1, 2)
            WHERE a.module_type = 'WRITING'
              AND a.band_score IS NOT NULL
            """
        )
    ).mappings()
    for row in legacy_rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO attempt_writing_scores
                    (id, attempt_id, writing_task_id, ta, cc, lr, gra)
                VALUES
                    (:id, :attempt_id, :writing_task_id, :band, :band, :band, :band)
                """
            ),
            {
                "id": uuid.uuid4(),
                "attempt_id": row["attempt_id"],
                "writing_task_id": row["writing_task_id"],
                "band": row["band_score"],
            },
        )


def downgrade() -> None:
    op.drop_table("attempt_writing_scores")
