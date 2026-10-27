from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ClassroomAssignmentExtension(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "classroom_assignment_extensions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id"),
        CheckConstraint("additional_attempts >= 0", name="additional_attempts"),
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("classroom_assignments.id", ondelete="RESTRICT")
    )
    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    override_due: Mapped[bool] = mapped_column(Boolean, default=False)
    due_at_override: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    override_cutoff: Mapped[bool] = mapped_column(Boolean, default=False)
    cutoff_at_override: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    additional_attempts: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class AssignmentPolicyEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only scheduling snapshots. Nullable student_id means base policy."""

    __tablename__ = "classroom_assignment_policy_events"
    __table_args__ = (
        UniqueConstraint("assignment_id", "revision"),
        Index(
            "ix_assignment_policy_history",
            "assignment_id",
            "student_id",
            "effective_at",
            "revision",
        ),
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("classroom_assignments.id", ondelete="RESTRICT")
    )
    student_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    revision: Mapped[int] = mapped_column(Integer)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    kind: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text)
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_attempts: Mapped[int | None] = mapped_column(Integer)
    allow_late_submission: Mapped[bool] = mapped_column(Boolean, default=True)
    override_due: Mapped[bool] = mapped_column(Boolean, default=False)
    override_cutoff: Mapped[bool] = mapped_column(Boolean, default=False)
    additional_attempts: Mapped[int] = mapped_column(Integer, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
