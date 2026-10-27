import uuid
from datetime import datetime

from sqlalchemy import (
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
        Index("ix_classroom_assignments_feed", "classroom_id", "status", "created_at", "id"),
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
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus, name="assignment_status"), default=AssignmentStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
