"""Authored Speaking content and private candidate runtime state."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SpeakingPromptType

if TYPE_CHECKING:
    from app.models.entities import TestModule


class SpeakingPart(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_parts"
    __table_args__ = (
        UniqueConstraint("module_id", "part_number"),
        CheckConstraint("part_number BETWEEN 1 AND 3", name="part_number"),
    )

    module_id: Mapped[UUID] = mapped_column(ForeignKey("test_modules.id", ondelete="CASCADE"))
    part_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(240))
    instructions: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    module: Mapped[TestModule] = relationship(back_populates="speaking_parts")
    prompts: Mapped[list[SpeakingPrompt]] = relationship(
        back_populates="part", cascade="all, delete-orphan", order_by="SpeakingPrompt.order_index"
    )


class SpeakingPrompt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_prompts"
    __table_args__ = (
        UniqueConstraint("speaking_part_id", "order_index", deferrable=True, initially="DEFERRED"),
    )

    speaking_part_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_parts.id", ondelete="CASCADE")
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_type: Mapped[SpeakingPromptType] = mapped_column(
        Enum(SpeakingPromptType, name="speaking_prompt_type"),
        nullable=False,
    )
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    preparation_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    part: Mapped[SpeakingPart] = relationship(back_populates="prompts")


class SpeakingResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_responses"
    __table_args__ = (UniqueConstraint("attempt_id", "prompt_id"),)

    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    prompt_id: Mapped[UUID] = mapped_column(ForeignKey("speaking_prompts.id", ondelete="RESTRICT"))
    active_take_number: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    completion_reason: Mapped[str | None] = mapped_column(String(24))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    committed_audio_fingerprint: Mapped[str | None] = mapped_column(String(64))


class SpeakingResponseTake(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_response_takes"
    __table_args__ = (UniqueConstraint("response_id", "take_number"),)

    response_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_responses.id", ondelete="CASCADE")
    )
    take_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class SpeakingPromptProgress(TimestampMixin, Base):
    __tablename__ = "speaking_prompt_progress"

    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"), primary_key=True
    )
    prompt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("speaking_prompts.id", ondelete="RESTRICT")
    )
    response_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("speaking_responses.id", ondelete="SET NULL")
    )
    take_number: Mapped[int | None] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(24), default="QUESTION_ENTER")
    phase_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phase_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_confirmed_remaining_ms: Mapped[int] = mapped_column(Integer, default=0)
    interruption_generation: Mapped[int] = mapped_column(Integer, default=0)
    interruption_count: Mapped[int] = mapped_column(Integer, default=0)
    recovery_state: Mapped[str | None] = mapped_column(String(24))
    recovery_grace_used: Mapped[bool] = mapped_column(Boolean, default=False)
    last_resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Private convenience data lives ONLY here; never on spoken response/take DTOs.
    scratch_notes: Mapped[str] = mapped_column(Text, default="")


class SpeakingAudioSegment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_audio_segments"
    __table_args__ = (UniqueConstraint("response_take_id", "segment_index"),)
    response_take_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_response_takes.id", ondelete="CASCADE")
    )
    segment_index: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(80))
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpeakingAudioChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_audio_chunks"
    __table_args__ = (UniqueConstraint("segment_id", "sequence"),)
    segment_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_audio_segments.id", ondelete="CASCADE")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)


class SpeakingMediaCleanup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Transactional outbox survives deleting the authorization/manifest rows."""

    __tablename__ = "speaking_media_cleanup"
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
