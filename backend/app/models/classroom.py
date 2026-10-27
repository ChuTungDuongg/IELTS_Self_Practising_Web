import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AssignmentStatus, ClassroomStatus, InvitationStatus


class Classroom(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "classrooms"
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ClassroomStatus] = mapped_column(
        Enum(ClassroomStatus, name="classroom_status"), default=ClassroomStatus.ACTIVE
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ClassroomInvitation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "classroom_invitations"
    __table_args__ = (
        Index(
            "uq_classroom_pending_invitation",
            "classroom_id",
            "invited_email_normalized",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="RESTRICT"), index=True
    )
    invited_email: Mapped[str] = mapped_column(String(320))
    invited_email_normalized: Mapped[str] = mapped_column(String(320), index=True)
    invited_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, name="invitation_status"), default=InvitationStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClassroomMembership(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "classroom_memberships"
    __table_args__ = (
        Index(
            "uq_classroom_active_membership",
            "classroom_id",
            "user_id",
            unique=True,
            postgresql_where=text("left_at IS NULL"),
        ),
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )


class ClassroomAssignment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "classroom_assignments"
    __table_args__ = (
        UniqueConstraint("classroom_id", "id"),
        CheckConstraint("grade_selection IN ('LATEST_ACCEPTED','FIRST_ACCEPTED','BEST_ACCEPTED')", name="grade_selection"),
        Index("ix_classroom_assignments_feed", "classroom_id", "status", "created_at", "id"),
        CheckConstraint("max_attempts IS NULL OR max_attempts >= 1", name="max_attempts"),
        CheckConstraint(
            "available_from IS NULL OR due_at IS NULL OR available_from < due_at",
            name="availability_due",
        ),
        CheckConstraint(
            "due_at IS NULL OR cutoff_at IS NULL OR due_at <= cutoff_at", name="due_cutoff"
        ),
        CheckConstraint(
            "available_from IS NULL OR cutoff_at IS NULL OR available_from < cutoff_at",
            name="availability_cutoff",
        ),
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="RESTRICT"), index=True
    )
    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="RESTRICT"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    title: Mapped[str | None] = mapped_column(String(240))
    note: Mapped[str | None] = mapped_column(Text)
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_attempts: Mapped[int | None] = mapped_column(Integer)
    allow_late_submission: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    policy_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    grade_selection: Mapped[str] = mapped_column(String(24), default="LATEST_ACCEPTED", server_default="LATEST_ACCEPTED")
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus, name="assignment_status"), default=AssignmentStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
