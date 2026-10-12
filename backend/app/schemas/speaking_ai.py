"""Private transcription and acoustic evidence contracts; no scoring fields."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WordTiming(BaseModel):
    model_config = ConfigDict(extra="forbid")
    word: str = Field(min_length=1, max_length=200)
    start: float = Field(ge=0, le=3600, allow_inf_nan=False)
    end: float = Field(ge=0, le=3600, allow_inf_nan=False)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("Invalid word timing")
        return self


class ASRResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=60000)
    words: list[WordTiming] = Field(default_factory=list, max_length=10000)
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    language: str | None = Field(default=None, max_length=12)
    mean_confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_timings(self):
        if not self.text.strip() or any(
            b.start < a.end for a, b in zip(self.words, self.words[1:], strict=False)
        ):
            raise ValueError("Invalid transcript or word order")
        return self


class TranscriptResponse(BaseModel):
    response_id: UUID
    status: Literal["WAITING", "PROCESSING", "READY", "FAILED"]
    verbatim: str | None = None
    clean: str | None = None
    words: list[WordTiming] = Field(default_factory=list)
    error_code: str | None = None
    source_audio_fingerprint: str


class TranscriptRunData(BaseModel):
    run_id: UUID
    attempt_id: UUID
    status: Literal["PENDING", "RUNNING", "COMPLETED", "PARTIAL", "FAILED"]
    cache_key: str
    last_sequence: int
    responses: list[TranscriptResponse]
    created_at: datetime


class TranscriptCreated(BaseModel):
    run_id: UUID
    cache_hit: bool
    existing_active: bool


class TranscriptEventData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sequence: int
    event_type: str
    payload: dict[str, str]


class TranscriptRunList(BaseModel):
    run: TranscriptRunData | None
