from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SpeakingAIGradingRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_ai_grading_runs"
    __table_args__ = (
        UniqueConstraint("attempt_id", "cache_key"),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')", name="valid_status"
        ),
        CheckConstraint("raw_mean >= 0 AND raw_mean <= 9", name="raw_mean_range"),
        CheckConstraint(
            "overall_band >= 0 AND overall_band <= 9 AND mod(overall_band * 2, 1) = 0",
            name="overall_half_band",
        ),
    )
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    requested_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    cache_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    stage: Mapped[str] = mapped_column(String(32), default="PENDING")
    identity_json: Mapped[dict] = mapped_column(JSONB)
    manifest_json: Mapped[list] = mapped_column(JSONB)
    criteria_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    usage_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    raw_mean: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))
    overall_band: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    error_code: Mapped[str | None] = mapped_column(String(80))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpeakingAIGradingEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_ai_grading_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence"),
        CheckConstraint("sequence > 0", name="positive_sequence"),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_ai_grading_runs.id", ondelete="CASCADE")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
