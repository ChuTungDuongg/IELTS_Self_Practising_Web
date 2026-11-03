"""Unlabelled replay contracts; the labelled benchmark manifest remains unchanged."""

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.evaluation.speaking.manifest import BenchmarkInputError, _text, _unique
from app.evaluation.speaking.models import Identifier, band
from app.schemas.speaking_grading import StrictDTO

Milliseconds = Annotated[int, Field(ge=0, le=3_600_000, strict=True)]


def local_name(value):
    if value is not None and (
        ":" in value
        or "\\" in value
        or "\0" in value
        or Path(value).is_absolute()
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("Local relative audio name required")
    return value


class ReplaySegment(StrictDTO):
    id: Identifier
    source: str | None = Field(default=None, max_length=1000)
    part_number: Literal[1, 2, 3]
    start_ms: Milliseconds | None = None
    end_ms: Milliseconds | None = None
    prompt_type: Literal["SHORT_ANSWER", "LONG_TURN", "FOLLOW_UP"]
    prompt_text: str = Field(default="", max_length=10000)
    cue_points: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(
        default_factory=list, max_length=20
    )
    speaker_role: Literal["candidate", "examiner", "preparation", "unknown"] = "unknown"
    speaker_id: Identifier | None = None

    _source = field_validator("source")(local_name)

    @model_validator(mode="after")
    def window(self):
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("Both window bounds required")
        if self.end_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("Empty or reversed window")
        if (self.part_number != 2 and self.prompt_type == "LONG_TURN") or (
            self.part_number == 1 and self.prompt_type != "SHORT_ANSWER"
        ):
            raise ValueError("Prompt does not belong to this Part")
        return self


class ReplayManifest(StrictDTO):
    schema_version: Literal[1] = 1
    source: str | None = Field(default=None, max_length=1000)
    candidate_id: Identifier = "candidate-1"
    candidate_only_verified: bool = False
    segments: list[ReplaySegment] = Field(default_factory=list, max_length=100)

    _source = field_validator("source")(local_name)

    @model_validator(mode="after")
    def boundaries(self):
        identifiers, windows = set(), {}
        for segment in self.segments:
            source = segment.source or self.source
            if source is None or segment.id in identifiers:
                raise ValueError("Source and unique segment IDs required")
            identifiers.add(segment.id)
            if segment.speaker_role == "candidate" and segment.speaker_id not in (
                None,
                self.candidate_id,
            ):
                raise ValueError("A replay attempt must belong to one candidate")
            if segment.start_ms is not None:
                windows.setdefault(source, []).append((segment.start_ms, segment.end_ms))
        for spans in windows.values():
            ordered = sorted(spans)
            if any(
                end > following
                for (_, end), (following, _) in zip(ordered, ordered[1:], strict=False)
            ):
                raise ValueError("Overlapping source windows")
        return self

    def grading_limitations(self):
        reasons = []
        candidates = [s for s in self.segments if s.speaker_role == "candidate"]
        if not self.candidate_only_verified:
            reasons.append("SPEAKER_NOT_VERIFIED")
        if not candidates or any(s.start_ms is None for s in candidates):
            reasons.append("UNSEGMENTED_AUDIO")
        if {s.part_number for s in candidates} != {1, 2, 3} or not any(
            s.part_number == 2 and s.prompt_type == "LONG_TURN" for s in candidates
        ):
            reasons.append("FULL_ATTEMPT_PARTS_REQUIRED")
        if any(not s.prompt_text.strip() for s in candidates):
            reasons.append("PROMPT_CONTEXT_REQUIRED")
        return reasons


class ReplayBands(StrictDTO):
    fc: float | None = None
    lr: float | None = None
    gra: float | None = None
    pr: float | None = None
    overall: float | None = None

    @field_validator("fc", "lr", "gra", "pr", "overall", mode="before")
    @classmethod
    def published_band(cls, value):
        return None if value is None else band(value)


class LabelProvenance(StrictDTO):
    kind: Literal["human_examiner", "published_human_assessment", "unverified", "ai_prediction"]
    reference: str = Field(min_length=1, max_length=2000)
    verified: bool = False

    @model_validator(mode="after")
    def human_only(self):
        if self.verified and self.kind not in {"human_examiner", "published_human_assessment"}:
            raise ValueError("Only independently human labels can be verified ground truth")
        return self


class ReplayHumanLabels(StrictDTO):
    schema_version: Literal[1] = 1
    bands: ReplayBands
    provenance: LabelProvenance


def read_json(path, model):
    try:
        return model.model_validate(
            json.loads(_text(path).lstrip("\ufeff"), object_pairs_hook=_unique)
        )
    except (ValueError, RecursionError):
        raise BenchmarkInputError("REPLAY_CONFIGURATION_INVALID") from None
