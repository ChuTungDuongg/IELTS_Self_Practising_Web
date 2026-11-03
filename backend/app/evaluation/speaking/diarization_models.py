"""Private machine proposals are deliberately not grading manifests."""

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.evaluation.speaking.models import Identifier
from app.evaluation.speaking.replay_models import Milliseconds, local_name
from app.schemas.speaking_grading import StrictDTO


class SpeakerTurn(StrictDTO):
    id: Identifier
    speaker_id: Identifier
    start_ms: Milliseconds
    end_ms: Milliseconds

    @model_validator(mode="after")
    def positive(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("Invalid speaker turn")
        return self


class DiarizationResult(StrictDTO):
    schema_version: Literal[1] = 1
    source: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    duration_ms: Annotated[int, Field(gt=0, le=1800000, strict=True)]
    cache_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    identity: dict
    regular: list[SpeakerTurn] = Field(default_factory=list, max_length=20000)
    exclusive: list[SpeakerTurn] = Field(default_factory=list, max_length=20000)
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    limitations: list[str] = Field(default_factory=lambda: ["MODEL_SPEAKER_IDENTITY_UNVERIFIED"])

    _source = field_validator("source")(local_name)

    @model_validator(mode="after")
    def timeline(self):
        for turns in (self.regular, self.exclusive):
            if len({t.id for t in turns}) != len(turns) or any(
                t.end_ms > self.duration_ms for t in turns
            ):
                raise ValueError("Invalid speaker timeline")
        ordered = sorted(self.exclusive, key=lambda t: t.start_ms)
        if any(a.end_ms > b.start_ms for a, b in zip(ordered, ordered[1:], strict=False)):
            raise ValueError("Exclusive timeline contains overlap")
        if {t.speaker_id for t in self.exclusive} - {t.speaker_id for t in self.regular}:
            raise ValueError("Exclusive timeline introduced an unknown speaker")
        return self


class ResponseProposal(SpeakerTurn):
    source: str
    suggested_role: Literal["candidate", "examiner", "unknown"] = "unknown"
    selected: bool = False
    turn_ids: list[Identifier] = Field(default_factory=list, max_length=20000)
    context_turn_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    part_number: Literal[1, 2, 3] | None = None
    part_verified: bool = False
    prompt_text: str = Field(default="", max_length=10000)
    cue_points: list[str] = Field(default_factory=list, max_length=20)
    prompt_verified: bool = False
    flags: list[str] = Field(default_factory=list, max_length=20)

    _source = field_validator("source")(local_name)


class ProposalBundle(StrictDTO):
    schema_version: Literal[1] = 1
    identity: str
    sources: dict[str, str]
    roles: dict
    segments: list[ResponseProposal] = Field(default_factory=list, max_length=20000)
    role_verification: Literal["pending", "confirmed"] = "pending"
    boundary_verification: Literal["pending"] = "pending"
    limitations: list[str] = Field(default_factory=list)
