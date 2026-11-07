"""Bounded private admin contracts; never expose storage keys or runtime paths."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.evaluation.speaking.diarization_models import DiarizationResult
from app.evaluation.speaking.replay_models import ReplayBands, ReplayManifest
from app.schemas.speaking_grading import StrictDTO


class SampleMetadata(StrictDTO):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[\w .-]+$")
    candidate_id: str = Field(default="", max_length=120)
    split: Literal["DEV", "HOLDOUT"] = "DEV"
    source_note: str = Field(min_length=1, max_length=2000)
    rights_confirmed: Literal[True]

    @field_validator("code", "source_note")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("Non-blank sample code and source note required")
        return value


class Mutation(StrictDTO):
    expected_revision: int = Field(ge=0)


class SamplePatch(SampleMetadata, Mutation):
    pass


class SampleDTO(SampleMetadata):
    id: UUID
    source_sha256: str
    mime_type: str
    byte_size: int
    duration_ms: int
    status: Literal["DRAFT", "PROCESSING", "REVIEW", "APPROVED"]
    revision: int
    review_revision: int
    label_revision: int
    label_status: Literal["UNLABELLED", "UNVERIFIED", "HUMAN_VERIFIED"]
    approved_fingerprint: str | None
    created_at: datetime
    updated_at: datetime


class SamplePage(StrictDTO):
    items: list[SampleDTO]
    total: int
    offset: int
    limit: int


class JobDTO(StrictDTO):
    id: UUID
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
    stage: str
    progress: int
    attempts: int
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ReviewSegment(StrictDTO):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    speaker_id: str = Field(min_length=1, max_length=100)
    start_ms: int = Field(ge=0, le=1800000, strict=True)
    end_ms: int = Field(gt=0, le=1800000, strict=True)
    included: bool = True
    prompt_text: str = Field(default="", max_length=10000)
    cue_points: list[str] = Field(default_factory=list, max_length=20)
    prompt_verified: bool = False
    long_turn: bool = False
    silence_reviewed: bool = False

    @model_validator(mode="after")
    def bounds(self):
        if self.end_ms <= self.start_ms or any(
            not p.strip() or len(p) > 1000 for p in self.cue_points
        ):
            raise ValueError("Invalid response window or cue points")
        return self


class ReviewDraft(StrictDTO):
    schema_version: Literal[1] = 1
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    roles: dict[str, Literal["candidate", "examiner", "other", "unknown"]] = Field(
        default_factory=dict, max_length=20
    )
    candidate_speaker_id: str | None = Field(default=None, max_length=100)
    candidate_confirmed: bool = False
    part2_start_ms: int | None = Field(default=None, gt=0, le=1800000)
    part3_start_ms: int | None = Field(default=None, gt=0, le=1800000)
    boundaries_verified: bool = False
    segments: list[ReviewSegment] = Field(default_factory=list, max_length=100)


class ReviewPatch(Mutation):
    draft: ReviewDraft


class ReviewDTO(StrictDTO):
    revision: int
    draft: ReviewDraft
    diarization: DiarizationResult
    approved_at: datetime | None
    manifest: ReplayManifest | None
    approval_errors: list[str]
    role_suggestions: dict[str, Literal["candidate", "examiner", "unknown"]]


class HumanLabels(StrictDTO):
    bands: ReplayBands = Field(default_factory=ReplayBands)
    provenance: Literal["human_examiner", "published_human_assessment", "unverified"] = "unverified"
    reference: str = Field(default="", max_length=2000)
    verified: bool = False
    examiner: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def human_only(self):
        if self.verified and (self.provenance == "unverified" or not self.reference.strip()):
            raise ValueError("Independent human provenance and a source reference are required")
        return self


class LabelsPut(HumanLabels, Mutation):
    pass


class LabelsDTO(HumanLabels):
    revision: int = 0


class LabAvailability(StrictDTO):
    execution: Literal["local", "remote", "disabled"]
    can_queue: bool
    reason: str | None
    max_bytes: int
    max_duration_ms: int
