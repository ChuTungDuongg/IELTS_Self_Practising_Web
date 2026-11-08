"""Examiner ASR proposals are separate from human-verified P1 review manifests."""

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SpeakingBenchmarkQuestionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_question_jobs"
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
        CheckConstraint("review_revision > 0", name="revision"),
        CheckConstraint(
            "status IN ('DRAFT','PENDING','RUNNING','INTERRUPTED','COMPLETED','PARTIAL','FAILED','CANCELLED')",
            name="status",
        ),
        CheckConstraint(
            "status != 'RUNNING' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="lease",
        ),
        Index("ix_speaking_questions_queue", "status", "created_at"),
        Index("ix_speaking_questions_sample", "sample_id", "created_at", "id"),
    )
    sample_id: Mapped[UUID] = mapped_column()
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    submission_key: Mapped[UUID] = mapped_column()
    review_revision: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    draft_fingerprint: Mapped[str] = mapped_column(String(64))
    model_fingerprint: Mapped[str] = mapped_column(String(64))
    examiner_speaker_id: Mapped[str] = mapped_column(String(100))
    configuration: Mapped[dict] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(String(64))
    windows: Mapped[list] = mapped_column(JSONB)
    exclusions: Mapped[list] = mapped_column(JSONB)
    consent: Mapped[dict | None] = mapped_column(JSONB)
    proposals: Mapped[list] = mapped_column(JSONB, default=list)
    decisions: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    error_code: Mapped[str | None] = mapped_column(String(100))
    lease_token: Mapped[UUID | None] = mapped_column()
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpeakingBenchmarkQuestionRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_question_requests"
    __table_args__ = (
        UniqueConstraint("job_id", "window_id", "attempt"),
        CheckConstraint("attempt > 0", name="attempt"),
        CheckConstraint(
            "status IN ('ATTEMPTED','COMPLETED','FAILED','INTERRUPTED_BILLING_UNKNOWN')",
            name="status",
        ),
        CheckConstraint("status != 'COMPLETED' OR result IS NOT NULL", name="result"),
        Index("ix_speaking_questions_cache", "identity", "status"),
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_benchmark_question_jobs.id", ondelete="CASCADE")
    )
    window_id: Mapped[str] = mapped_column(String(100))
    identity: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40))
    billing_state: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    result: Mapped[dict | None] = mapped_column(JSONB)
    usage: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    reused_from: Mapped[UUID | None] = mapped_column(
        ForeignKey("speaking_benchmark_question_requests.id", ondelete="SET NULL")
    )
    reconciliation: Mapped[dict | None] = mapped_column(JSONB)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
