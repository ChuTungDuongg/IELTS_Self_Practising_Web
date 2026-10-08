from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.domains.scoring.mts_prompts import correction_message, evidence_messages, scoring_messages
from app.domains.scoring.writing import WritingScoringRequest, WritingScoringResult
from app.providers.writing_llm.base import LLMProvider, Message, ProviderFailure
from app.schemas.writing_ai import (
    TRAITS,
    AIWritingResult,
    Criteria,
    CriterionResult,
    EventPayload,
    EventType,
    EvidenceResult,
    TraitScore,
)

T = TypeVar("T", bound=BaseModel)
TraceCallback = Callable[[EventType, EventPayload], Awaitable[None]]


class MTSWritingScoringService:
    """Implements the existing WritingScoringProvider concept with an LLM boundary.

    Each trait owns two fresh logical turns. No other trait's score is shared.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.usage: list[dict[str, int]] = []

    async def _validated(self, messages: list[Message], schema: type[T], essay: str) -> T:
        for repair in range(2):
            try:
                completion = await self.provider.complete(
                    messages + ([correction_message()] if repair else []),
                    schema.model_json_schema(mode="serialization"),
                )
                self.usage.append(completion.usage)
                result = schema.model_validate_json(completion.text)
                if isinstance(result, EvidenceResult):
                    if any(item.quote not in essay for item in result.evidence):
                        raise ValueError("Quotation is not in essay")
                return result
            except (ValidationError, ValueError):
                pass
            except ProviderFailure as exc:
                if exc.code != "INVALID_PROVIDER_OUTPUT":
                    raise
        raise ProviderFailure("INVALID_PROVIDER_OUTPUT")

    async def assess(self, request: WritingScoringRequest, trace: TraceCallback) -> AIWritingResult:
        self.usage = []
        criteria = {}
        for trait in TRAITS:
            await trace("criterion.started", EventPayload(criterion=trait))
            evidence = await self._validated(
                evidence_messages(request.prompt, request.response, trait),
                EvidenceResult,
                request.response,
            )
            await trace(
                "criterion.evidence.completed",
                EventPayload(criterion=trait, evidence=evidence.evidence),
            )
            await trace("criterion.scoring.started", EventPayload(criterion=trait))
            score = await self._validated(
                scoring_messages(request.prompt, request.response, trait, evidence),
                TraitScore,
                request.response,
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
