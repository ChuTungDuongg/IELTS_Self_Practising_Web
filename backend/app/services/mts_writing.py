import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.domains.scoring.ai_writing_validation import validation_reason, verify_evidence
from app.domains.scoring.mts_prompts import correction_message, evidence_messages, scoring_messages
from app.domains.scoring.writing import WritingScoringRequest, WritingScoringResult
from app.providers.writing_llm.base import LLMProvider, Message, ProviderFailure
from app.schemas.writing_ai import (
    TRAITS,
    AIWritingResult,
    AssessmentStage,
    Criteria,
    CriterionResult,
    EventPayload,
    EventType,
    EvidenceResult,
    OutputDiagnostic,
    Trait,
    TraitScore,
)

T = TypeVar("T", bound=BaseModel)
TraceCallback = Callable[[EventType, EventPayload], Awaitable[None]]
logger = logging.getLogger(__name__)


class MTSWritingScoringService:
    """Implements the existing WritingScoringProvider concept with an LLM boundary.

    Each trait owns two fresh logical turns. No other trait's score is shared.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.usage: list[dict[str, int]] = []
        self.diagnostics: list[OutputDiagnostic] = []
        self.current_criterion: Trait | None = None
        self.current_stage: AssessmentStage | None = None

    async def _validated(
        self,
        messages: list[Message],
        schema: type[T],
        essay: str,
        trait: Trait,
        stage: AssessmentStage,
        trace: TraceCallback,
    ) -> T:
        self.current_stage = stage
        reason = "SCHEMA_VALIDATION"
        await trace(
            "evidence.request.started" if stage == "evidence" else "criterion.scoring.started",
            EventPayload(criterion=trait, stage=stage),
        )
        for repair in range(2):
            try:
                completion = await self.provider.complete(
                    messages + ([correction_message(reason)] if repair else []),
                    schema.model_json_schema(mode="serialization"),
                )
                self.usage.append(completion.usage)
                await trace(
                    "evidence.validation.started"
                    if stage == "evidence"
                    else "criterion.scoring.validation.started",
                    EventPayload(criterion=trait, stage=stage),
                )
                result = schema.model_validate_json(completion.text)
                if isinstance(result, EvidenceResult):
                    result = verify_evidence(result, essay)
                return result
            except ValidationError as exc:
                reason = validation_reason(exc)
            except ProviderFailure as exc:
                if exc.code not in {"INVALID_PROVIDER_OUTPUT", "AI_PROVIDER_BAD_RESPONSE"}:
                    raise
                reason = exc.reason or "SCHEMA_VALIDATION"
            diagnostic = OutputDiagnostic(
                stage=stage, criterion=trait, reason=reason, attempt=repair + 1
            )
            self.diagnostics.append(diagnostic)
            logger.warning(
                "AI validation failure: stage=%s criterion=%s reason=%s attempt=%s",
                stage,
                trait,
                reason,
                repair + 1,
            )
            if not repair:
                await trace("criterion.retrying", EventPayload(criterion=trait, stage=stage))
        raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason=reason)

    async def assess(self, request: WritingScoringRequest, trace: TraceCallback) -> AIWritingResult:
        self.usage = []
        self.diagnostics = []
        criteria = {}
        for trait in TRAITS:
            self.current_criterion = trait
            self.current_stage = "evidence"
            await trace("criterion.started", EventPayload(criterion=trait))
            evidence = await self._validated(
                evidence_messages(request.prompt, request.response, trait),
                EvidenceResult,
                request.response,
                trait,
                "evidence",
                trace,
            )
            await trace(
                "criterion.evidence.completed",
                EventPayload(criterion=trait, evidence=evidence.evidence),
            )
            score = await self._validated(
                scoring_messages(request.prompt, request.response, trait, evidence),
                TraitScore,
                request.response,
                trait,
                "scoring",
                trace,
            )
            result = CriterionResult(**score.model_dump(), evidence=evidence.evidence)
            criteria[trait] = result
            await trace("criterion.completed", EventPayload(criterion=trait, result=result))
        validated = Criteria.model_validate(criteria)
        raw_mean, overall_band = aggregate_ai_task_two(*(criteria[trait].score for trait in TRAITS))
        return AIWritingResult(criteria=validated, raw_mean=raw_mean, overall_band=overall_band)

    async def score(self, request: WritingScoringRequest) -> WritingScoringResult:
        async def no_trace(_event: EventType, _payload: EventPayload) -> None:
            pass

        result = await self.assess(request, no_trace)
        return WritingScoringResult(
            overall_band=float(result.overall_band),
            criterion_scores={
                trait: float(getattr(result.criteria, trait).score) for trait in TRAITS
            },
            feedback=result.criteria.model_dump(mode="json"),
        )
