"""Add focused content scope to existing attempts.

Revision ID: 20261010_0021
Revises: 20261008_0020
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261010_0021"
down_revision = "20261008_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    scope = postgresql.ENUM("FULL_MODULE", "FOCUSED_UNIT", name="attempt_scope", create_type=False)
    scope.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "attempts", sa.Column("scope", scope, nullable=True, server_default="FULL_MODULE")
    )
    for column, table in [
        ("focused_reading_passage_id", "reading_passages"),
        ("focused_listening_part_id", "listening_parts"),
        ("focused_writing_task_id", "writing_tasks"),
    ]:
        op.add_column("attempts", sa.Column(column, sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_attempts_{column}_{table}",
            "attempts",
            table,
            [column],
            ["id"],
            ondelete="RESTRICT",
        )
    # Historical attempts keep their original full-module meaning.
    op.execute("UPDATE attempts SET scope = 'FULL_MODULE' WHERE scope IS NULL")
    op.alter_column("attempts", "scope", nullable=False)
    op.create_check_constraint(
        "scope_target",
        "attempts",
        "(scope = 'FULL_MODULE' AND focused_reading_passage_id IS NULL "
        "AND focused_listening_part_id IS NULL AND focused_writing_task_id IS NULL) OR "
        "(scope = 'FOCUSED_UNIT' AND ((module_type = 'READING' "
        "AND focused_reading_passage_id IS NOT NULL AND focused_listening_part_id IS NULL "
        "AND focused_writing_task_id IS NULL) OR (module_type = 'LISTENING' "
        "AND focused_listening_part_id IS NOT NULL AND focused_reading_passage_id IS NULL "
        "AND focused_writing_task_id IS NULL) OR (module_type = 'WRITING' "
        "AND focused_writing_task_id IS NOT NULL AND focused_reading_passage_id IS NULL "
        "AND focused_listening_part_id IS NULL)))",
    )
    op.create_check_constraint(
        "session_full_module", "attempts", "test_session_id IS NULL OR scope = 'FULL_MODULE'"
    )


def downgrade() -> None:
    # Refuse to silently reinterpret partial historical attempts as complete modules.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM attempts WHERE scope = 'FOCUSED_UNIT') THEN
            RAISE EXCEPTION 'Cannot remove attempt scope while focused attempts exist';
        END IF;
    END $$""")
    op.drop_constraint("ck_attempts_session_full_module", "attempts", type_="check")
    op.drop_constraint("ck_attempts_scope_target", "attempts", type_="check")
    for column, table in [
        ("focused_writing_task_id", "writing_tasks"),
        ("focused_listening_part_id", "listening_parts"),
        ("focused_reading_passage_id", "reading_passages"),
    ]:
        op.drop_constraint(f"fk_attempts_{column}_{table}", "attempts", type_="foreignkey")
        op.drop_column("attempts", column)
    op.drop_column("attempts", "scope")
    postgresql.ENUM(name="attempt_scope").drop(op.get_bind(), checkfirst=True)
