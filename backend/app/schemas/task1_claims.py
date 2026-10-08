from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.domains.scoring.task1_facts import MAX_DERIVED_FACTS, DerivedFact, FactKind, FactNumber
from app.schemas.task1_visual import (
    GroundingConfidence,
    Location,
    Text,
    VisualModel,
    VisualReference,
)

SourceID = Annotated[str, Field(pattern=r"^P[1-9][0-9]*S[1-9][0-9]*$", max_length=32)]
ClaimKind = Literal[
    "numeric_value",
    "comparison",
    "ranking",
    "trend",
    "change",
    "extrema",
    "overview",
    "process_stage",
    "process_order",
    "map_change",
    "spatial_relation",
    "system_relation",
    "other_visual_claim",
]
Verdict = Literal["SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE", "NOT_APPLICABLE"]


class NumericCheck(VisualModel):
    type: Literal["numeric"]
    component_id: str | None = Field(default=None, max_length=40)
    subject: Text
    fact: FactKind
    category: str | None = Field(default=None, max_length=120)
    end_category: str | None = Field(default=None, max_length=120)
    value: FactNumber | None = None
    direction: Literal["increase", "decrease", "stable"] | None = None


class ComparisonCheck(VisualModel):
    type: Literal["comparison"]
    component_id: str | None = Field(default=None, max_length=40)
    subject: Text
    other: Text
    category: Text
    operator: Literal["gt", "lt", "eq"]


class RelationCheck(VisualModel):
    type: Literal["relation"]
    subject: Text
    other: Text | None = None
    relation: Literal[
        "stage",
        "before",
        "connected",
        "addition",
        "removal",
        "replacement",
        "relocation",
        "expansion",
        "unchanged",
        "location",
    ]
    from_state: str | None = Field(default=None, max_length=120)
    to_state: str | None = Field(default=None, max_length=120)
    location: Location | None = None


ClaimCheck = Annotated[NumericCheck | ComparisonCheck | RelationCheck, Field(discriminator="type")]


class ExtractedClaim(VisualModel):
    claim_id: str = Field(min_length=1, max_length=40)
    source_ids: list[SourceID] = Field(min_length=1, max_length=3)
    kind: ClaimKind
    claim: str = Field(min_length=1, max_length=400)
    check: ClaimCheck | None = None


class ExtractedClaims(VisualModel):
    claims: list[ExtractedClaim] = Field(max_length=20)


class VerifiedClaim(VisualModel):
    claim_id: str = Field(max_length=40)
    source_ids: list[SourceID] = Field(min_length=1, max_length=3)
    quote: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=12000)]
    claim: str = Field(max_length=400)
    verdict: Verdict
    explanation: str = Field(min_length=1, max_length=400)
    evidence: list[str] = Field(default_factory=list, max_length=8)


class SemanticVerdict(VisualModel):
    claim_id: str = Field(max_length=40)
    verdict: Verdict
    explanation: str = Field(min_length=1)


class SemanticVerification(VisualModel):
    items: list[SemanticVerdict] = Field(max_length=20)


class Task1Analysis(VisualModel):
    visual_family: Literal["chart_table", "process", "map", "system", "other"]
    confidence: GroundingConfidence = GroundingConfidence.UNUSABLE
    reference: VisualReference | None = None
    derived_facts: list[DerivedFact] = Field(default_factory=list, max_length=MAX_DERIVED_FACTS)
    claims: list[VerifiedClaim] = Field(default_factory=list, max_length=20)
    warnings: list[
        Literal[
            "VISUAL_LOW_CONFIDENCE",
            "VISUAL_GROUNDING_FAILED",
            "CLAIM_EXTRACTION_FAILED",
            "CLAIM_VERIFICATION_FAILED",
        ]
    ] = Field(default_factory=list, max_length=4)
