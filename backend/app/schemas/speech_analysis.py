"""Private provider-neutral speech observations. Scores are never IELTS bands."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SpeechModel(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


class SpeechAnalysisIdentity(SpeechModel):
    provider: str
    adapter_version: str
    sdk_version: str | None = None
    model_version: str | None = None
    locale: str
    configuration_fingerprint: str
    configuration: dict[str, str | bool | int | float | None] = Field(default_factory=dict)


class SpeechAnalysisSource(SpeechModel):
    audio_fingerprint: str
    normalized_audio_fingerprint: str
    duration_ms: int = Field(ge=0)
    response_id: str | None = None
    take_number: int | None = Field(default=None, ge=1)
    segment_id: str | None = None


class SpeechSpan(SpeechModel):
    evidence_id: str
    start_ms: int | None = Field(default=None, ge=0, strict=True)
    end_ms: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def ordered(self):
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("Both timing bounds are required")
        if self.start_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("Invalid speech timing")
        return self


class SpeechWord(SpeechSpan):
    utterance_id: str
    text: str = Field(min_length=1, max_length=200)
    recognition_confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class SpeechUncertainty(SpeechSpan):
    reason: Literal["RECOGNITION_NO_MATCH", "RECOGNITION_INVALID"]


class SpeechUtterance(SpeechSpan):
    lexical_text: str
    display_text: str | None = None
    recognition_confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class SpeechObservation(SpeechSpan):
    response_id: str | None = None
    segment_id: str | None = None
    kind: Literal["pronunciation", "phoneme", "syllable", "prosody", "fluency"]
    target_id: str
    metric: str
    score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    provider_confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    label: str | None = None
    token: str | None = None
    source: str = "provider"
    certainty: Literal["provider_measurement", "provider_flag", "heuristic", "unknown"] = "unknown"
    limitations: list[str] = Field(default_factory=list)


class SpeechCapabilities(SpeechModel):
    continuous_recognition: bool = True
    unscripted: bool = True
    word_timing_observed: bool | None = None
    recognition_confidence_observed: bool | None = None
    pronunciation_observed: bool | None = None
    phonemes_observed: bool | None = None
    prosody_requested: bool = False
    prosody_supported: bool | None = None
    prosody_observed: bool | None = None
    acoustic_metadata_complete: bool | None = None


class SpeechCoverage(SpeechModel):
    audio_duration_ms: int = Field(ge=0)
    stream_completed: bool = False
    final_utterance_count: int = Field(default=0, ge=0)
    word_count: int = Field(default=0, ge=0)
    timed_word_count: int = Field(default=0, ge=0)
    confidence_word_count: int = Field(default=0, ge=0)
    recognized_span_ms: int = Field(default=0, ge=0)


class SpeechUsage(SpeechModel):
    attempted_calls: int = Field(default=0, ge=0)
    submitted_audio_ms: int = Field(default=0, ge=0)
    billed_duration_ms: int | None = Field(default=None, ge=0)
    billing_uncertain: bool = True
    automatic_retries: int = 0
    failed_calls: int = Field(default=0, ge=0)
    successful_calls: int = Field(default=0, ge=0)
    outcome: Literal["NOT_ATTEMPTED", "COMPLETED", "PARTIAL", "FAILED", "CANCELLED", "UNKNOWN"] = (
        "NOT_ATTEMPTED"
    )


class SpeechAnalysisResult(SpeechModel):
    schema_version: Literal["speech-analysis.v1"] = "speech-analysis.v1"
    provider: SpeechAnalysisIdentity
    source: SpeechAnalysisSource
    status: Literal["COMPLETE", "PARTIAL", "FAILED", "CANCELLED"]
    lexical_transcript: str = ""
    display_transcript: str | None = None
    utterances: list[SpeechUtterance] = Field(default_factory=list, max_length=10000)
    words: list[SpeechWord] = Field(default_factory=list, max_length=30000)
    observations: list[SpeechObservation] = Field(default_factory=list, max_length=200000)
    uncertain_regions: list[SpeechUncertainty] = Field(default_factory=list, max_length=10000)
    coverage: SpeechCoverage
    capabilities: SpeechCapabilities
    limitations: list[str] = Field(default_factory=list)
    usage: SpeechUsage = Field(default_factory=SpeechUsage)
    error_code: str | None = None
    provider_reason_code: (
        Literal[
            "SDK_TOO_MANY_REQUESTS",
            "HTTP_429",
            "PROVIDER_RATE_LIMIT",
            "PROVIDER_CONCURRENCY_LIMIT",
            "PROVIDER_QUOTA_EXHAUSTED",
        ]
        | None
    ) = None
    latency_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def source_bounds(self):
        spans = [*self.utterances, *self.words, *self.observations, *self.uncertain_regions]
        if any(s.end_ms is not None and s.end_ms > self.source.duration_ms for s in spans):
            raise ValueError("Speech evidence exceeds source duration")
        identifiers = [s.evidence_id for s in spans]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Duplicate evidence identity")
        return self
