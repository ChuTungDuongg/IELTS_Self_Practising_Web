"""Structured course content; assignment rows remain canonical and immutable references."""

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
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


class ClassroomSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "classroom_sections"
    __table_args__ = (
        UniqueConstraint("classroom_id", "id"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="status"),
        CheckConstraint("position >= 0", name="position"),
        Index("ix_classroom_sections_order", "classroom_id", "position", "id"),
    )
    classroom_id: Mapped[UUID] = mapped_column(ForeignKey("classrooms.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", server_default="DRAFT")
    position: Mapped[int] = mapped_column(Integer, default=0)


class ClassroomResource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "classroom_resources"
    __table_args__ = (
        UniqueConstraint("classroom_id", "id"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="status"),
        CheckConstraint("kind IN ('TEXT','LINK','FILE')", name="kind"),
        CheckConstraint(
            "(kind='TEXT' AND body IS NOT NULL AND url IS NULL AND storage_key IS NULL) OR "
            "(kind='LINK' AND url IS NOT NULL AND body IS NULL AND storage_key IS NULL) OR "
            "(kind='FILE' AND storage_key IS NOT NULL AND body IS NULL AND url IS NULL "
            "AND original_filename IS NOT NULL AND media_type IS NOT NULL AND size_bytes > 0)",
            name="target",
        ),
        Index("ix_classroom_resources_visibility", "classroom_id", "status", "id"),
    )
    classroom_id: Mapped[UUID] = mapped_column(ForeignKey("classrooms.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(12))
    body: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", server_default="DRAFT")
    storage_key: Mapped[str | None] = mapped_column(String(512), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)


class ClassroomContentItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "classroom_content_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["classroom_id", "section_id"],
            ["classroom_sections.classroom_id", "classroom_sections.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["classroom_id", "resource_id"],
            ["classroom_resources.classroom_id", "classroom_resources.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["classroom_id", "assignment_id"],
            ["classroom_assignments.classroom_id", "classroom_assignments.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(resource_id IS NOT NULL)::int + (assignment_id IS NOT NULL)::int = 1",
            name="one_target",
        ),
        CheckConstraint("position >= 0", name="position"),
        UniqueConstraint("resource_id"),
        UniqueConstraint("assignment_id"),
        Index("ix_classroom_content_items_order", "classroom_id", "section_id", "position", "id"),
    )
    classroom_id: Mapped[UUID] = mapped_column(ForeignKey("classrooms.id", ondelete="RESTRICT"))
    section_id: Mapped[UUID | None]
    resource_id: Mapped[UUID | None]
    assignment_id: Mapped[UUID | None]
    position: Mapped[int] = mapped_column(Integer, default=0)
