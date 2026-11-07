"""Private, source-bound predictions and physical request accounting."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

FINAL_STATUSES = ("COMPLETED", "PARTIAL", "FAILED", "CANCELLED")


class SpeakingBenchmarkGradingRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_grading_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sample_id", "owner_id"],
            ["speaking_benchmark_samples.id", "speaking_benchmark_samples.owner_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["sample_id", "review_revision"],
            ["speaking_benchmark_reviews.sample_id", "speaking_benchmark_reviews.revision"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("owner_id", "submission_key"),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','INTERRUPTED','COMPLETED','PARTIAL','FAILED','CANCELLED')",
            name="status",
        ),
        CheckConstraint(
            "review_revision > 0 AND candidate_ms > 0 AND window_count > 0 AND progress BETWEEN 0 AND 100",
            name="bounds",
        ),
        CheckConstraint(
            "status != 'RUNNING' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="lease",
        ),
        Index("ix_speaking_benchmark_grading_queue", "status", "created_at"),
        Index(
            "uq_speaking_benchmark_grading_active",
            "sample_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING','RUNNING','INTERRUPTED')"),
        ),
    )
    sample_id: Mapped[UUID] = mapped_column()
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    review_revision: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    manifest_fingerprint: Mapped[str] = mapped_column(String(64))
    config_fingerprint: Mapped[str] = mapped_column(String(64))
    submission_key: Mapped[UUID] = mapped_column()
    configuration: Mapped[dict] = mapped_column(JSONB)
    consent: Mapped[dict] = mapped_column(JSONB)
    candidate_ms: Mapped[int] = mapped_column(Integer)
    window_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    stage: Mapped[str] = mapped_column(String(100), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[UUID | None] = mapped_column()
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    prediction: Mapped[dict | None] = mapped_column(JSONB)


class SpeakingBenchmarkGradingCheckpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_grading_checkpoints"
    __table_args__ = (
        UniqueConstraint("run_id", "stage", "identity", "attempt"),
        CheckConstraint("attempt > 0", name="attempt"),
        CheckConstraint(
            "status IN ('ATTEMPTED','COMPLETED','FAILED','INTERRUPTED_BILLING_UNKNOWN')",
            name="status",
        ),
        CheckConstraint("billing_state IN ('UNKNOWN','OBSERVED','NOT_BILLABLE')", name="billing"),
        CheckConstraint("status != 'COMPLETED' OR result IS NOT NULL", name="result"),
        Index("ix_speaking_benchmark_checkpoint_reuse", "identity", "status"),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_benchmark_grading_runs.id", ondelete="CASCADE")
    )
    stage: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(80))
    identity: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="ATTEMPTED")
    billing_state: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    result: Mapped[dict | None] = mapped_column(JSONB)
    usage: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    reused_from: Mapped[UUID | None] = mapped_column(
        ForeignKey("speaking_benchmark_grading_checkpoints.id", ondelete="SET NULL")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
