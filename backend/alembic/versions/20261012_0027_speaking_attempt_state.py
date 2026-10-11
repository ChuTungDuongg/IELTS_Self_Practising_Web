"""speaking_attempt_state

Revision ID: 20261012_0027
Revises: 20261012_0026
Create Date: 2026-10-12 03:22:48.432852
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261012_0027"
down_revision: str | None = "20261012_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE attempt_module_type ADD VALUE IF NOT EXISTS 'SPEAKING'")
    op.create_table(
        "speaking_responses",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_id", sa.Uuid(), nullable=False),
        sa.Column("active_take_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("completion_reason", sa.String(length=24), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("committed_audio_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            name=op.f("fk_speaking_responses_attempt_id_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"],
            ["speaking_prompts.id"],
            name=op.f("fk_speaking_responses_prompt_id_speaking_prompts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speaking_responses")),
        sa.UniqueConstraint(
            "attempt_id", "prompt_id", name=op.f("uq_speaking_responses_attempt_id_prompt_id")
        ),
    )
    op.create_table(
        "speaking_prompt_progress",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_id", sa.Uuid(), nullable=True),
        sa.Column("response_id", sa.Uuid(), nullable=True),
        sa.Column("take_number", sa.Integer(), nullable=True),
        sa.Column("phase", sa.String(length=24), nullable=False),
        sa.Column("phase_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_confirmed_remaining_ms", sa.Integer(), nullable=False),
        sa.Column("interruption_generation", sa.Integer(), nullable=False),
        sa.Column("interruption_count", sa.Integer(), nullable=False),
        sa.Column("recovery_state", sa.String(length=24), nullable=True),
        sa.Column("recovery_grace_used", sa.Boolean(), nullable=False),
        sa.Column("last_resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scratch_notes", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            name=op.f("fk_speaking_prompt_progress_attempt_id_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"],
            ["speaking_prompts.id"],
            name=op.f("fk_speaking_prompt_progress_prompt_id_speaking_prompts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["response_id"],
            ["speaking_responses.id"],
            name=op.f("fk_speaking_prompt_progress_response_id_speaking_responses"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("attempt_id", name=op.f("pk_speaking_prompt_progress")),
    )
    op.create_table(
        "speaking_response_takes",
        sa.Column("response_id", sa.Uuid(), nullable=False),
        sa.Column("take_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["response_id"],
            ["speaking_responses.id"],
            name=op.f("fk_speaking_response_takes_response_id_speaking_responses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speaking_response_takes")),
        sa.UniqueConstraint(
            "response_id",
            "take_number",
            name=op.f("uq_speaking_response_takes_response_id_take_number"),
        ),
    )
    op.add_column("attempts", sa.Column("focused_speaking_prompt_id", sa.Uuid(), nullable=True))
    op.add_column("attempts", sa.Column("speaking_mode", sa.String(length=16), nullable=True))
    op.create_foreign_key(
        op.f("fk_attempts_focused_speaking_prompt_id_speaking_prompts"),
        "attempts",
        "speaking_prompts",
        ["focused_speaking_prompt_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(op.f("ck_attempts_scope_target"), "attempts", type_="check")
    op.create_check_constraint("scope_target", "attempts", SCOPE_WITH_SPEAKING)


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM attempts WHERE module_type = 'SPEAKING') THEN
            RAISE EXCEPTION 'Cannot remove Speaking runtime while Speaking attempts exist';
        END IF;
    END $$""")
    op.drop_constraint(op.f("ck_attempts_scope_target"), "attempts", type_="check")
    op.create_check_constraint("scope_target", "attempts", SCOPE_BEFORE_SPEAKING)
    op.drop_constraint(
        op.f("fk_attempts_focused_speaking_prompt_id_speaking_prompts"),
        "attempts",
        type_="foreignkey",
    )
    op.drop_column("attempts", "speaking_mode")
    op.drop_column("attempts", "focused_speaking_prompt_id")
    op.drop_table("speaking_response_takes")
    op.drop_table("speaking_prompt_progress")
    op.drop_table("speaking_responses")
    # Keep the enum label; removing it would require rewriting historical types.


SCOPE_BEFORE_SPEAKING = (
    "(scope = 'FULL_MODULE' AND focused_reading_passage_id IS NULL "
    "AND focused_listening_part_id IS NULL AND focused_writing_task_id IS NULL) OR "
    "(scope = 'FOCUSED_UNIT' AND ((module_type = 'READING' "
    "AND focused_reading_passage_id IS NOT NULL AND focused_listening_part_id IS NULL "
    "AND focused_writing_task_id IS NULL) OR (module_type = 'LISTENING' "
    "AND focused_listening_part_id IS NOT NULL AND focused_reading_passage_id IS NULL "
    "AND focused_writing_task_id IS NULL) OR (module_type = 'WRITING' "
    "AND focused_writing_task_id IS NOT NULL AND focused_reading_passage_id IS NULL "
    "AND focused_listening_part_id IS NULL)))"
)
SCOPE_WITH_SPEAKING = (
    "(" + SCOPE_BEFORE_SPEAKING + ") AND focused_speaking_prompt_id IS NULL OR "
    "(scope = 'FOCUSED_UNIT' AND module_type = 'SPEAKING' "
    "AND focused_speaking_prompt_id IS NOT NULL AND focused_reading_passage_id IS NULL "
    "AND focused_listening_part_id IS NULL AND focused_writing_task_id IS NULL)"
)
