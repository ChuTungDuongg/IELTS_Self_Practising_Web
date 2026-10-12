"""Speaking scoring DTOs, independent of transcript and Writing contracts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.speaking_ai import (
    FluencyEvidence,
    QualityState,
    SpeakingFeatureBundle,
    WordTiming,
)

SpeakingCriterion = Literal["fc", "lr", "gra", "pr"]
CRITERIA: tuple[SpeakingCriterion, ...] = ("fc", "lr", "gra", "pr")


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


class CriterionBandScore(StrictDTO):
    score: float = Field(ge=0, le=9, multiple_of=0.5, allow_inf_nan=False)

    @field_validator("score", mode="before")
    @classmethod
    def numeric_only(cls, value):
        if type(value) not in (int, float):
            raise ValueError("A numeric half band is required")
        return value


ShortFeedback = Annotated[str, Field(min_length=1, max_length=300)]


class CriterionFeedback(StrictDTO):
    feedback: str = Field(min_length=1, max_length=1200)
    strengths: list[ShortFeedback] = Field(max_length=6)
    improvements: list[ShortFeedback] = Field(max_length=6)

    @field_validator("feedback")
    @classmethod
    def nonempty_feedback(cls, value):
        if not value.strip():
            raise ValueError("Empty feedback")
        return value


class SpeakingResponseEvidence(StrictDTO):
    response_id: UUID
    prompt_id: UUID
    part_number: Literal[1, 2, 3]
    prompt_type: Literal["SHORT_ANSWER", "LONG_TURN", "FOLLOW_UP"]
    prompt_text: str = Field(min_length=1, max_length=10000)
    cue_points: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(
        default_factory=list, max_length=20
    )
    verbatim: str = Field(min_length=1, max_length=60000)
    clean: str = Field(min_length=1, max_length=60000)
    words: list[WordTiming] = Field(default_factory=list, max_length=10000)
    features: SpeakingFeatureBundle | None = None

    @model_validator(mode="after")
    def meaningful_consistent_evidence(self):
        if not self.verbatim.strip() or not self.clean.strip() or not self.prompt_text.strip():
            raise ValueError("Empty response evidence")
        if any(b.start < a.end for a, b in zip(self.words, self.words[1:], strict=False)):
            raise ValueError("Unordered response evidence")
        if self.features:
            feature = self.features
            if not (
                feature.source_audio_fingerprint
                == feature.quality.source_audio_fingerprint
                == feature.pronunciation.source_audio_fingerprint
            ):
                raise ValueError("Inconsistent audio provenance")
        return self


class SpeakingAttemptEvidence(StrictDTO):
    responses: list[SpeakingResponseEvidence] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def bounded_unique_responses(self):
        if len({row.response_id for row in self.responses}) != len(self.responses):
            raise ValueError("Duplicate response evidence")
        if sum(len(row.verbatim) + len(row.clean) for row in self.responses) > 300000:
            raise ValueError("Attempt transcript budget exceeded")
        if sum(len(row.words) for row in self.responses) > 30000:
            raise ValueError("Attempt timing budget exceeded")
        return self


class GradingPronunciationEvidence(StrictDTO):
    """Allowlisted acoustic/alignment facts; never storage paths or provider text."""

    status: Literal["AVAILABLE", "LOW_EVIDENCE", "UNAVAILABLE"]
    alignment_word_count: int = Field(ge=0, le=30000)
    alignment_coverage: float = Field(ge=0, le=1, allow_inf_nan=False)
    confidence_coverage: float = Field(ge=0, le=1, allow_inf_nan=False)
    low_confidence_count: int = Field(ge=0, le=10000)
    mean_alignment_confidence: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    word_duration_cv: float | None = Field(ge=0, allow_inf_nan=False)
    inter_word_gap_mean_seconds: float | None = Field(ge=0, allow_inf_nan=False)
    rms: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    energy_cv: float | None = Field(ge=0, allow_inf_nan=False)
    word_energy_cv: float | None = Field(ge=0, allow_inf_nan=False)
    acoustic_frame_count: int = Field(ge=0, le=256)
    voiced_pitch_frames: int = Field(ge=0, le=256)
    pitch_mean_hz: float | None = Field(ge=80, le=400, allow_inf_nan=False)
    pitch_range_hz: float | None = Field(ge=0, le=320, allow_inf_nan=False)
    intelligibility_proxy: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    limitations: list[str] = Field(max_length=20)


class CriterionResponseEvidence(StrictDTO):
    response_id: UUID
    prompt_id: UUID
    part_number: Literal[1, 2, 3]
    prompt_type: Literal["SHORT_ANSWER", "LONG_TURN", "FOLLOW_UP"]
    prompt_text: str = Field(min_length=1, max_length=10000)
    cue_points: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(max_length=20)
    verbatim: str = Field(min_length=1, max_length=60000)
    clean: str = Field(min_length=1, max_length=60000)
    words: list[WordTiming] = Field(max_length=10000)
    utterances: list[Annotated[str, Field(min_length=1, max_length=60000)]] | None = Field(
        default=None, max_length=200
    )
    quality_state: QualityState | None = None
    fluency: FluencyEvidence | None = None
    pronunciation: GradingPronunciationEvidence | None = None


class CriterionEvidence(StrictDTO):
    criterion: SpeakingCriterion
    scope: Literal["WHOLE_ATTEMPT"] = "WHOLE_ATTEMPT"
    responses: list[CriterionResponseEvidence] = Field(min_length=1, max_length=100)


class CriterionResult(StrictDTO):
    criterion: SpeakingCriterion
    status: Literal["SCORE_READY", "COMPLETED", "FEEDBACK_FAILED", "FAILED", "UNAVAILABLE"]
    score: float | None = None
    feedback: CriterionFeedback | None = None
    feedback_status: Literal["PENDING", "READY", "FAILED", "UNAVAILABLE"] = "PENDING"
    error_code: (
        Literal[
            "SPEAKING_AI_PROVIDER_FAILED",
            "SPEAKING_AI_INVALID_SCORE",
            "SPEAKING_AI_FEEDBACK_FAILED",
            "SPEAKING_PR_UNASSESSABLE",
            "SPEAKING_AUDIO_UNASSESSABLE",
        ]
        | None
    ) = None
    evidence: CriterionEvidence
    advisory: Literal[True] = True

    @field_validator("score", mode="before")
    @classmethod
    def validated_numeric_score(cls, value):
        return CriterionBandScore(score=value).score if value is not None else None

    @model_validator(mode="after")
    def consistent_score(self):
        if self.criterion != self.evidence.criterion:
            raise ValueError("Criterion evidence mismatch")
        if self.score is not None:
            CriterionBandScore(score=self.score)
        if (self.status in {"FAILED", "UNAVAILABLE"}) != (self.score is None):
            raise ValueError("Inconsistent criterion score state")
        return self
