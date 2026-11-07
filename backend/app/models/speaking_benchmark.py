"""Private admin datasets. No relationship to learner attempts or AI predictions."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SpeakingBenchmarkSample(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_samples"
    __table_args__ = (
        UniqueConstraint("owner_id", "code"),
        UniqueConstraint("owner_id", "source_sha256"),
        CheckConstraint("split IN ('DEV','HOLDOUT')", name="split"),
        CheckConstraint("status IN ('DRAFT','PROCESSING','REVIEW','APPROVED')", name="status"),
        CheckConstraint(
            "byte_size BETWEEN 1 AND 134217728 AND duration_ms BETWEEN 1 AND 1800000",
            name="audio_bounds",
        ),
        CheckConstraint("mime_type IN ('audio/wav','audio/mpeg')", name="mime"),
        CheckConstraint(
            "length(trim(code)) > 0 AND length(trim(source_note)) BETWEEN 1 AND 2000",
            name="metadata",
        ),
        CheckConstraint("source_sha256 ~ '^[a-f0-9]{64}$'", name="sha256"),
        CheckConstraint("rights_confirmed", name="rights"),
        CheckConstraint(
            "revision >= 1 AND review_revision >= 0 AND label_revision >= 0", name="revisions"
        ),
        Index("ix_speaking_benchmark_owner_created", "owner_id", "created_at", "id"),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(String(80))
    audio_key: Mapped[str] = mapped_column(String(512), unique=True)
    source_sha256: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(32))
    byte_size: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    candidate_id: Mapped[str] = mapped_column(String(120), default="")
    split: Mapped[str] = mapped_column(String(12), default="DEV")
    source_note: Mapped[str] = mapped_column(Text)
    rights_confirmed: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    review_revision: Mapped[int] = mapped_column(Integer, default=0)
    label_revision: Mapped[int] = mapped_column(Integer, default=0)
    approved_fingerprint: Mapped[str | None] = mapped_column(String(64))


class SpeakingBenchmarkJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_jobs"
    __table_args__ = (
        CheckConstraint("kind = 'DIARIZATION'", name="kind"),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')", name="status"
        ),
        CheckConstraint("progress BETWEEN 0 AND 100 AND attempts BETWEEN 0 AND 3", name="bounds"),
        CheckConstraint(
            "status != 'RUNNING' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL)",
            name="running_lease",
        ),
        CheckConstraint("status != 'COMPLETED' OR result IS NOT NULL", name="completed_result"),
        Index("ix_speaking_benchmark_job_queue", "status", "created_at"),
        Index(
            "uq_speaking_benchmark_job_active",
            "sample_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING','RUNNING')"),
        ),
    )
    sample_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_benchmark_samples.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(20), default="DIARIZATION")
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    stage: Mapped[str] = mapped_column(String(40), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[UUID | None] = mapped_column()
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str] = mapped_column(String(64))
    source_sha256: Mapped[str] = mapped_column(String(64))
    configuration: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpeakingBenchmarkReview(TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_reviews"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision"),
        CheckConstraint("(manifest IS NULL) = (approved_at IS NULL)", name="approval"),
    )
    sample_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_benchmark_samples.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_benchmark_jobs.id", ondelete="CASCADE")
    )
    draft: Mapped[dict] = mapped_column(JSONB)
    manifest: Mapped[dict | None] = mapped_column(JSONB)
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str | None] = mapped_column(String(64))


class SpeakingBenchmarkHumanLabel(TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_human_labels"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision"),
        CheckConstraint(
            "provenance IN ('human_examiner','published_human_assessment','unverified')",
            name="provenance",
        ),
        CheckConstraint(
            "NOT verified OR (provenance IN ('human_examiner','published_human_assessment') AND length(trim(reference)) > 0)",
            name="verified",
        ),
        *(
            CheckConstraint(
                f"{field} IS NULL OR ({field} BETWEEN 0 AND 9 AND {field} * 2 = floor({field} * 2))",
                name=f"{field}_half_band",
            )
            for field in ("fc", "lr", "gra", "pr", "overall")
        ),
    )
    sample_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_benchmark_samples.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    fc: Mapped[Decimal | None] = mapped_column(Numeric())
    lr: Mapped[Decimal | None] = mapped_column(Numeric())
    gra: Mapped[Decimal | None] = mapped_column(Numeric())
    pr: Mapped[Decimal | None] = mapped_column(Numeric())
    overall: Mapped[Decimal | None] = mapped_column(Numeric())
    provenance: Mapped[str] = mapped_column(String(40))
    reference: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean)
    examiner: Mapped[str] = mapped_column(String(500))
    notes: Mapped[str] = mapped_column(Text)
    authored_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
