import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.domains.scoring.ai_writing_normalization import (
    normalize_criterion_feedback,
    normalize_scoring_output,
)
from app.domains.scoring.ai_writing_validation import (
    resolve_evidence,
    safe_validation_issues,
    sanitize_calibration,
    validation_reason,
)
from app.domains.scoring.essay_sources import SourceSegment, request_sources, segment_essay
from app.domains.scoring.mts_prompts import (
    correction_message,
    evidence_messages,
    feedback_messages,
    scoring_messages,
    task2_feedback_correction,
)
from app.domains.scoring.task2_feedback import render_task2_feedback, validate_task2_feedback
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
    CompletionStage,
    Criteria,
    CriterionBandScore,
    CriterionFailure,
    CriterionFeedbackOutput,
    CriterionResult,
    EventPayload,
    EventType,
    EvidenceResult,
    EvidenceSelection,
    OutputDiagnostic,
    RawCriterionFeedbackOutput,
    RawScoringOutput,
    ScoringOutput,
    Task2FeedbackDraft,
    Trait,
)
from app.services.writing_execution import (
    BoundedWritingProvider,
    CriterionExecutionState,
    TraceFailure,
    WritingLatencyMetrics,
    gather_isolated,
)
from app.services.writing_relevance import classify_relevance

T = TypeVar("T", bound=BaseModel)
TraceCallback = Callable[[EventType, EventPayload], Awaitable[None]]
logger = logging.getLogger(__name__)

# Independent caps protect the score from explanation verbosity. One length
# repair adds only stage-specific headroom; input is never truncated.
EVIDENCE_MAX_TOKENS = 1800
SCORE_MAX_TOKENS = 128
FEEDBACK_MAX_TOKENS = 1200
STAGE_REPAIR_HEADROOM = {"evidence": 256, "score": 128, "feedback": 200, "scoring": 1024}
# Frozen evaluation baselines retain their original combined-output cap.
SCORING_MAX_TOKENS = 3072
COMPLETION_MAX_TOKENS = 4096
FEEDBACK_FALLBACK = (
    "Nhận xét chi tiết hiện chưa khả dụng; điểm tham khảo cho tiêu chí này đã được chấm hoàn tất."
)
FEEDBACK_RECOVERABLE_REASONS = frozenset(
    {
        "INVALID_JSON",
        "SCHEMA_VALIDATION",
        "FEEDBACK_SCHEMA_INVALID",
        "FEEDBACK_SCORE_MISMATCH",
        "EMPTY_MODEL_CONTENT",
        "MALFORMED_COMPLETION_ENVELOPE",
        "OUTPUT_TOO_LARGE",
        "PROVIDER_FINISH_LENGTH",
    }
)


class MTSWritingScoringService:
    """Implements the existing WritingScoringProvider concept with an LLM boundary.

    Each trait owns evidence, score-only and feedback turns. Scores are independent.
    """

    score_schema = CriterionBandScore

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_concurrent_requests: int = 2,
        latency: WritingLatencyMetrics | None = None,
        relevance_enabled: bool = True,
    ) -> None:
        self.provider = BoundedWritingProvider(provider, max_concurrent_requests)
        # Offline historical benchmarks can retain their pre-gate contract.
        self.relevance_enabled = relevance_enabled
        self._external_latency = latency is not None
        self.latency = latency or WritingLatencyMetrics()
        self._start_assessment()

    def _start_assessment(self) -> None:
        self.states = {trait: CriterionExecutionState(trait) for trait in TRAITS}
        self.aux_usage: list[dict[str, int]] = []
        self.aux_diagnostics: list[OutputDiagnostic] = []
        self.relevance = None
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
        stage: AssessmentStage | CompletionStage,
        trace: TraceCallback,
    ) -> T:
        state = self.states[trait]
        # Keep the public SSE stage vocabulary compatible with existing clients.
        state.stage = "scoring" if stage in {"score", "feedback"} else stage
        with self.latency.stage(stage, trait):
            return await self._validated_stage(messages, schema, sources, trait, stage, trace)

    def _normal_completion_budget(
        self, trait: Trait, stage: AssessmentStage | CompletionStage
    ) -> int:
        return {
            "evidence": EVIDENCE_MAX_TOKENS,
            "score": SCORE_MAX_TOKENS,
            "feedback": FEEDBACK_MAX_TOKENS,
            "scoring": SCORING_MAX_TOKENS,
        }[stage]

    async def _validated_stage(self, messages, schema, sources, trait, stage, trace):
        state = self.states[trait]
        reason = "SCHEMA_VALIDATION"
        normal_max_tokens = self._normal_completion_budget(trait, stage)
        public_stage = "scoring" if stage in {"score", "feedback"} else stage
        if stage != "feedback":
            await trace(
                "evidence.request.started" if stage == "evidence" else "criterion.scoring.started",
                EventPayload(criterion=trait, stage=public_stage),
            )
        for repair in range(2):
            finish_reason = None
            issues = []
            repair_headroom = (
                1024 if self.score_schema is RawScoringOutput else STAGE_REPAIR_HEADROOM[stage]
            )
            max_tokens = (
                normal_max_tokens + repair_headroom
                if repair and reason == "PROVIDER_FINISH_LENGTH"
                else normal_max_tokens
            )
            if self.score_schema is RawScoringOutput:
                max_tokens = min(max_tokens, COMPLETION_MAX_TOKENS)
            try:
                with self.latency.attempt(stage, trait, repair + 1) as timing:
                    try:
                        completion = await self.provider.complete(
                            messages
                            + (
                                [
                                    task2_feedback_correction(reason, trait)
                                    if schema is Task2FeedbackDraft
                                    else correction_message(reason, stage)
                                ]
                                if repair
                                else []
                            ),
                            # Provider display limits remain independent of semantic validation.
                            (
                                ScoringOutput
                                if schema is RawScoringOutput
                                else CriterionFeedbackOutput
                                if schema is RawCriterionFeedbackOutput
                                else schema
                            ).model_json_schema(mode="serialization"),
                            options=CompletionOptions(max_tokens=max_tokens),
                        )
                    except ProviderFailure as exc:
                        self.latency.completion(timing, exc.finish_reason, exc.usage)
                        if exc.usage:
                            state.usage.append(exc.usage)
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
                if stage != "feedback":
                    await trace(
                        "evidence.validation.started"
                        if stage == "evidence"
                        else "criterion.scoring.validation.started",
                        EventPayload(criterion=trait, stage=public_stage),
                    )
                result = schema.model_validate_json(completion.text)
                if isinstance(result, EvidenceSelection):
                    resolve_evidence(result, sources)
                if isinstance(result, Task2FeedbackDraft):
                    result = validate_task2_feedback(result, sources, trait, state.band_score.score)
                if isinstance(result, RawCriterionFeedbackOutput):
                    result, issues = normalize_criterion_feedback(result, state.band_score.score)
                    if issues:
                        state.diagnostics.append(
                            OutputDiagnostic(
                                stage=stage,
                                criterion=trait,
                                reason="FEEDBACK_PRESENTATION_NORMALIZED",
                                attempt=repair + 1,
                                finish_reason=finish_reason,
                                validation_issues=issues,
                            )
                        )
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
                "AI validation failure: stage=%s criterion=%s reason=%s attempt=%s finish_reason=%s completion_tokens=%s",
                stage,
                trait,
                reason,
                repair + 1,
                finish_reason,
                timing.get("completion_tokens"),
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
                await trace("criterion.retrying", EventPayload(criterion=trait, stage=public_stage))
        raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason=reason)

    async def assess(
        self, request: WritingScoringRequest, trace: TraceCallback
    ) -> AIWritingResult | None:
        self._start_assessment()
        trace = self.protected_trace(trace)
        segments = request_sources(request)

        async def run(trait):
            if trait == "ta" and await self._relevance_gate(request, None, trace):
                return
            await self._run_criterion(
                request,
                trait,
                trace,
                lambda: evidence_messages(request.prompt, request.response, trait, segments),
                lambda evidence: scoring_messages(
                    request.prompt, request.response, trait, evidence, segments
                ),
                assessor=self._assess_task2_criterion,
            )

        await gather_isolated(*(run(trait) for trait in TRAITS))
        return self._task2_result()

    def _task2_result(self) -> AIWritingResult | None:
        if self.failures:
            return None
        criteria = {trait: self.states[trait].result for trait in TRAITS}
        validated = Criteria.model_validate(criteria)
        raw_mean, overall_band = aggregate_ai_task_two(*(criteria[trait].score for trait in TRAITS))
        return AIWritingResult(
            criteria=validated,
            raw_mean=raw_mean,
            overall_band=overall_band,
            relevance=self.relevance,
        )

    async def _relevance_gate(self, request, reference, trace):
        if not self.relevance_enabled:
            return False
        self.states["ta"].stage = "relevance"
        self.relevance = await classify_relevance(
            self.provider,
            request,
            reference,
            trace,
            self.aux_usage,
            self.aux_diagnostics,
            self.latency,
        )
        if self.relevance is None or not self.relevance.short_circuit_applied:
            return False
        await trace("criterion.started", EventPayload(criterion="ta"))
        name = "Task Achievement" if reference is not None else "Task Response"
        result = CriterionResult(
            score=1,
            feedback=f"Bài viết hoàn toàn không liên quan đến yêu cầu của đề, phù hợp mô tả {name} Band 1. {self.relevance.reason}",
            strengths=[],
            improvements=["Viết nội dung trực tiếp đáp ứng yêu cầu của đề bài."],
            evidence=self.relevance.evidence,
        )
        self.states["ta"].result = result
        self.latency.completed_criterion()
        await trace("criterion.completed", EventPayload(criterion="ta", result=result))
        return True

    async def _run_criterion(
        self,
        request,
        trait,
        trace,
        evidence_prompt,
        score_prompt,
        feedback_prompt=None,
        *,
        assessor=None,
    ):
        state = self.states[trait]
        await trace("criterion.started", EventPayload(criterion=trait))
        try:
            state.result = await (assessor or self.assess_criterion)(
                request,
                trait,
                trace,
                evidence_prompt() if callable(evidence_prompt) else evidence_prompt,
                score_prompt,
                feedback_prompt,
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

    async def _assess_task2_criterion(
        self, request, trait, trace, evidence_prompt, score_prompt, _feedback_prompt=None
    ) -> CriterionResult:
        segments = request_sources(request)
        sources = {segment.source_id: segment for segment in segments}
        buffered_events = []

        async def buffer(event, payload):
            buffered_events.append((event, payload))

        async def flush():
            for event, payload in buffered_events:
                await trace(event, payload)
            buffered_events.clear()

        # Infer strictly from question + full essay + descriptors BEFORE any
        # generated assessment. Preserve the public evidence/scoring SSE order.
        try:
            self.states[trait].stage = "scoring"
            score = await self._validated(
                score_prompt(EvidenceResult(evidence=[])),
                CriterionBandScore,
                sources,
                trait,
                "score",
                buffer,
            )
            self.states[trait].band_score = score
            selection = await self._validated(
                evidence_prompt, EvidenceSelection, sources, trait, "evidence", trace
            )
            evidence = resolve_evidence(selection, sources)
            for item in evidence.evidence:
                # Selector prose is unverified, never scoring input or public
                # feedback. Only backend-resolved source locations are shown.
                item.assessment = (
                    f"Trích dẫn từ đoạn {sources[item.source_id].paragraph_index} của bài viết."
                )
            await trace(
                "criterion.evidence.completed",
                EventPayload(criterion=trait, evidence=evidence.evidence),
            )
        except Exception:
            await flush()
            raise
        await flush()
        try:
            candidate = await self._validated(
                feedback_messages(
                    request.prompt, request.response, trait, evidence, score.score, segments
                ),
                Task2FeedbackDraft,
                sources,
                trait,
                "feedback",
                trace,
            )
            display, evidence = render_task2_feedback(candidate, sources)
        except ProviderFailure as exc:
            recoverable = FEEDBACK_RECOVERABLE_REASONS | {
                "EVIDENCE_UNKNOWN_SOURCE_ID",
                "QUOTE_NOT_EXACT",
            }
            if (
                exc.code not in {"INVALID_PROVIDER_OUTPUT", "AI_PROVIDER_BAD_RESPONSE"}
                or exc.reason not in recoverable
            ):
                raise
            self.states[trait].diagnostics.append(
                OutputDiagnostic(
                    stage="feedback", criterion=trait, reason="FEEDBACK_FALLBACK_USED", attempt=2
                )
            )
            logger.warning(
                "AI feedback fallback: stage=feedback criterion=%s reason=FEEDBACK_FALLBACK_USED",
                trait,
            )
            display = CriterionFeedbackOutput(
                feedback=FEEDBACK_FALLBACK, strengths=[], improvements=[]
            )
        return CriterionResult(
            score=score.score, **display.model_dump(), evidence=evidence.evidence
        )

    async def assess_criterion(
        self,
        request: WritingScoringRequest,
        trait: Trait,
        trace: TraceCallback,
        evidence_prompt: list[Message],
        score_prompt: Callable[[EvidenceResult], list[Message]],
        feedback_prompt: Callable[[EvidenceResult, CriterionBandScore], list[Message]]
        | None = None,
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
            score_prompt(evidence),
            self.score_schema,
            sources,
            trait,
            "scoring" if self.score_schema is RawScoringOutput else "score",
            trace,
        )
        if isinstance(score, RawScoringOutput):
            # Evaluation-only frozen baselines keep their combined contract.
            return CriterionResult(
                **score.model_dump(exclude={"calibration"}), evidence=evidence.evidence
            )
        self.states[trait].band_score = score
        messages = (
            feedback_prompt(evidence, score)
            if feedback_prompt
            else feedback_messages(request.prompt, request.response, trait, evidence, score.score)
        )
        try:
            feedback = await self._validated(
                messages, RawCriterionFeedbackOutput, sources, trait, "feedback", trace
            )
        except ProviderFailure as exc:
            if (
                exc.code not in {"INVALID_PROVIDER_OUTPUT", "AI_PROVIDER_BAD_RESPONSE"}
                or exc.reason not in FEEDBACK_RECOVERABLE_REASONS
            ):
                raise
            diagnostic = OutputDiagnostic(
                stage="feedback", criterion=trait, reason="FEEDBACK_FALLBACK_USED", attempt=2
            )
            self.states[trait].diagnostics.append(diagnostic)
            logger.warning(
                "AI feedback fallback: stage=feedback criterion=%s reason=FEEDBACK_FALLBACK_USED",
                trait,
            )
            feedback = CriterionFeedbackOutput(
                feedback=FEEDBACK_FALLBACK, strengths=[], improvements=[]
            )
        return CriterionResult(
            score=score.score, **feedback.model_dump(), evidence=evidence.evidence
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
