from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WritingAIRunStatus


class WritingAIGradingRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "writing_ai_grading_runs"
    __table_args__ = (
        Index(
            "ix_writing_ai_runs_cache",
            "attempt_id",
            "writing_task_id",
            "input_fingerprint",
            "status",
        ),
        CheckConstraint("raw_mean >= 0 AND raw_mean <= 9", name="raw_mean_range"),
        CheckConstraint(
            "overall_band >= 0 AND overall_band <= 9 AND mod(overall_band * 2, 1) = 0",
            name="overall_half_band",
        ),
    )

    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    writing_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("writing_tasks.id", ondelete="RESTRICT")
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[WritingAIRunStatus] = mapped_column(
        Enum(WritingAIRunStatus, name="writing_ai_run_status"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_mean: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))
    overall_band: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WritingAIGradingEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "writing_ai_grading_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence"),
        CheckConstraint("sequence > 0", name="positive_sequence"),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("writing_ai_grading_runs.id", ondelete="CASCADE")
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
