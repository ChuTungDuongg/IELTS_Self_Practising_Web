import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ClassroomPost(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "classroom_posts"
    __table_args__ = (
        CheckConstraint("kind IN ('ANNOUNCEMENT', 'DISCUSSION')", name="kind"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="status"),
        CheckConstraint("length(body) BETWEEN 1 AND 20000", name="body_length"),
        Index("ix_classroom_posts_feed", "classroom_id", "status", "pinned", "created_at", "id"),
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="RESTRICT"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", server_default="DRAFT")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClassroomPostResource(Base):
    __tablename__ = "classroom_post_resources"
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classroom_posts.id", ondelete="RESTRICT"), primary_key=True
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classroom_resources.id", ondelete="RESTRICT"), primary_key=True, index=True
    )


class ClassroomComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "classroom_comments"
    __table_args__ = (
        CheckConstraint("state IN ('VISIBLE', 'RETRACTED', 'MODERATED')", name="state"),
        CheckConstraint("length(body) BETWEEN 1 AND 5000", name="body_length"),
        Index("ix_classroom_comments_thread", "post_id", "created_at", "id"),
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classroom_posts.id", ondelete="RESTRICT")
    )
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="VISIBLE", server_default="VISIBLE")
