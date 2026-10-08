from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.writing_anchors import LanguageTrait

Preference = Literal["RESPONSE_1_BETTER", "RESPONSE_2_BETTER", "COMPARABLE"]
NormalizedPreference = Literal["TARGET_BETTER", "ANCHOR_BETTER", "COMPARABLE"]
FallbackReason = Literal[
    "NO_ANCHORS",
    "INSUFFICIENT_CONTIGUOUS_COVERAGE",
    "OUT_OF_RANGE",
    "POSITION_CONFLICT",
    "BUDGET_EXHAUSTED",
    "PAIRWISE_PROVIDER_FAILURE",
]


class PairwisePreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preference: Preference


class ComparisonResponse(BaseModel):
    """The entire permitted response boundary: no scores, identity or provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    task_prompt: str = Field(repr=False)
    response_text: str = Field(repr=False)


class TreeNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    band: int
    anchor_id: UUID
    forward: NormalizedPreference | None = None
    reverse: NormalizedPreference | None = None
    result: NormalizedPreference | None = None


class TreeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: Decimal | None = None
    fallback_reason: FallbackReason | None = None
    nodes: list[TreeNode] = Field(default_factory=list)

    @property
    def pairwise_calls(self) -> int:
        return len(self.nodes) * 2


__all__ = [
    "ComparisonResponse",
    "FallbackReason",
    "LanguageTrait",
    "PairwisePreference",
    "TreeNode",
    "TreeResult",
]
