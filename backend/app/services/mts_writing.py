import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.domains.scoring.ai_writing_normalization import normalize_scoring_output
from app.domains.scoring.ai_writing_validation import (
    resolve_evidence,
    safe_validation_issues,
    sanitize_calibration,
    validation_reason,
)
from app.domains.scoring.essay_sources import SourceSegment, segment_essay
from app.domains.scoring.mts_prompts import correction_message, evidence_messages, scoring_messages
from app.domains.scoring.writing import WritingScoringRequest, WritingScoringResult
from app.providers.writing_llm.base import (
    CompletionOptions,
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
    EvidenceResult,
    EvidenceSelection,
    OutputDiagnostic,
    RawScoringOutput,
    ScoringOutput,
    Trait,
)

T = TypeVar("T", bound=BaseModel)
TraceCallback = Callable[[EventType, EventPayload], Awaitable[None]]
logger = logging.getLogger(__name__)

# Evidence selects at most four IDs/short assessments. Scoring allows an
# 800-character paragraph plus six 240-character bullets, with headroom over
# the observed 1800-token truncation. Only a length repair adds 1024 tokens;
# the 4096 hard cap stays within half of the deployed 8192-token context.
# The adapter may lower it to verified remaining context without truncating input.
EVIDENCE_MAX_TOKENS = 1800
SCORING_MAX_TOKENS = 3072
LENGTH_REPAIR_HEADROOM_TOKENS = 1024
COMPLETION_MAX_TOKENS = 4096


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
        normal_max_tokens = EVIDENCE_MAX_TOKENS if stage == "evidence" else SCORING_MAX_TOKENS
        await trace(
            "evidence.request.started" if stage == "evidence" else "criterion.scoring.started",
            EventPayload(criterion=trait, stage=stage),
        )
        for repair in range(2):
            finish_reason = None
            issues = []
            max_tokens = (
                min(normal_max_tokens + LENGTH_REPAIR_HEADROOM_TOKENS, COMPLETION_MAX_TOKENS)
                if repair and reason == "PROVIDER_FINISH_LENGTH"
                else normal_max_tokens
            )
            try:
                completion = await self.provider.complete(
                    messages + ([correction_message(reason)] if repair else []),
                    # Request concise output/maxItems, but parse semantic core
                    # independently of provider-unsupported display limits.
                    (ScoringOutput if schema is RawScoringOutput else schema).model_json_schema(
                        mode="serialization"
                    ),
                    options=CompletionOptions(max_tokens=max_tokens),
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
                if isinstance(result, RawScoringOutput):
                    calibration, notices = sanitize_calibration(
                        result.calibration, result.score, sources
                    )
                    result, normalized_issues = normalize_scoring_output(result)
                    result.calibration = calibration
                    if normalized_issues:
                        self.diagnostics.append(
                            OutputDiagnostic(
                                stage=stage,
                                criterion=trait,
                                reason="SCORE_PRESENTATION_NORMALIZED",
                                attempt=repair + 1,
                                finish_reason=finish_reason,
                                validation_issues=normalized_issues,
                            )
                        )
                        for issue in normalized_issues:
                            logger.info(
                                "AI display normalization: stage=%s criterion=%s reason=SCORE_PRESENTATION_NORMALIZED attempt=%s finish_reason=%s field=%s validation_type=%s",
                                stage,
                                trait,
                                repair + 1,
                                finish_reason,
                                issue.field,
                                issue.validation_type,
                            )
                    for notice in notices:
                        self.diagnostics.append(
                            OutputDiagnostic(
                                stage=stage,
                                criterion=trait,
                                reason=notice,
                                attempt=repair + 1,
                                finish_reason=finish_reason,
                            )
                        )
                        logger.info(
                            "AI optional metadata: stage=%s criterion=%s reason=%s attempt=%s finish_reason=%s",
                            stage,
                            trait,
                            notice,
                            repair + 1,
                            finish_reason,
                        )
                return result
            except ValidationError as exc:
                reason = validation_reason(exc, stage)
                issues = safe_validation_issues(exc)
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
                validation_issues=issues,
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
            for issue in issues:
                logger.warning(
                    "AI validation detail: stage=%s criterion=%s reason=%s attempt=%s finish_reason=%s field=%s validation_type=%s",
                    stage,
                    trait,
                    reason,
                    repair + 1,
                    finish_reason,
                    issue.field,
                    issue.validation_type,
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
                    RawScoringOutput,
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
            # Text is already bounded; optional metadata never gates this result.
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

    async def assess_criterion(
        self,
        request: WritingScoringRequest,
        trait: Trait,
        trace: TraceCallback,
        evidence_prompt: list[Message],
        score_prompt: Callable[[EvidenceResult], list[Message]],
    ) -> CriterionResult:
        """Shared source validation/normalization for task-specific criterion prompts."""
        self.current_criterion = trait
        sources = {segment.source_id: segment for segment in segment_essay(request.response)}
        selection = await self._validated(
            evidence_prompt, EvidenceSelection, sources, trait, "evidence", trace
        )
        evidence = resolve_evidence(selection, sources)
        await trace(
            "criterion.evidence.completed",
            EventPayload(criterion=trait, evidence=evidence.evidence),
        )
        score = await self._validated(
            score_prompt(evidence), RawScoringOutput, sources, trait, "scoring", trace
        )
        return CriterionResult(
            **score.model_dump(exclude={"calibration"}), evidence=evidence.evidence
        )

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
