from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.exceptions import AppError
from app.domains.scoring.direct_writing_prompts import DIRECT_PROMPT_VERSION
from app.domains.scoring.tacs_prompts import PAIRWISE_PROMPT_VERSION
from app.schemas.writing_anchors import AnchorSnapshot
from app.services.task1_direct import Task1DirectScoringService
from app.services.task1_input import TASK1_PROMPT_VERSION, TASK1_VISUAL_CONTRACT_VERSION
from app.services.task1_tacs import (
    FEEDBACK_PROMPT_VERSION,
    HYBRID_PROMPT_VERSION,
    Task1TACSScoringService,
)
from app.services.task1_writing import Task1WritingScoringService


class Task1ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    architecture: Literal["anchor_pairwise", "direct", "mts"]
    prompt_version: str = Field(min_length=1, max_length=80)
    direct_prompt_version: str = DIRECT_PROMPT_VERSION
    pairwise_prompt_version: str = PAIRWISE_PROMPT_VERSION
    feedback_prompt_version: str = FEEDBACK_PROMPT_VERSION
    visual_contract_version: str = TASK1_VISUAL_CONTRACT_VERSION
    anchor_set_id: UUID | None = None
    anchor_set_version: int | None = Field(default=None, ge=1)
    max_tree_nodes: int = Field(default=2, ge=1, le=3)

    @model_validator(mode="after")
    def coherent_pin(self):
        if (self.anchor_set_id is None) != (self.anchor_set_version is None):
            raise ValueError("Snapshot identity requires both ID and version")
        return self

    @classmethod
    def pin(cls, architecture, snapshot: AnchorSnapshot, max_nodes):
        return cls(
            architecture=architecture,
            prompt_version={
                "mts": TASK1_PROMPT_VERSION,
                "direct": DIRECT_PROMPT_VERSION,
                "anchor_pairwise": HYBRID_PROMPT_VERSION,
            }[architecture],
            anchor_set_id=snapshot.id if architecture == "anchor_pairwise" else None,
            anchor_set_version=snapshot.version if architecture == "anchor_pairwise" else None,
            max_tree_nodes=max_nodes,
        )


def create_task1_scorer(
    execution,
    snapshot,
    provider,
    chart_derenderer=None,
    chart_timeout=90,
    *,
    target_fingerprint,
    **kwargs,
):
    if execution is not None:
        supported = {
            "prompt_version": {
                "mts": TASK1_PROMPT_VERSION,
                "direct": DIRECT_PROMPT_VERSION,
                "anchor_pairwise": HYBRID_PROMPT_VERSION,
            }[execution.architecture],
            "direct_prompt_version": DIRECT_PROMPT_VERSION,
            "pairwise_prompt_version": PAIRWISE_PROMPT_VERSION,
            "feedback_prompt_version": FEEDBACK_PROMPT_VERSION,
            "visual_contract_version": TASK1_VISUAL_CONTRACT_VERSION,
        }
        if any(getattr(execution, field) != version for field, version in supported.items()):
            raise AppError(
                "AI_CONFIGURATION_CHANGED",
                "Cấu hình AI đã thay đổi. Bạn có thể thử chấm lại.",
                409,
            )
    if execution is None or execution.architecture == "mts":
        service = Task1WritingScoringService
    elif execution.architecture == "direct":
        service = Task1DirectScoringService
    else:
        if (snapshot.id, snapshot.version) != (
            execution.anchor_set_id,
            execution.anchor_set_version,
        ):
            raise ValueError("Pinned snapshot mismatch")
        return Task1TACSScoringService(
            provider,
            chart_derenderer,
            chart_timeout,
            anchor_snapshot=snapshot,
            target_fingerprint=target_fingerprint,
            max_tree_nodes=execution.max_tree_nodes,
            **kwargs,
        )
    return service(provider, chart_derenderer, chart_timeout, **kwargs)
