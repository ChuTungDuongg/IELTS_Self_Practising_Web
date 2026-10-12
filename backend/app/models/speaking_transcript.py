from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SpeakingNormalizedAudio(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_normalized_audio"
    __table_args__ = (UniqueConstraint("response_id", "cache_key"),)
    response_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_responses.id", ondelete="CASCADE")
    )
    cache_key: Mapped[str] = mapped_column(String(64))
    source_audio_fingerprint: Mapped[str] = mapped_column(String(64))
    normalizer_version: Mapped[str] = mapped_column(String(80))
    storage_key: Mapped[str] = mapped_column(String(512))
    duration_ms: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class SpeakingTranscriptRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_transcript_runs"
    __table_args__ = (UniqueConstraint("attempt_id", "cache_key"),)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    requested_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    cache_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    identity_json: Mapped[dict] = mapped_column(JSONB)
    manifest_json: Mapped[list] = mapped_column(JSONB)
    responses_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))


class SpeakingTranscriptEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_transcript_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_transcript_runs.id", ondelete="CASCADE")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSONB)


class SpeakingTranscript(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speaking_transcripts"
    __table_args__ = (UniqueConstraint("response_id", "cache_key", "kind"),)
    response_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_responses.id", ondelete="CASCADE")
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("speaking_transcript_runs.id", ondelete="CASCADE")
    )
    cache_key: Mapped[str] = mapped_column(String(64))
    source_audio_fingerprint: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    word_timing_json: Mapped[list] = mapped_column(JSONB)
    provider_json: Mapped[dict] = mapped_column(JSONB)
