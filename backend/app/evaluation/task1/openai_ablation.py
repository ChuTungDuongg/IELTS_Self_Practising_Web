"""A–D comparison manifests only; no historical behavior emulated by the new adapter.

Live execution remains closed until a pre-request cost reservation accounts for
input/image tokens, all arms, both repair kinds and in-flight requests. A dollar
value printed in a dry-run plan is a requested ceiling, never a verified bound.
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.evaluation.task1.manifest import BenchmarkInputError

LIVE_DISABLED = (
    "BENCHMARK_ABLATION_LIVE_DISABLED: reliable pre-request cost reservation is unavailable; "
    "use --dry-run. No provider was called."
)


class OpenAIComparisonArm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arm: Literal["A", "B", "C", "D"]
    profile: str
    api: Literal["chat.completions"] = "chat.completions"
    planning_only: Literal[True] = True
    baseline_revision: str = "f950d30c47dd4e40d7a0aba9a01b2014888ed9da"
    reasoning: dict[str, str]
    image_detail: Literal["auto", "low", "high", "original"] | None
    legacy_stage_caps: bool
    low_completion_tokens: int | None
    medium_completion_tokens: int | None
    repair_completion_tokens: int | None
    global_safety_cap: int
    task1_image_assessment: bool
    task1_text_relevance_gate: bool
    additional_change: str
    stage_timeout_seconds: float
    max_budget_repairs_per_completion: int
    max_visual_reconciliations: int


def ablation_configurations(settings: Settings):
    """Keep sample/model/scorer fixed and describe each incremental intervention."""
    from app.evaluation.task1.runner import configurations

    if settings.ai_writing_provider != "openai" or settings.ai_writing_openai_model != "gpt-6-luna":
        raise BenchmarkInputError("BENCHMARK_OPENAI_ABLATION_REQUIRES_LUNA")
    base = configurations(settings, "v12", "off")[0]
    reasoning = {
        "default": "low",
        "task1.visual_grounding": "medium",
        "task1.visual_reconciliation": "medium",
        "task1.claim_extraction": "low",
        "task1.claim_verification": "medium",
        "task1.scoring.ta": "medium",
        "task1.evidence": "low",
        "task1.relevance": "low",
        "task1.feedback": "low",
    }
    arms = []
    for arm in ("A", "B", "C", "D"):
        legacy = arm == "A"
        policy = OpenAIComparisonArm(
            arm=arm,
            profile="openai_legacy_f950d30c" if legacy else "openai_task1_reasoned_v1",
            reasoning={"default": "none"} if legacy else reasoning,
            image_detail="high" if arm in {"C", "D"} else None,
            legacy_stage_caps=legacy,
            low_completion_tokens=None if legacy else 8192,
            medium_completion_tokens=None if legacy else 16384,
            repair_completion_tokens=None if legacy else 32768,
            global_safety_cap=4096 if legacy else 32768,
            task1_image_assessment=arm == "D",
            task1_text_relevance_gate=arm != "D",
            stage_timeout_seconds=300,
            max_budget_repairs_per_completion=0 if legacy else 1,
            max_visual_reconciliations=1 if arm == "D" else 0,
            additional_change={
                "A": "Historical adapter: none; min(legacy stage cap,4096); detail omitted; text-only TA.",
                "B": "A + staged reasoning, completion budgets and bounded budget repair; 300s timeout retained.",
                "C": "B + explicit high image detail; no claim that high beats auto.",
                "D": "C + TA source image, conflict assessment and bounded reference reconciliation; skip the inherited text-only relevance gate before image assessment.",
            }[arm],
        )
        # Plans use a fixed experimental protocol. Runtime overrides are not
        # silently described as if they were the controlled starting defaults.
        arms.append(
            base.model_copy(
                update={
                    "label": f"openai-luna-ablation-{arm}:plan-only",
                    "openai_inference": policy.model_dump(mode="json"),
                    "prompt_version": base.prompt_version if arm == "D" else "mts-task1-visual-v12",
                    "scoring_prompt_version": base.scoring_prompt_version
                    if arm == "D"
                    else "mts-task1-scoring-v12",
                }
            )
        )
    return arms


def annotate_plan(report, requested_max_usd: Decimal):
    report["openai_ablation"] = {
        "protocol_version": "openai-task1-ablation-v1",
        "status": "PLAN_ONLY_NO_INFERENCE",
        "same_samples_all_arms": True,
        "cache": "Arm/profile policy is part of each key; dry-run neither reads nor writes scoring checkpoints.",
        "budget": {
            "requested_max_usd": format(requested_max_usd, "f"),
            "live_enabled": False,
            "bound_verified": False,
            "reason": "No trustworthy pre-request reservation for input/images, arms, repairs and in-flight requests.",
        },
        "factual_feedback_accuracy": "unmeasured",
        "stability": "unmeasured",
        "cost_usd": None,
        "truncation_rate": None,
        "measured_quality_improvement": False,
        "required_before_live": [
            "Human authorization for the smoke run and a per-run dollar ceiling.",
            "Reviewed current model pricing and conservative input/image token upper bounds.",
            "Reserve worst-case cost before every POST including all arms, repairs and in-flight calls.",
            "Executable frozen A/B/C modes: never label the new adapter as historical baseline A.",
            "Private DEV essays, matching source images and permitted human labels.",
        ],
    }
    return report
