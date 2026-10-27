"""Contextual staff access, independent of global account privileges."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class ClassroomStaff(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "classroom_staff"
    __table_args__ = (
        CheckConstraint("staff_role IN ('CO_TEACHER','TEACHING_ASSISTANT')", name="role"),
        CheckConstraint("status IN ('PENDING','ACCEPTED','DECLINED','CANCELLED','REVOKED')", name="status"),
        Index("uq_classroom_staff_current", "classroom_id", "user_id", unique=True,
              postgresql_where=text("status IN ('PENDING','ACCEPTED')")),
    )
    classroom_id: Mapped[UUID] = mapped_column(ForeignKey("classrooms.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    staff_role: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    invited_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    content_manage: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    discussion_moderate: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    analytics_view: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    learning_plans_manage: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClassroomStaffEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "classroom_staff_events"
    staff_id: Mapped[UUID] = mapped_column(ForeignKey("classroom_staff.id", ondelete="RESTRICT"), index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    staff_role: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16))
    content_manage: Mapped[bool] = mapped_column(Boolean)
    discussion_moderate: Mapped[bool] = mapped_column(Boolean)
    analytics_view: Mapped[bool] = mapped_column(Boolean)
    learning_plans_manage: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
