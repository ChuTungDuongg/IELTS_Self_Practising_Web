"""Initial Phase 1 schema.

Revision ID: 20260918_0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260918_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

version_status = sa.Enum("DRAFT", "PUBLISHED", "ARCHIVED", name="version_status")
module_type = sa.Enum("READING", "LISTENING", "WRITING", name="module_type")
attempt_module_type = sa.Enum("READING", "LISTENING", "WRITING", name="attempt_module_type")
timer_mode = sa.Enum("COUNTDOWN", "COUNT_UP", name="timer_mode")
attempt_status = sa.Enum(
    "IN_PROGRESS", "SUBMITTED", "AUTO_SUBMITTED", "INTERRUPTED", "ABANDONED", name="attempt_status"
)
finished_reason = sa.Enum(
    "USER_SUBMIT", "TIME_EXPIRED", "AFK_TIMEOUT", "USER_EXIT", name="finished_reason"
)
asset_type = sa.Enum("LISTENING_AUDIO", "WRITING_TASK_IMAGE", "QUESTION_IMAGE", name="asset_type")
event_type = sa.Enum(
    "ANSWER_CHANGED",
    "QUESTION_VISITED",
    "PASSAGE_CHANGED",
    "HIGHLIGHT_CREATED",
    "HIGHLIGHT_REMOVED",
    "FLAG_CHANGED",
    "WRITING_UPDATED",
    "AFK_DETECTED",
    "SUBMITTED",
    name="event_type",
)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "tests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source_label", sa.String(160)),
        sa.Column("test_number", sa.Integer()),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_tests"),
    )
    op.create_table(
        "test_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", version_status, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["test_id"], ["tests.id"], ondelete="CASCADE", name="fk_test_versions_test_id_tests"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_test_versions"),
        sa.UniqueConstraint(
            "test_id", "version_number", name="uq_test_versions_test_id_version_number"
        ),
    )
    op.create_table(
        "test_modules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("module_type", module_type, nullable=False),
        sa.Column("title", sa.String(240)),
        sa.Column("recommended_duration_seconds", sa.Integer()),
        sa.Column("order_index", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["test_version_id"],
            ["test_versions.id"],
            ondelete="CASCADE",
            name="fk_test_modules_test_version_id_test_versions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_test_modules"),
        sa.UniqueConstraint(
            "test_version_id", "module_type", name="uq_test_modules_test_version_id_module_type"
        ),
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type", asset_type, nullable=False),
        sa.Column("relative_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["test_version_id"],
            ["test_versions.id"],
            ondelete="CASCADE",
            name="fk_assets_test_version_id_test_versions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.UniqueConstraint("relative_path", name="uq_assets_relative_path_"),
    )
    op.create_index("ix_assets_test_version_id", "assets", ["test_version_id"])
    op.create_table(
        "reading_passages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("plain_text", sa.Text(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["test_modules.id"],
            ondelete="CASCADE",
            name="fk_reading_passages_module_id_test_modules",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reading_passages"),
        sa.UniqueConstraint(
            "module_id", "order_index", name="uq_reading_passages_module_id_order_index"
        ),
    )
    op.create_table(
        "listening_parts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("audio_asset_id", sa.Uuid()),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["audio_asset_id"],
            ["assets.id"],
            ondelete="SET NULL",
            name="fk_listening_parts_audio_asset_id_assets",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["test_modules.id"],
            ondelete="CASCADE",
            name="fk_listening_parts_module_id_test_modules",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_listening_parts"),
        sa.UniqueConstraint(
            "module_id", "order_index", name="uq_listening_parts_module_id_order_index"
        ),
    )
    op.create_table(
        "writing_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("task_number", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("image_asset_id", sa.Uuid()),
        sa.Column("minimum_recommended_words", sa.Integer()),
        sa.Column("recommended_duration_seconds", sa.Integer()),
        sa.Column("order_index", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["image_asset_id"],
            ["assets.id"],
            ondelete="SET NULL",
            name="fk_writing_tasks_image_asset_id_assets",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["test_modules.id"],
            ondelete="CASCADE",
            name="fk_writing_tasks_module_id_test_modules",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_writing_tasks"),
        sa.UniqueConstraint(
            "module_id", "order_index", name="uq_writing_tasks_module_id_order_index"
        ),
    )
    op.create_table(
        "question_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("passage_id", sa.Uuid()),
        sa.Column("section_reference", sa.String(120)),
        sa.Column("question_type", sa.String(80), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["test_modules.id"],
            ondelete="CASCADE",
            name="fk_question_groups_module_id_test_modules",
        ),
        sa.ForeignKeyConstraint(
            ["passage_id"],
            ["reading_passages.id"],
            ondelete="SET NULL",
            name="fk_question_groups_passage_id_reading_passages",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_question_groups"),
        sa.UniqueConstraint(
            "module_id", "order_index", name="uq_question_groups_module_id_order_index"
        ),
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_group_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("answer_key", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text()),
        sa.Column("order_index", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["question_group_id"],
            ["question_groups.id"],
            ondelete="CASCADE",
            name="fk_questions_question_group_id_question_groups",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_questions"),
        sa.UniqueConstraint(
            "question_group_id", "number", name="uq_questions_question_group_id_number"
        ),
        sa.UniqueConstraint(
            "question_group_id", "order_index", name="uq_questions_question_group_id_order_index"
        ),
    )
    op.create_table(
        "attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("module_type", attempt_module_type, nullable=False),
        sa.Column("timer_mode", timer_mode, nullable=False),
        sa.Column("timer_limit_seconds", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("elapsed_seconds", sa.Integer()),
        sa.Column("status", attempt_status, nullable=False),
        sa.Column("finished_reason", finished_reason),
        sa.Column("raw_score", sa.Integer()),
        sa.Column("max_score", sa.Integer()),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["test_version_id"],
            ["test_versions.id"],
            ondelete="RESTRICT",
            name="fk_attempts_test_version_id_test_versions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attempts"),
    )
    op.create_index("ix_attempts_test_version_id", "attempts", ["test_version_id"])
    op.create_table(
        "attempt_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_correct", sa.Boolean()),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            ondelete="CASCADE",
            name="fk_attempt_answers_attempt_id_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            ondelete="RESTRICT",
            name="fk_attempt_answers_question_id_questions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attempt_answers"),
        sa.UniqueConstraint(
            "attempt_id", "question_id", name="uq_attempt_answers_attempt_id_question_id"
        ),
    )
    op.create_table(
        "attempt_writing_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("writing_task_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            ondelete="CASCADE",
            name="fk_attempt_writing_responses_attempt_id_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["writing_task_id"],
            ["writing_tasks.id"],
            ondelete="RESTRICT",
            name="fk_attempt_writing_responses_writing_task_id_writing_tasks",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attempt_writing_responses"),
        sa.UniqueConstraint(
            "attempt_id",
            "writing_task_id",
            name="uq_attempt_writing_responses_attempt_id_writing_task_id",
        ),
    )
    op.create_table(
        "highlights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("passage_id", sa.Uuid(), nullable=False),
        sa.Column("start_block_id", sa.Uuid(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_block_id", sa.Uuid(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("selected_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            ondelete="CASCADE",
            name="fk_highlights_attempt_id_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["passage_id"],
            ["reading_passages.id"],
            ondelete="RESTRICT",
            name="fk_highlights_passage_id_reading_passages",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_highlights"),
    )
    op.create_table(
        "question_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("flagged", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            ondelete="CASCADE",
            name="fk_question_flags_attempt_id_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            ondelete="RESTRICT",
            name="fk_question_flags_question_id_questions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_question_flags"),
        sa.UniqueConstraint(
            "attempt_id", "question_id", name="uq_question_flags_attempt_id_question_id"
        ),
    )
    op.create_table(
        "attempt_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("question_id", sa.Uuid()),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            ondelete="CASCADE",
            name="fk_attempt_events_attempt_id_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            ondelete="SET NULL",
            name="fk_attempt_events_question_id_questions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attempt_events"),
    )


def downgrade() -> None:
    for table in [
        "attempt_events",
        "question_flags",
        "highlights",
        "attempt_writing_responses",
        "attempt_answers",
        "attempts",
        "questions",
        "question_groups",
        "writing_tasks",
        "listening_parts",
        "reading_passages",
        "assets",
        "test_modules",
        "test_versions",
        "tests",
    ]:
        op.drop_table(table)
    for enum in [
        event_type,
        asset_type,
        finished_reason,
        attempt_status,
        timer_mode,
        attempt_module_type,
        module_type,
        version_status,
    ]:
        enum.drop(op.get_bind(), checkfirst=True)
