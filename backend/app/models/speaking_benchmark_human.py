"""Source-bound human assessments, separate from legacy labels and AI results."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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

FIELDS = ("fc", "lr", "gra", "pr", "overall")


def band_constraints():
    return tuple(
        CheckConstraint(
            f"{field} IS NULL OR ({field} BETWEEN 0 AND 9 AND {field} * 2 = floor({field} * 2))",
            name=f"{field}_half_band",
        )
        for field in FIELDS
    )


def source_constraints():
    return (
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
        CheckConstraint("review_revision > 0", name="review_revision"),
        CheckConstraint(
            "source_sha256 ~ '^[a-f0-9]{64}$' AND manifest_fingerprint ~ '^[a-f0-9]{64}$'",
            name="fingerprints",
        ),
    )


class SpeakingBenchmarkRater(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_raters"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        UniqueConstraint("owner_id", "user_id"),
        UniqueConstraint("owner_id", "external_key"),
        CheckConstraint("kind IN ('INTERNAL','EXTERNAL')", name="kind"),
        CheckConstraint(
            "(kind = 'INTERNAL' AND user_id IS NOT NULL AND external_key IS NULL) OR (kind = 'EXTERNAL' AND user_id IS NULL AND length(trim(external_key)) > 0)",
            name="identity",
        ),
        CheckConstraint("length(trim(display_name)) > 0", name="display_name"),
        Index("ix_speaking_benchmark_rater_owner", "owner_id", "created_at", "id"),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    external_key: Mapped[str | None] = mapped_column(String(160))
    display_name: Mapped[str] = mapped_column(String(200))


class SpeakingBenchmarkRaterAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_rater_assignments"
    __table_args__ = (
        *source_constraints(),
        ForeignKeyConstraint(
            ["rater_id", "owner_id"],
            ["speaking_benchmark_raters.id", "speaking_benchmark_raters.owner_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "owner_id"),
        CheckConstraint("revision >= 1", name="revision"),
        Index(
            "uq_speaking_benchmark_active_assignment",
            "sample_id",
            "review_revision",
            "rater_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_speaking_benchmark_assignment_rater", "rater_id", "created_at", "id"),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    sample_id: Mapped[UUID] = mapped_column()
    review_revision: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    manifest_fingerprint: Mapped[str] = mapped_column(String(64))
    rater_id: Mapped[UUID] = mapped_column()
    assigned_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    permitted_original_audio: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class SpeakingBenchmarkHumanAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_human_assessments"
    __table_args__ = (
        *source_constraints(),
        *band_constraints(),
        ForeignKeyConstraint(
            ["assignment_id", "owner_id"],
            [
                "speaking_benchmark_rater_assignments.id",
                "speaking_benchmark_rater_assignments.owner_id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["rater_id", "owner_id"],
            ["speaking_benchmark_raters.id", "speaking_benchmark_raters.owner_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("assignment_id", "revision"),
        CheckConstraint("revision > 0 AND status = 'SUBMITTED'", name="submission"),
        CheckConstraint(
            "provenance IN ('internal_blind','external_verified_report','external_unverified')",
            name="provenance",
        ),
        CheckConstraint(
            "provenance != 'external_verified_report' OR length(trim(source_reference)) > 0",
            name="verified_reference",
        ),
        Index(
            "ix_speaking_benchmark_assessment_sample",
            "sample_id",
            "review_revision",
            "rater_id",
            "revision",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    sample_id: Mapped[UUID] = mapped_column()
    review_revision: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    manifest_fingerprint: Mapped[str] = mapped_column(String(64))
    assignment_id: Mapped[UUID] = mapped_column()
    rater_id: Mapped[UUID] = mapped_column()
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="SUBMITTED")
    fc: Mapped[Decimal | None] = mapped_column(Numeric())
    lr: Mapped[Decimal | None] = mapped_column(Numeric())
    gra: Mapped[Decimal | None] = mapped_column(Numeric())
    pr: Mapped[Decimal | None] = mapped_column(Numeric())
    overall: Mapped[Decimal | None] = mapped_column(Numeric())
    comments: Mapped[dict] = mapped_column(JSONB, default=dict)
    provenance: Mapped[str] = mapped_column(String(40))
    source_reference: Mapped[str] = mapped_column(Text, default="")
    independently_performed: Mapped[bool] = mapped_column(Boolean)
    authored_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SpeakingBenchmarkAdjudication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_adjudications"
    __table_args__ = (
        *source_constraints(),
        *band_constraints(),
        UniqueConstraint("sample_id", "review_revision", "revision"),
        CheckConstraint(
            "revision > 0 AND length(trim(rationale)) > 0 AND length(trim(policy_version)) > 0",
            name="decision",
        ),
        CheckConstraint(
            "jsonb_typeof(assessment_refs) = 'array' AND jsonb_array_length(assessment_refs) > 0",
            name="assessments",
        ),
        Index(
            "ix_speaking_benchmark_adjudication_sample", "sample_id", "review_revision", "revision"
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    sample_id: Mapped[UUID] = mapped_column()
    review_revision: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    manifest_fingerprint: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    assessment_refs: Mapped[list] = mapped_column(JSONB)
    fc: Mapped[Decimal | None] = mapped_column(Numeric())
    lr: Mapped[Decimal | None] = mapped_column(Numeric())
    gra: Mapped[Decimal | None] = mapped_column(Numeric())
    pr: Mapped[Decimal | None] = mapped_column(Numeric())
    overall: Mapped[Decimal | None] = mapped_column(Numeric())
    rationale: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(100))
    provenance: Mapped[str] = mapped_column(String(40), default="owner_human_adjudication")
    adjudicator_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    adjudicated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
