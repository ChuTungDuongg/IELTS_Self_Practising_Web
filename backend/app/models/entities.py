from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AssetType,
    AttemptStatus,
    EventType,
    FinishedReason,
    ModuleType,
    TimerMode,
    VersionStatus,
)


class Test(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tests"

    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_label: Mapped[str | None] = mapped_column(String(160))
    test_number: Mapped[int | None] = mapped_column(Integer)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    versions: Mapped[list[TestVersion]] = relationship(
        back_populates="test", cascade="all, delete-orphan", order_by="TestVersion.version_number"
    )


class TestVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "test_versions"
    __table_args__ = (
        UniqueConstraint("test_id", "version_number"),
        Index(
            "uq_test_versions_one_draft_per_test",
            "test_id",
            unique=True,
            postgresql_where=text("status = 'DRAFT'"),
        ),
        Index(
            "uq_test_versions_one_published_per_test",
            "test_id",
            unique=True,
            postgresql_where=text("status = 'PUBLISHED'"),
        ),
    )

    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"))
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[VersionStatus] = mapped_column(
        Enum(VersionStatus, name="version_status"), default=VersionStatus.DRAFT, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    test: Mapped[Test] = relationship(back_populates="versions")
    modules: Mapped[list[TestModule]] = relationship(
        back_populates="test_version",
        cascade="all, delete-orphan",
        order_by="TestModule.order_index",
    )
    assets: Mapped[list[Asset]] = relationship(
        back_populates="test_version", cascade="all, delete-orphan", passive_deletes=True
    )


class TestModule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "test_modules"
    __table_args__ = (UniqueConstraint("test_version_id", "module_type"),)

    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="CASCADE")
    )
    module_type: Mapped[ModuleType] = mapped_column(
        Enum(ModuleType, name="module_type"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(240))
    recommended_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    audio_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )

    test_version: Mapped[TestVersion] = relationship(back_populates="modules")
    audio_asset: Mapped[Asset | None] = relationship(foreign_keys=[audio_asset_id])
    passages: Mapped[list[ReadingPassage]] = relationship(
        back_populates="module", cascade="all, delete-orphan", order_by="ReadingPassage.order_index"
    )
    listening_parts: Mapped[list[ListeningPart]] = relationship(
        back_populates="module", cascade="all, delete-orphan", order_by="ListeningPart.order_index"
    )
    writing_tasks: Mapped[list[WritingTask]] = relationship(
        back_populates="module", cascade="all, delete-orphan", order_by="WritingTask.order_index"
    )
    question_groups: Mapped[list[QuestionGroup]] = relationship(
        back_populates="module", cascade="all, delete-orphan", order_by="QuestionGroup.order_index"
    )


class ReadingPassage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reading_passages"
    __table_args__ = (UniqueConstraint("module_id", "order_index"),)

    module_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_modules.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    plain_text: Mapped[str] = mapped_column(Text, nullable=False)

    module: Mapped[TestModule] = relationship(back_populates="passages")
    question_groups: Mapped[list[QuestionGroup]] = relationship(
        back_populates="passage", order_by="QuestionGroup.order_index"
    )


class ListeningPart(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "listening_parts"
    __table_args__ = (UniqueConstraint("module_id", "order_index"),)

    module_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_modules.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    module: Mapped[TestModule] = relationship(back_populates="listening_parts")
    question_groups: Mapped[list[QuestionGroup]] = relationship(
        back_populates="listening_part", order_by="QuestionGroup.order_index"
    )


class WritingTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "writing_tasks"
    __table_args__ = (UniqueConstraint("module_id", "order_index"),)

    module_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_modules.id", ondelete="CASCADE"))
    task_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    image_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    minimum_recommended_words: Mapped[int | None] = mapped_column(Integer)
    recommended_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    module: Mapped[TestModule] = relationship(back_populates="writing_tasks")


class QuestionGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "question_groups"
    __table_args__ = (UniqueConstraint("module_id", "order_index"),)

    module_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_modules.id", ondelete="CASCADE"))
    passage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reading_passages.id", ondelete="SET NULL")
    )
    listening_part_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("listening_parts.id", ondelete="SET NULL"), index=True
    )
    image_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    section_reference: Mapped[str | None] = mapped_column(String(120))
    question_type: Mapped[str] = mapped_column(String(80), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    module: Mapped[TestModule] = relationship(back_populates="question_groups")
    passage: Mapped[ReadingPassage | None] = relationship(back_populates="question_groups")
    listening_part: Mapped[ListeningPart | None] = relationship(back_populates="question_groups")
    image_asset: Mapped[Asset | None] = relationship(foreign_keys=[image_asset_id])
    questions: Mapped[list[Question]] = relationship(
        back_populates="question_group",
        cascade="all, delete-orphan",
        order_by="Question.order_index",
    )


class Question(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("question_group_id", "number"),
        UniqueConstraint("question_group_id", "order_index"),
    )

    question_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_groups.id", ondelete="CASCADE")
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    answer_key: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    question_group: Mapped[QuestionGroup] = relationship(back_populates="questions")


class Attempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attempts"

    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="RESTRICT"), index=True
    )
    module_type: Mapped[ModuleType] = mapped_column(
        Enum(ModuleType, name="attempt_module_type"), nullable=False
    )
    timer_mode: Mapped[TimerMode] = mapped_column(
        Enum(TimerMode, name="timer_mode"), nullable=False
    )
    timer_limit_seconds: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, name="attempt_status"), nullable=False
    )
    finished_reason: Mapped[FinishedReason | None] = mapped_column(
        Enum(FinishedReason, name="finished_reason")
    )
    raw_score: Mapped[int | None] = mapped_column(Integer)
    max_score: Mapped[int | None] = mapped_column(Integer)

    test_version: Mapped[TestVersion] = relationship()
    answers: Mapped[list[AttemptAnswer]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )
    writing_responses: Mapped[list[AttemptWritingResponse]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )
    highlights: Mapped[list[Highlight]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )
    flags: Mapped[list[QuestionFlag]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )
    events: Mapped[list[AttemptEvent]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


class AttemptAnswer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attempt_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)

    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"))
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)

    attempt: Mapped[Attempt] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship()


class AttemptWritingResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attempt_writing_responses"
    __table_args__ = (UniqueConstraint("attempt_id", "writing_task_id"),)

    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    writing_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("writing_tasks.id", ondelete="RESTRICT")
    )
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    attempt: Mapped[Attempt] = relationship(back_populates="writing_responses")
    writing_task: Mapped[WritingTask] = relationship()


class Highlight(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "highlights"

    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    passage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reading_passages.id", ondelete="RESTRICT")
    )
    start_block_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_block_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    attempt: Mapped[Attempt] = relationship(back_populates="highlights")


class QuestionFlag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "question_flags"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)

    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"))
    flagged: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    attempt: Mapped[Attempt] = relationship(back_populates="flags")


class Asset(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "assets"

    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="CASCADE"), index=True
    )
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, name="asset_type"), nullable=False
    )
    relative_path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    test_version: Mapped[TestVersion] = relationship(back_populates="assets")


class AttemptEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "attempt_events"

    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type"), nullable=False
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL")
    )
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    attempt: Mapped[Attempt] = relationship(back_populates="events")
