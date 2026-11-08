"""Bounded owner commands; ASR evidence and confidence are never client-writable."""

import math
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.speaking_grading import StrictDTO

QuestionProvider = Literal["azure_stt", "faster_whisper_local", "faster_whisper_modal"]
QUESTION_PROTOCOL = "speaking-question-assistant-v1"


class QuestionJobCreate(StrictDTO):
    submission_key: UUID
    review_revision: int = Field(ge=1)
    examiner_speaker_id: str = Field(min_length=1, max_length=100)
    examiner_confirmed: Literal[True]
    provider: QuestionProvider = "azure_stt"
    window_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    max_window_ms: int = Field(default=60000, ge=1000, le=120000)
    max_windows: int = Field(default=100, ge=1, le=100)
    max_provider_audio_seconds: float = Field(default=600, gt=0, le=1800, allow_inf_nan=False)
    max_physical_requests: int = Field(default=100, ge=1, le=100)

    @model_validator(mode="after")
    def unique(self):
        if self.window_ids and len(set(self.window_ids)) != len(self.window_ids):
            raise ValueError("Duplicate examiner windows")
        return self


class QuestionConsent(StrictDTO):
    provider_audio: Literal[True]
    modal_gpu: bool = False
    estimates_usd: dict[str, float]
    max_estimated_cost_usd: float = Field(gt=0, le=1000, allow_inf_nan=False)

    @model_validator(mode="after")
    def budget(self):
        if (
            not self.estimates_usd
            or any(not math.isfinite(v) or v < 0 for v in self.estimates_usd.values())
            or sum(self.estimates_usd.values()) > self.max_estimated_cost_usd
        ):
            raise ValueError("Finite provider estimates within the admission ceiling required")
        return self


class QuestionStart(StrictDTO):
    preflight_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    consent: QuestionConsent


class QuestionReconcile(QuestionStart):
    request_id: UUID
    reason: str = Field(min_length=10, max_length=1000)


class QuestionDecision(StrictDTO):
    proposal_id: str = Field(min_length=1, max_length=100)
    action: Literal["ACCEPT", "REJECT"]
    text: str | None = Field(default=None, min_length=1, max_length=10000)
    candidate_segment_id: str | None = Field(default=None, max_length=100)
    part_number: Literal[1, 2, 3] | None = None
    ambiguity_reviewed: bool = False


class QuestionDecisions(StrictDTO):
    expected_review_revision: int = Field(ge=1)
    expected_decision_count: int = Field(ge=0)
    independently_reviewed: Literal[True]
    batch: bool = False
    decisions: list[QuestionDecision] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len({d.proposal_id for d in self.decisions}) != len(self.decisions):
            raise ValueError("Duplicate proposal decisions")
        return self


class QuestionProposal(StrictDTO):
    id: str
    source_review_revision: int
    source_sha256: str
    draft_fingerprint: str
    examiner_speaker_id: str
    window_id: str
    start_ms: int
    end_ms: int
    recognized_text: str
    provider_identity: dict
    candidate_segment_id: str | None
    part_number: Literal[1, 2, 3]
    question_type: Literal["question", "instruction", "acknowledgement", "clarification", "unclear"]
    ambiguity_flags: list[str]
    human_verification_status: Literal["PENDING"] = "PENDING"


class QuestionRequestDTO(StrictDTO):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    window_id: str
    attempt: int
    status: str
    billing_state: str
    usage: dict | None
    error_code: str | None
    reused_from: UUID | None
    reconciliation: dict | None
    created_at: datetime
    finished_at: datetime | None


class QuestionJobDTO(StrictDTO):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    sample_id: UUID
    review_revision: int
    source_sha256: str
    draft_fingerprint: str
    model_fingerprint: str
    examiner_speaker_id: str
    configuration: dict
    fingerprint: str
    windows: list[dict]
    exclusions: list[dict]
    status: str
    error_code: str | None
    proposals: list[QuestionProposal]
    decisions: list[dict]
    requests: list[QuestionRequestDTO] = Field(default_factory=list)
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class QuestionPreflight(StrictDTO):
    preflight_fingerprint: str
    can_start: bool
    blockers: list[str]
    windows: list[dict]
    exclusions: list[dict]
    requests: dict[str, int]
    provider_audio_seconds: float
    limits: dict
    warnings: list[str]
