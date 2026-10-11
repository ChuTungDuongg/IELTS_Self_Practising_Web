import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import ModerationScope, ModerationStatus


class TestVersionModeration(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "test_version_moderation"
    __table_args__ = (
        Index(
            "uq_moderation_pending_scope",
            "test_version_id",
            "scope",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )
    test_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_versions.id", ondelete="RESTRICT"), index=True
    )
    scope: Mapped[ModerationScope] = mapped_column(Enum(ModerationScope, name="moderation_scope"))
    status: Mapped[ModerationStatus] = mapped_column(
        Enum(ModerationStatus, name="moderation_status"),
        default=ModerationStatus.PENDING,
        index=True,
    )
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    submit_note: Mapped[str | None] = mapped_column(String(2000))
    review_note: Mapped[str | None] = mapped_column(String(2000))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    revoke_reason: Mapped[str | None] = mapped_column(String(2000))
