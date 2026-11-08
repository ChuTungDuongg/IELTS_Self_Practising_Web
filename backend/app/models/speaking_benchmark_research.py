"""Private research artifacts. References are never inference inputs."""

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SpeakingBenchmarkASRReference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_asr_references"
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
        UniqueConstraint("sample_id", "review_revision", "segment_id", "revision"),
        CheckConstraint(
            "revision > 0 AND review_revision > 0 AND start_ms >= 0 AND end_ms > start_ms",
            name="bounds",
        ),
        CheckConstraint("status IN ('DRAFT','VERIFIED')", name="status"),
        CheckConstraint(
            "status != 'VERIFIED' OR (provenance = 'independent_human_transcriber' AND reviewer_id IS NOT NULL AND verified_at IS NOT NULL AND length(trim(source_reference)) > 0)",
            name="verification",
        ),
        Index(
            "ix_speaking_research_reference_window",
            "sample_id",
            "review_revision",
            "segment_id",
            "revision",
        ),
    )
    sample_id: Mapped[UUID] = mapped_column()
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    review_revision: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    manifest_fingerprint: Mapped[str] = mapped_column(String(64))
    segment_id: Mapped[str] = mapped_column(String(100))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    normalization: Mapped[str] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text)
    annotations: Mapped[list] = mapped_column(JSONB)
    uncertainty: Mapped[list] = mapped_column(JSONB)
    metadata_labels: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    provenance: Mapped[str] = mapped_column(String(80))
    source_reference: Mapped[str] = mapped_column(String(1000))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewer_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpeakingBenchmarkExperiment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_experiments"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        UniqueConstraint("owner_id", "submission_key"),
        CheckConstraint("mode IN ('ASR_ONLY','PAIRED_GRADING')", name="mode"),
        CheckConstraint(
            "status IN ('DRAFT','PENDING','RUNNING','INTERRUPTED','COMPLETED','PARTIAL','FAILED','CANCELLED')",
            name="status",
        ),
        Index("ix_speaking_research_owner_created", "owner_id", "created_at", "id"),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    submission_key: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(24))
    configuration: Mapped[dict] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(String(64))
    evaluation_selection: Mapped[dict] = mapped_column(JSONB)
    consent: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    holdout_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpeakingBenchmarkExperimentVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_experiment_variants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "owner_id"],
            ["speaking_benchmark_experiments.id", "speaking_benchmark_experiments.owner_id"],
            ondelete="CASCADE",
        ),
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
        UniqueConstraint("experiment_id", "sample_id", "provider_key"),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','WAITING','INTERRUPTED','COMPLETED','PARTIAL','FAILED','CANCELLED')",
            name="status",
        ),
        CheckConstraint(
            "status != 'RUNNING' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="lease",
        ),
        Index("ix_speaking_research_variant_queue", "status", "created_at"),
    )
    experiment_id: Mapped[UUID] = mapped_column()
    owner_id: Mapped[UUID] = mapped_column()
    sample_id: Mapped[UUID] = mapped_column()
    review_revision: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    manifest_fingerprint: Mapped[str] = mapped_column(String(64))
    provider_key: Mapped[str] = mapped_column(String(80))
    configuration: Mapped[dict] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(String(64))
    windows: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    error_code: Mapped[str | None] = mapped_column(String(100))
    grading_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("speaking_benchmark_grading_runs.id", ondelete="SET NULL")
    )
    lease_token: Mapped[UUID | None] = mapped_column()
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpeakingBenchmarkASRObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An attempt or a cache receipt, containing only normalized provider evidence."""

    __tablename__ = "speaking_benchmark_asr_observations"
    __table_args__ = (
        UniqueConstraint("variant_id", "segment_id", "attempt"),
        CheckConstraint("attempt > 0", name="attempt"),
        CheckConstraint(
            "status IN ('ATTEMPTED','COMPLETED','FAILED','INTERRUPTED_BILLING_UNKNOWN')",
            name="status",
        ),
        CheckConstraint("status != 'COMPLETED' OR result IS NOT NULL", name="result"),
        Index("ix_speaking_research_observation_cache", "identity", "status"),
    )
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_benchmark_experiment_variants.id", ondelete="CASCADE")
    )
    segment_id: Mapped[str] = mapped_column(String(100))
    identity: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40))
    billing_state: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    result: Mapped[dict | None] = mapped_column(JSONB)
    usage: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    reused_from: Mapped[UUID | None] = mapped_column(
        ForeignKey("speaking_benchmark_asr_observations.id", ondelete="SET NULL")
    )
    reconciliation: Mapped[dict | None] = mapped_column(JSONB)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
