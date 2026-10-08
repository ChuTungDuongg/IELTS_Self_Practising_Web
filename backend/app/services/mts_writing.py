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
from app.services.writing_execution import (
    BoundedWritingProvider,
    CriterionExecutionState,
    TraceFailure,
    WritingLatencyMetrics,
    gather_isolated,
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

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_concurrent_requests: int = 2,
        latency: WritingLatencyMetrics | None = None,
    ) -> None:
        self.provider = BoundedWritingProvider(provider, max_concurrent_requests)
        self._external_latency = latency is not None
        self.latency = latency or WritingLatencyMetrics()
        self._start_assessment()

    def _start_assessment(self) -> None:
        self.states = {trait: CriterionExecutionState(trait) for trait in TRAITS}
        self.aux_usage: list[dict[str, int]] = []
        self.aux_diagnostics: list[OutputDiagnostic] = []
        if not self._external_latency:
            self.latency = WritingLatencyMetrics()

    @property
    def usage(self) -> list[dict[str, int]]:
        return self.aux_usage + [item for trait in TRAITS for item in self.states[trait].usage]

    @property
    def diagnostics(self) -> list[OutputDiagnostic]:
        return self.aux_diagnostics + [
            item for trait in TRAITS for item in self.states[trait].diagnostics
        ]

    @property
    def failures(self) -> dict[Trait, CriterionFailure]:
        return {trait: self.states[trait].failure for trait in TRAITS if self.states[trait].failure}

    @property
    def failure_context(self) -> tuple[Trait | None, AssessmentStage | None]:
        return next(
            ((trait, failure.stage) for trait, failure in self.failures.items()), (None, None)
        )

    def latency_summary(self) -> dict:
        return {
            **self.latency.summary(),
            "llm_concurrency_limit": self.provider.limit,
            "peak_active_llm_requests": self.provider.peak_active,
        }

    @staticmethod
    def protected_trace(trace: TraceCallback) -> TraceCallback:
        async def emit(event, payload):
            try:
                await trace(event, payload)
            except TraceFailure:
                raise
            except Exception:
                raise TraceFailure from None

        return emit

    async def _validated(
        self,
        messages: list[Message],
        schema: type[T],
        sources: dict[str, SourceSegment],
        trait: Trait,
        stage: AssessmentStage,
        trace: TraceCallback,
    ) -> T:
        state = self.states[trait]
        state.stage = stage
        with self.latency.stage(stage, trait):
            return await self._validated_stage(messages, schema, sources, trait, stage, trace)

    async def _validated_stage(self, messages, schema, sources, trait, stage, trace):
        state = self.states[trait]
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
                with self.latency.attempt(stage, trait, repair + 1) as timing:
                    try:
                        completion = await self.provider.complete(
                            messages + ([correction_message(reason)] if repair else []),
                            # Provider display limits remain independent of semantic validation.
                            (
                                ScoringOutput if schema is RawScoringOutput else schema
                            ).model_json_schema(mode="serialization"),
                            options=CompletionOptions(max_tokens=max_tokens),
                        )
                    except ProviderFailure as exc:
                        self.latency.completion(timing, exc.finish_reason, {})
                        raise
                    self.latency.completion(timing, completion.finish_reason, completion.usage)
                state.usage.append(completion.usage)
                finish_reason = safe_finish_reason(completion.finish_reason)
                logger.info(
                    "AI completion: stage=%s criterion=%s attempt=%s finish_reason=%s completion_tokens=%s",
                    stage,
                    trait,
                    repair + 1,
                    finish_reason,
                    timing.get("completion_tokens"),
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
                        state.diagnostics.append(
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
                        state.diagnostics.append(
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
            state.diagnostics.append(diagnostic)
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
        self._start_assessment()
        trace = self.protected_trace(trace)
        segments = segment_essay(request.response)
        await gather_isolated(
            *(
                self._run_criterion(
                    request,
                    trait,
                    trace,
                    lambda trait=trait: evidence_messages(
                        request.prompt, request.response, trait, segments
                    ),
                    lambda evidence, trait=trait: scoring_messages(
                        request.prompt, request.response, trait, evidence, segments
                    ),
                )
                for trait in TRAITS
            )
        )
        return self._task2_result()

    def _task2_result(self) -> AIWritingResult | None:
        if self.failures:
            return None
        criteria = {trait: self.states[trait].result for trait in TRAITS}
        validated = Criteria.model_validate(criteria)
        raw_mean, overall_band = aggregate_ai_task_two(*(criteria[trait].score for trait in TRAITS))
        return AIWritingResult(criteria=validated, raw_mean=raw_mean, overall_band=overall_band)

    async def _run_criterion(self, request, trait, trace, evidence_prompt, score_prompt):
        state = self.states[trait]
        await trace("criterion.started", EventPayload(criterion=trait))
        try:
            state.result = await self.assess_criterion(
                request,
                trait,
                trace,
                evidence_prompt() if callable(evidence_prompt) else evidence_prompt,
                score_prompt,
            )
        except TraceFailure:
            raise
        except Exception as exc:
            # Unexpected criterion/provider bugs are isolated; never retain exception text.
            failure = CriterionFailure(
                error_code=exc.code
                if isinstance(exc, ProviderFailure)
                else "AI_PROVIDER_BAD_RESPONSE",
                error_message="Không thể hoàn tất tiêu chí này.",
                stage=state.stage,
            )
            state.failure = failure
            await trace("criterion.failed", EventPayload(criterion=trait, **failure.model_dump()))
            return None
        self.latency.completed_criterion()
        await trace("criterion.completed", EventPayload(criterion=trait, result=state.result))
        return state.result

    async def assess_criterion(
        self,
        request: WritingScoringRequest,
        trait: Trait,
        trace: TraceCallback,
        evidence_prompt: list[Message],
        score_prompt: Callable[[EvidenceResult], list[Message]],
    ) -> CriterionResult:
        """Shared source validation/normalization for task-specific criterion prompts."""
        sources = {segment.source_id: segment for segment in segment_essay(request.response)}
        selection = await self._validated(
            evidence_prompt, EvidenceSelection, sources, trait, "evidence", trace
        )
        evidence = resolve_evidence(selection, sources)
        await trace(
            "criterion.evidence.completed",
            EventPayload(criterion=trait, evidence=evidence.evidence),
        )
        self.states[trait].stage = "scoring"
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
