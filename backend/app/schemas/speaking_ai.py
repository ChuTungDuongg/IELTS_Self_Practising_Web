"""Private transcription and acoustic evidence contracts; no scoring fields."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


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


class AudioQualityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(default="energy-quality-v1", min_length=1, max_length=80)
    minimum_duration_seconds: float = Field(default=1, gt=0, le=30, allow_inf_nan=False)
    minimum_speech_seconds: float = Field(default=0.5, gt=0, le=30, allow_inf_nan=False)
    minimum_rms: float = Field(default=0.005, gt=0, le=0.2, allow_inf_nan=False)
    silence_floor_rms: float = Field(default=0.00001, ge=0, le=0.01, allow_inf_nan=False)
    activity_rms: float = Field(default=0.01, gt=0, le=0.3, allow_inf_nan=False)
    clipping_amplitude: float = Field(default=0.98, ge=0.8, le=1, allow_inf_nan=False)
    maximum_clipping_ratio: float = Field(default=0.1, gt=0, le=1, allow_inf_nan=False)
    noise_zero_crossing_ratio: float = Field(default=0.35, gt=0, le=1, allow_inf_nan=False)
    maximum_background_ratio: float = Field(default=0.85, gt=0, le=1, allow_inf_nan=False)


class AudioMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_seconds: float = Field(ge=0, le=1800, allow_inf_nan=False)
    speech_seconds: float = Field(ge=0, le=1800, allow_inf_nan=False)
    rms: float = Field(ge=0, le=1, allow_inf_nan=False)
    clipping_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    background_proxy_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    segment_count: int = Field(default=1, ge=1, le=1000)
    recovery_gaps_known: bool = True
    activity_method: Literal["frame-energy-proxy-v1"] = "frame-energy-proxy-v1"

    @computed_field
    @property
    def silence_seconds(self) -> float:
        return max(0, self.duration_seconds - self.speech_seconds)

    @computed_field
    @property
    def speech_ratio(self) -> float:
        return self.speech_seconds / self.duration_seconds if self.duration_seconds else 0

    @computed_field
    @property
    def silence_ratio(self) -> float:
        return self.silence_seconds / self.duration_seconds if self.duration_seconds else 0


QualityState = Literal[
    "AUDIO_OK",
    "NO_SPEECH",
    "TOO_SHORT",
    "AUDIO_CORRUPT",
    "VERY_LOW_SIGNAL",
    "SEVERE_CLIPPING",
    "BACKGROUND_DOMINANT",
    "ASR_UNUSABLE",
]


class AudioQualityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: QualityState
    assessable: bool
    cache_key: str
    source_audio_fingerprint: str
    config: AudioQualityConfig
    metrics: AudioMetrics | None = None
    asr_usable: bool | None = None
