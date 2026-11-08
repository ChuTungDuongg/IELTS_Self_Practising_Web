"""Owner commands and explicitly narrow blind-review contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.evaluation.speaking.replay_models import ReplayBands
from app.schemas.speaking_grading import StrictDTO


class RaterCreate(StrictDTO):
    kind: Literal["INTERNAL", "EXTERNAL"]
    display_name: str = Field(min_length=1, max_length=200)
    user_id: UUID | None = None
    external_key: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def identity(self):
        if (
            not self.display_name.strip()
            or (self.kind == "INTERNAL" and (self.user_id is None or self.external_key is not None))
            or (
                self.kind == "EXTERNAL"
                and (self.user_id is not None or not (self.external_key or "").strip())
            )
        ):
            raise ValueError("An internal user or stable external examiner identity is required")
        return self


class RaterDTO(RaterCreate):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    created_at: datetime


class AssignmentCreate(StrictDTO):
    rater_id: UUID
    review_revision: int = Field(ge=1)
    permitted_original_audio: Literal[True] = True


class AssignmentRevoke(StrictDTO):
    expected_revision: int = Field(ge=1)


class AssignmentDTO(StrictDTO):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    sample_id: UUID
    rater_id: UUID
    review_revision: int
    source_sha256: str
    manifest_fingerprint: str
    permitted_original_audio: bool
    revision: int
    revoked_at: datetime | None
    created_at: datetime


class CriterionComments(StrictDTO):
    fc: str = Field(default="", max_length=3000)
    lr: str = Field(default="", max_length=3000)
    gra: str = Field(default="", max_length=3000)
    pr: str = Field(default="", max_length=3000)
    overall: str = Field(default="", max_length=3000)


class AssessmentSubmit(StrictDTO):
    expected_revision: int = Field(ge=0)
    bands: ReplayBands
    comments: CriterionComments = Field(default_factory=CriterionComments)
    independently_performed: bool = False
    provenance: Literal["external_verified_report", "external_unverified"] = "external_unverified"
    source_reference: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def report_reference(self):
        if self.provenance == "external_verified_report" and not self.source_reference.strip():
            raise ValueError("A verifiable external report requires a source reference")
        return self


class AssessmentDTO(StrictDTO):
    id: UUID
    assignment_id: UUID
    sample_id: UUID
    rater_id: UUID
    review_revision: int
    source_sha256: str
    manifest_fingerprint: str
    revision: int
    status: Literal["SUBMITTED"]
    bands: ReplayBands
    comments: CriterionComments
    independently_performed: bool
    provenance: str
    source_reference: str
    eligible: bool
    authored_by: UUID
    submitted_at: datetime


class ExternalAssessmentSubmit(AssessmentSubmit):
    assignment_id: UUID


class AdjudicationCreate(StrictDTO):
    review_revision: int = Field(ge=1)
    expected_revision: int = Field(ge=0)
    assessment_ids: list[UUID] = Field(min_length=1, max_length=100)
    bands: ReplayBands
    rationale: str = Field(min_length=1, max_length=10000)
    policy_version: Literal["human-adjudication-v1"] = "human-adjudication-v1"

    @model_validator(mode="after")
    def decision(self):
        if len(set(self.assessment_ids)) != len(self.assessment_ids) or not self.rationale.strip():
            raise ValueError("Unique assessment IDs and an explicit human rationale are required")
        return self


class AdjudicationDTO(StrictDTO):
    id: UUID
    sample_id: UUID
    review_revision: int
    source_sha256: str
    manifest_fingerprint: str
    revision: int
    assessment_refs: list[dict]
    bands: ReplayBands
    rationale: str
    policy_version: str
    provenance: str
    adjudicator_id: UUID
    adjudicated_at: datetime


class LabelSelection(StrictDTO):
    kind: Literal["LEGACY", "INDEPENDENT", "ADJUDICATED"]
    id: UUID | None = None
    revision: int | None = Field(default=None, ge=1)
    rater_id: UUID | None = None


class BlindQuestion(StrictDTO):
    id: str
    part_number: Literal[1, 2, 3]
    prompt_type: Literal["SHORT_ANSWER", "LONG_TURN", "FOLLOW_UP"]
    prompt_text: str
    cue_points: list[str]
    start_ms: int | None
    end_ms: int | None


class BlindAssessmentDTO(StrictDTO):
    id: UUID
    sample_id: UUID
    review_revision: int
    source_sha256: str
    manifest_fingerprint: str
    revision: int
    duration_ms: int
    audio_url: str
    questions: list[BlindQuestion]
    assessments: list[AssessmentDTO]
    created_at: datetime


class RaterPage(StrictDTO):
    items: list[RaterDTO]
    total: int
    offset: int
    limit: int


class AssignmentPage(StrictDTO):
    items: list[AssignmentDTO]
    total: int
    offset: int
    limit: int


class AssessmentPage(StrictDTO):
    items: list[AssessmentDTO]
    total: int
    offset: int
    limit: int


class AdjudicationPage(StrictDTO):
    items: list[AdjudicationDTO]
    total: int
    offset: int
    limit: int
