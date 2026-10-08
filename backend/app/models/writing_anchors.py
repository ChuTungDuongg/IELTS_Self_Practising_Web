from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WritingAnchorSet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "writing_anchor_sets"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','ACTIVE','RETIRED')", name="valid_status"),
        CheckConstraint("version > 0", name="positive_version"),
        Index("uq_writing_anchor_sets_version", "version", unique=True),
        Index(
            "uq_writing_anchor_sets_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_writing_anchor_sets_draft",
            "status",
            unique=True,
            postgresql_where=text("status = 'DRAFT'"),
        ),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WritingHumanAnchor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "writing_human_anchors"
    __table_args__ = tuple(
        CheckConstraint(
            f"{trait}_score >= 0 AND {trait}_score <= 9 AND mod({trait}_score * 2, 1) = 0",
            name=f"{trait}_half_band",
        )
        for trait in ("ta", "cc", "lr", "gra")
    ) + (
        CheckConstraint("length(btrim(response_text)) > 0", name="nonblank_response"),
        Index("ix_writing_human_anchors_set_task", "anchor_set_id", "writing_task_id"),
    )

    anchor_set_id: Mapped[UUID] = mapped_column(
        ForeignKey("writing_anchor_sets.id", ondelete="RESTRICT")
    )
    writing_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("writing_tasks.id", ondelete="RESTRICT")
    )
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    ta_score: Mapped[Decimal] = mapped_column(Numeric(2, 1), nullable=False)
    cc_score: Mapped[Decimal] = mapped_column(Numeric(2, 1), nullable=False)
    lr_score: Mapped[Decimal] = mapped_column(Numeric(2, 1), nullable=False)
    gra_score: Mapped[Decimal] = mapped_column(Numeric(2, 1), nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    admin_note: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[str | None] = mapped_column(Text)
