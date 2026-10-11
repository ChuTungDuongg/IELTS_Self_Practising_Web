"""Authored, versioned Speaking content. No candidate runtime or audio state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
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
