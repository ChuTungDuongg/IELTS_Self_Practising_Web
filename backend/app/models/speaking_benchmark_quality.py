"""Frozen, provider-free evaluation records; private assets remain in AssetStorage."""

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


class SpeakingBenchmarkQualitySnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_quality_snapshots"
    __table_args__ = (Index("ix_speaking_quality_owner_created", "owner_id", "created_at", "id"),)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    protocol: Mapped[str] = mapped_column(String(80))
    configuration: Mapped[dict] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    report: Mapped[dict] = mapped_column(JSONB)


class SpeakingBenchmarkEvaluationSuite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_evaluation_suites"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        UniqueConstraint("owner_id", "family_id", "revision"),
        CheckConstraint("revision > 0", name="revision"),
        Index("ix_speaking_suite_owner_created", "owner_id", "created_at", "id"),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    family_id: Mapped[UUID] = mapped_column()
    revision: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    configuration: Mapped[dict] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(String(64))
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SpeakingBenchmarkRegressionGate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_regression_gates"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        ForeignKeyConstraint(
            ["suite_id", "owner_id"],
            [
                "speaking_benchmark_evaluation_suites.id",
                "speaking_benchmark_evaluation_suites.owner_id",
            ],
            ondelete="RESTRICT",
        ),
        Index("ix_speaking_gate_owner_created", "owner_id", "created_at", "id"),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    suite_id: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(160))
    baseline: Mapped[dict] = mapped_column(JSONB)
    candidate: Mapped[dict] = mapped_column(JSONB)
    policy: Mapped[dict] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(String(64))


class SpeakingBenchmarkRegressionReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_regression_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["gate_id", "owner_id"],
            [
                "speaking_benchmark_regression_gates.id",
                "speaking_benchmark_regression_gates.owner_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('PASS','FAIL','INCONCLUSIVE','INVALID')", name="status"),
        Index("ix_speaking_gate_report_owner", "owner_id", "gate_id", "created_at", "id"),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    gate_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(20))
    protocol: Mapped[str] = mapped_column(String(80))
    fingerprint: Mapped[str] = mapped_column(String(64))
    report: Mapped[dict] = mapped_column(JSONB)


class SpeakingBenchmarkHoldoutAudit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_benchmark_holdout_audits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["suite_id", "owner_id"],
            [
                "speaking_benchmark_evaluation_suites.id",
                "speaking_benchmark_evaluation_suites.owner_id",
            ],
            ondelete="RESTRICT",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    suite_id: Mapped[UUID] = mapped_column()
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSONB)
