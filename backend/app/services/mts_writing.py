import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.domains.scoring.ai_writing_validation import (
    resolve_evidence,
    validate_calibration,
    validation_reason,
)
from app.domains.scoring.essay_sources import SourceSegment, segment_essay
from app.domains.scoring.mts_prompts import correction_message, evidence_messages, scoring_messages
from app.domains.scoring.writing import WritingScoringRequest, WritingScoringResult
from app.providers.writing_llm.base import (
    LLMProvider,
    Message,
    ProviderFailure,
    safe_finish_reason,
    validate_finish,
)
from app.schemas.writing_ai import (
    TRAITS,
    AIWritingResult,
    AssessmentStage,
    Criteria,
    CriterionFailure,
    CriterionResult,
    EventPayload,
    EventType,
    EvidenceSelection,
    OutputDiagnostic,
    ScoringOutput,
    Trait,
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
        self.failures: dict[Trait, CriterionFailure] = {}

    async def _validated(
        self,
        messages: list[Message],
        schema: type[T],
        sources: dict[str, SourceSegment],
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
            finish_reason = None
            try:
                completion = await self.provider.complete(
                    messages + ([correction_message(reason)] if repair else []),
                    schema.model_json_schema(mode="serialization"),
                )
                self.usage.append(completion.usage)
                finish_reason = safe_finish_reason(completion.finish_reason)
                logger.info(
                    "AI completion: stage=%s criterion=%s attempt=%s finish_reason=%s completion_tokens=%s",
                    stage,
                    trait,
                    repair + 1,
                    finish_reason,
                    completion.usage.get("completion_tokens"),
                )
                validate_finish(completion.finish_reason)
                await trace(
                    "evidence.validation.started"
                    if stage == "evidence"
                    else "criterion.scoring.validation.started",
                    EventPayload(criterion=trait, stage=stage),
                )
                result = schema.model_validate_json(completion.text)
                if isinstance(result, EvidenceSelection):
                    resolve_evidence(result, sources)
                if isinstance(result, ScoringOutput):
                    validate_calibration(result, sources)
                return result
            except ValidationError as exc:
                reason = validation_reason(exc, stage)
            except ProviderFailure as exc:
                if exc.code not in {"INVALID_PROVIDER_OUTPUT", "AI_PROVIDER_BAD_RESPONSE"}:
                    raise
                reason = exc.reason or "SCHEMA_VALIDATION"
                finish_reason = exc.finish_reason or finish_reason
            diagnostic = OutputDiagnostic(
                stage=stage,
                criterion=trait,
                reason=reason,
                attempt=repair + 1,
                finish_reason=finish_reason,
            )
            self.diagnostics.append(diagnostic)
            logger.warning(
                "AI validation failure: stage=%s criterion=%s reason=%s attempt=%s finish_reason=%s",
                stage,
                trait,
                reason,
                repair + 1,
                finish_reason,
            )
            if not repair:
                await trace("criterion.retrying", EventPayload(criterion=trait, stage=stage))
        raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason=reason)

    async def assess(
        self, request: WritingScoringRequest, trace: TraceCallback
    ) -> AIWritingResult | None:
        self.usage = []
        self.diagnostics = []
        self.failures = {}
        segments = segment_essay(request.response)
        sources = {segment.source_id: segment for segment in segments}
        criteria = {}
        for trait in TRAITS:
            self.current_criterion = trait
            self.current_stage = "evidence"
            await trace("criterion.started", EventPayload(criterion=trait))
            try:
                selection = await self._validated(
                    evidence_messages(request.prompt, request.response, trait, segments),
                    EvidenceSelection,
                    sources,
                    trait,
                    "evidence",
                    trace,
                )
                evidence = resolve_evidence(selection, sources)
                await trace(
                    "criterion.evidence.completed",
                    EventPayload(criterion=trait, evidence=evidence.evidence),
                )
                score = await self._validated(
                    scoring_messages(request.prompt, request.response, trait, evidence, segments),
                    ScoringOutput,
                    sources,
                    trait,
                    "scoring",
                    trace,
                )
            except ProviderFailure as exc:
                failure = CriterionFailure(
                    error_code=exc.code,
                    error_message="Không thể hoàn tất tiêu chí này.",
                    stage=self.current_stage,
                )
                self.failures[trait] = failure
                await trace(
                    "criterion.failed", EventPayload(criterion=trait, **failure.model_dump())
                )
                continue
            # Calibration is a bounded justification summary, not hidden reasoning.
            # It guides validation in this interaction; user-facing DTO stays small.
            result = CriterionResult(
                **score.model_dump(exclude={"calibration"}), evidence=evidence.evidence
            )
            criteria[trait] = result
            await trace("criterion.completed", EventPayload(criterion=trait, result=result))
        if self.failures:
            return None
        validated = Criteria.model_validate(criteria)
        raw_mean, overall_band = aggregate_ai_task_two(*(criteria[trait].score for trait in TRAITS))
        return AIWritingResult(criteria=validated, raw_mean=raw_mean, overall_band=overall_band)

    async def score(self, request: WritingScoringRequest) -> WritingScoringResult:
        async def no_trace(_event: EventType, _payload: EventPayload) -> None:
            pass

        result = await self.assess(request, no_trace)
        if result is None:
            raise ProviderFailure(next(iter(self.failures.values())).error_code)
        return WritingScoringResult(
            overall_band=float(result.overall_band),
            criterion_scores={
                trait: float(getattr(result.criteria, trait).score) for trait in TRAITS
            },
            feedback=result.criteria.model_dump(mode="json"),
        )
