"""Private playback mapping. Recovery joins have unknown elapsed time, never silence."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AudioSegmentMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    response_id: UUID
    take_number: int = Field(ge=1)
    segment_id: UUID
    normalized_start_ms: int = Field(ge=0, le=1800000, strict=True)
    normalized_end_ms: int = Field(ge=0, le=1800000, strict=True)
    source_start_ms: int = Field(default=0, ge=0, strict=True)
    gap_before_unknown: bool = False
    normalized_start_frame: int | None = Field(default=None, ge=0, strict=True)
    normalized_end_frame: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def ordered(self):
        if self.normalized_end_ms <= self.normalized_start_ms:
            raise ValueError("Empty or reversed segment")
        if (self.normalized_start_frame is None) != (self.normalized_end_frame is None):
            raise ValueError("Both sample bounds are required")
        if self.normalized_start_frame is not None and (
            self.normalized_end_frame <= self.normalized_start_frame
            or self.normalized_start_frame // 16 != self.normalized_start_ms
            or self.normalized_end_frame // 16 != self.normalized_end_ms
        ):
            raise ValueError("Inconsistent segment sample bounds")
        return self


class FeedbackAudioSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_id: UUID
    take_number: int = Field(ge=1)
    segment_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    normalized_start_ms: int = Field(ge=0)
    normalized_end_ms: int = Field(ge=0)


def validate_timeline(mappings, duration_ms):
    rows = [AudioSegmentMapping.model_validate(row) for row in mappings]
    if rows and (
        rows[0].normalized_start_ms != 0
        or rows[-1].normalized_end_ms != duration_ms
        or len({row.segment_id for row in rows}) != len(rows)
        or len({(row.response_id, row.take_number) for row in rows}) != 1
        or any(
            a.normalized_end_ms != b.normalized_start_ms
            for a, b in zip(rows, rows[1:], strict=False)
        )
        or any(
            a.normalized_end_frame != b.normalized_start_frame
            for a, b in zip(rows, rows[1:], strict=False)
            if a.normalized_end_frame is not None and b.normalized_start_frame is not None
        )
    ):
        raise ValueError("Invalid normalized timeline")
    return tuple(rows)


def resolve_audio_span(mappings, start_ms, end_ms):
    if type(start_ms) is not int or type(end_ms) is not int or not 0 <= start_ms < end_ms:
        return None
    for row in mappings:
        if row.normalized_start_ms <= start_ms < end_ms <= row.normalized_end_ms:
            return FeedbackAudioSpan(
                response_id=row.response_id,
                take_number=row.take_number,
                segment_id=row.segment_id,
                start_ms=row.source_start_ms + start_ms - row.normalized_start_ms,
                end_ms=row.source_start_ms + end_ms - row.normalized_start_ms,
                normalized_start_ms=start_ms,
                normalized_end_ms=end_ms,
            )
    return None
