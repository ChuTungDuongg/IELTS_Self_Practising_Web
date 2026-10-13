"""Part-focused Speaking practice, preserving historical prompt scope.

Revision ID: 20261013_0034
Revises: 20261013_0033
"""

import sqlalchemy as sa

from alembic import op

revision = "20261013_0034"
down_revision = "20261013_0033"
branch_labels = None
depends_on = None

OLD_SCOPE = (
    "(scope = 'FULL_MODULE' AND focused_reading_passage_id IS NULL "
    "AND focused_listening_part_id IS NULL AND focused_writing_task_id IS NULL "
    "AND focused_speaking_prompt_id IS NULL) OR "
    "(scope = 'FOCUSED_UNIT' AND ((module_type = 'READING' "
    "AND focused_reading_passage_id IS NOT NULL AND focused_listening_part_id IS NULL "
    "AND focused_writing_task_id IS NULL AND focused_speaking_prompt_id IS NULL) OR (module_type = 'LISTENING' "
    "AND focused_listening_part_id IS NOT NULL AND focused_reading_passage_id IS NULL "
    "AND focused_writing_task_id IS NULL AND focused_speaking_prompt_id IS NULL) OR (module_type = 'WRITING' "
    "AND focused_writing_task_id IS NOT NULL AND focused_reading_passage_id IS NULL "
    "AND focused_listening_part_id IS NULL AND focused_speaking_prompt_id IS NULL) OR "
    "(module_type = 'SPEAKING' AND focused_speaking_prompt_id IS NOT NULL "
    "AND focused_reading_passage_id IS NULL AND focused_listening_part_id IS NULL "
    "AND focused_writing_task_id IS NULL)))"
)
NEW_SCOPE = OLD_SCOPE.replace(
    "focused_speaking_prompt_id IS NULL",
    "focused_speaking_prompt_id IS NULL AND focused_speaking_part_id IS NULL",
).replace(
    "focused_speaking_prompt_id IS NOT NULL",
    "((focused_speaking_prompt_id IS NOT NULL AND focused_speaking_part_id IS NULL) OR "
    "(focused_speaking_prompt_id IS NULL AND focused_speaking_part_id IS NOT NULL))",
)
FLOW = (
    "(focused_speaking_part_id IS NULL OR speaking_practice_flow IS NOT NULL) AND "
    "(speaking_practice_flow IS NULL OR (speaking_practice_flow IN ('GUIDED', 'FREE') "
    "AND focused_speaking_part_id IS NOT NULL AND scope = 'FOCUSED_UNIT' "
    "AND module_type = 'SPEAKING' AND speaking_mode IS NOT NULL AND speaking_mode = 'PRACTICE' "
    "AND timer_mode = 'COUNT_UP' AND classroom_assignment_id IS NULL))"
)


def upgrade():
    op.add_column("attempts", sa.Column("focused_speaking_part_id", sa.Uuid(), nullable=True))
    op.add_column("attempts", sa.Column("speaking_practice_flow", sa.String(16), nullable=True))
    op.create_foreign_key(
        op.f("fk_attempts_focused_speaking_part_id_speaking_parts"),
        "attempts",
        "speaking_parts",
        ["focused_speaking_part_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(op.f("ck_attempts_scope_target"), "attempts", type_="check")
    op.create_check_constraint(op.f("ck_attempts_scope_target"), "attempts", NEW_SCOPE)
    op.create_check_constraint(op.f("ck_attempts_speaking_practice_flow"), "attempts", FLOW)


def downgrade():
    op.execute("""DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM attempts WHERE focused_speaking_part_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Cannot remove Speaking Part practice while its history exists';
    END IF; END $$""")
    op.drop_constraint(op.f("ck_attempts_speaking_practice_flow"), "attempts", type_="check")
    op.drop_constraint(op.f("ck_attempts_scope_target"), "attempts", type_="check")
    op.create_check_constraint(op.f("ck_attempts_scope_target"), "attempts", OLD_SCOPE)
    op.drop_constraint(
        op.f("fk_attempts_focused_speaking_part_id_speaking_parts"), "attempts", type_="foreignkey"
    )
    op.drop_column("attempts", "speaking_practice_flow")
    op.drop_column("attempts", "focused_speaking_part_id")
