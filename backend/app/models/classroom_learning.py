from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ClassroomLearningPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "classroom_learning_plans"
    __table_args__ = (
        UniqueConstraint("classroom_id", "id"),
        CheckConstraint(
            "target_skill IN ('READING','LISTENING','WRITING','SPEAKING')",
            name="ck_classroom_learning_plans_skill",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','COMPLETED','ARCHIVED')", name="ck_classroom_learning_plans_status"
        ),
        Index(
            "ix_classroom_learning_plans_student",
            "classroom_id",
            "student_id",
            "status",
            "created_at",
        ),
    )
    classroom_id: Mapped[UUID] = mapped_column(ForeignKey("classrooms.id", ondelete="RESTRICT"))
    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(240))
    target_skill: Mapped[str] = mapped_column(String(16))
    focus_area: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class ClassroomLearningPlanItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "classroom_learning_plan_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["classroom_id", "plan_id"],
            ["classroom_learning_plans.classroom_id", "classroom_learning_plans.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["classroom_id", "assignment_id"],
            ["classroom_assignments.classroom_id", "classroom_assignments.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["classroom_id", "resource_id"],
            ["classroom_resources.classroom_id", "classroom_resources.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(assignment_id IS NOT NULL)::int + (resource_id IS NOT NULL)::int = 1",
            name="ck_classroom_learning_plan_items_target",
        ),
        CheckConstraint(
            "assignment_id IS NULL OR (completed_at IS NULL AND completed_by_user_id IS NULL)",
            name="ck_classroom_learning_plan_items_resource_completion",
        ),
        UniqueConstraint("plan_id", "assignment_id"),
        UniqueConstraint("plan_id", "resource_id"),
        Index("ix_classroom_learning_plan_items_plan", "plan_id", "active", "position"),
    )
    classroom_id: Mapped[UUID]
    plan_id: Mapped[UUID]
    assignment_id: Mapped[UUID | None]
    resource_id: Mapped[UUID | None]
    position: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
