"""OpenAI inference budgets and capabilities, separate from self-hosted policy.

Initial budgets are evaluation starting points, not measured quality guarantees.
Chat Completions exposes one total cap for reasoning + visible output; business
JSON limits remain in the domain schemas. No internal reasoning is requested.
"""

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal, get_args

from app.providers.writing_llm.base import CompletionOptions, ProviderFailure

if TYPE_CHECKING:
    from app.core.config import OpenAIStageOverride, Settings

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
ImageDetail = Literal["auto", "low", "high", "original"]


@dataclass(frozen=True, slots=True)
class ResolvedOpenAIPolicy:
    profile: str
    task: str
    stage: str
    criterion: str | None
    reasoning_effort: ReasoningEffort
    image_detail: ImageDetail | None
    total_completion_tokens: int
    repair_completion_tokens: int
    timeout_seconds: float
    task1_image_assessment: bool

    def identity(self) -> dict:
        return asdict(self)


_STAGES = {
    "default",
    "visual_grounding",
    "visual_reconciliation",
    "claim_extraction",
    "claim_verification",
    "evidence",
    "evidence_selection",
    "relevance",
    "relevance_classification",
    "scoring",
    "feedback",
    "language_feedback",
}
_TASKS = {"default", "task1", "task2", "speaking"}
_CRITERIA = {"ta", "tr", "cc", "lr", "gra", "fc", "pr"}


def normalize_stage(value: str) -> str:
    return {"score": "scoring"}.get(value.lower(), value.lower())


def _configuration_error() -> ProviderFailure:
    # Never put model/override/raw environment contents in public failures.
    return ProviderFailure("AI_PROVIDER_CONFIGURATION_ERROR")


class OpenAIInferencePolicy:
    """Capabilities are allowlisted here, never guessed from model-name prefixes.

    Verified official Luna documentation supports these reasoning efforts.
    Chat image_url.detail=auto/low/high is supported; original stays fail-closed
    until model-specific Chat support is established (the current sizing table
    omits Luna). An unknown model needs an explicit capability addition.
    """

    PROFILE = "openai_task1_reasoned_v1"
    API = "chat/completions"

    def __init__(self, settings: "Settings", *, model: str | None = None) -> None:
        self.model = model or settings.ai_writing_openai_model
        self.settings = settings
        if self.model != "gpt-6-luna" or settings.ai_writing_openai_profile != self.PROFILE:
            raise _configuration_error()
        self.overrides: dict[str, OpenAIStageOverride] = {}
        for key, value in settings.ai_writing_openai_stage_overrides.items():
            parts = key.lower().split(".")
            if len(parts) not in {2, 3}:
                raise _configuration_error()
            task, stage = parts[0], normalize_stage(parts[1])
            if task not in _TASKS or stage not in _STAGES:
                raise _configuration_error()
            if len(parts) == 3 and parts[2] not in _CRITERIA:
                raise _configuration_error()
            canonical = ".".join([task, stage, *parts[2:]])
            if canonical in self.overrides:
                raise _configuration_error()
            self.overrides[canonical] = value
        # Validate the complete profile before a billable POST, including explicit
        # old 4096 safety caps. No silent min(legacy_stage_cap, new_budget).
        for task in _TASKS:
            for stage in _STAGES:
                for criterion in (None, *_CRITERIA):
                    self.resolve(
                        CompletionOptions(
                            task=task if task != "default" else None,
                            stage=stage,
                            criterion=criterion,
                        ),
                        has_image=True,
                    )

    def resolve(
        self, options: CompletionOptions | None = None, *, has_image: bool = False
    ) -> ResolvedOpenAIPolicy:
        options = options or CompletionOptions()
        task = options.task or "default"
        stage = normalize_stage(options.stage)
        criterion = options.criterion.lower() if options.criterion is not None else None
        if (
            task not in _TASKS
            or stage not in _STAGES
            or (criterion is not None and criterion not in _CRITERIA)
            or type(options.attempt) is not int
            or options.attempt not in {1, 2}
        ):
            raise _configuration_error()
        medium = task == "task1" and (
            stage in {"visual_grounding", "visual_reconciliation", "claim_verification"}
            or (stage == "scoring" and criterion == "ta")
        )
        effort = "medium" if medium else self.settings.ai_writing_openai_reasoning_effort
        # Stage overrides beat task/stage overrides, which beat default values.
        override = {}
        for key in (f"{task}.{stage}", f"{task}.{stage}.{criterion}"):
            if key in self.overrides:
                override.update(self.overrides[key].model_dump(exclude_none=True))
        effort = override.get("reasoning_effort", effort)
        if effort not in get_args(ReasoningEffort):
            raise _configuration_error()
        if effort in {"none", "low"}:
            budget = self.settings.ai_writing_openai_low_completion_tokens
        elif effort == "medium":
            budget = self.settings.ai_writing_openai_medium_completion_tokens
        else:
            budget = self.settings.ai_writing_openai_repair_completion_tokens
        budget = override.get("total_completion_tokens", budget)
        if budget > self.settings.ai_writing_openai_max_output_tokens:
            raise _configuration_error()
        detail = self.settings.ai_writing_openai_image_detail
        detail = override.get("image_detail", detail)
        if detail not in {"auto", "low", "high"}:
            raise _configuration_error()
        timeout = self.settings.ai_writing_openai_stage_timeout_seconds
        timeout = override.get("timeout_seconds", timeout)
        return ResolvedOpenAIPolicy(
            profile=self.PROFILE,
            task=task,
            stage=stage,
            criterion=criterion,
            reasoning_effort=effort,
            image_detail=detail if has_image else None,
            total_completion_tokens=budget,
            repair_completion_tokens=min(
                self.settings.ai_writing_openai_repair_completion_tokens,
                self.settings.ai_writing_openai_max_output_tokens,
            ),
            timeout_seconds=min(timeout, self.settings.ai_writing_request_timeout_seconds),
            task1_image_assessment=self.settings.ai_writing_openai_task1_image_assessment,
        )

    def identity(self) -> dict:
        return {
            "api": self.API,
            "model": self.model,
            "profile": self.PROFILE,
            "default_reasoning_effort": self.settings.ai_writing_openai_reasoning_effort,
            "image_detail": self.settings.ai_writing_openai_image_detail,
            "low_completion_tokens": self.settings.ai_writing_openai_low_completion_tokens,
            "medium_completion_tokens": self.settings.ai_writing_openai_medium_completion_tokens,
            "repair_completion_tokens": self.settings.ai_writing_openai_repair_completion_tokens,
            "global_safety_cap": self.settings.ai_writing_openai_max_output_tokens,
            "stage_timeout_seconds": self.settings.ai_writing_openai_stage_timeout_seconds,
            "request_timeout_seconds": self.settings.ai_writing_request_timeout_seconds,
            "run_timeout_seconds": self.settings.ai_writing_openai_run_timeout_seconds,
            "max_budget_repairs": 1,
            "task1_image_assessment": self.settings.ai_writing_openai_task1_image_assessment,
            "stage_overrides": {
                key: value.model_dump(exclude_none=True)
                for key, value in sorted(self.overrides.items())
            },
        }
