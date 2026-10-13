import logging
from functools import partial

from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.domains.scoring.ai_writing_validation import resolve_evidence
from app.domains.scoring.essay_sources import request_sources
from app.domains.scoring.task1_facts import derive_facts
from app.domains.scoring.task1_feedback import normalize_task1_feedback, render_task1_feedback
from app.domains.scoring.task1_prompts import evidence_prompt, feedback_prompt, score_prompt
from app.domains.scoring.writing_annotations import build_writing_annotations
from app.domains.writing.visual_families import visual_family
from app.providers.chart_derendering import ChartDerenderingProvider
from app.providers.writing_llm.base import LLMProvider, Message, ProviderFailure
from app.schemas.task1_claims import ExtractedClaims, Task1Analysis
from app.schemas.task1_feedback import RawTask1FeedbackDraft
from app.schemas.writing_ai import (
    TRAITS,
    AssessmentStage,
    Criteria,
    CriterionBandScore,
    CriterionFailure,
    CriterionFeedbackOutput,
    CriterionResult,
    EventPayload,
    EvidenceResult,
    EvidenceSelection,
    OutputDiagnostic,
    Task1WritingResult,
    Trait,
)
from app.services.mts_writing import (
    COMPLETION_MAX_TOKENS,
    FEEDBACK_FALLBACK,
    FEEDBACK_RECOVERABLE_REASONS,
    MTSWritingScoringService,
    TraceCallback,
)
from app.services.task1_chart_cross_check import (
    apply_chart_cross_check,
    extract_chart,
    specialist_eligible,
)
from app.services.task1_claims import Task1ClaimService
from app.services.task1_grounding import Task1VisualGroundingService
from app.services.task1_input import Task1ScoringRequest
from app.services.writing_execution import TraceFailure, WritingLatencyMetrics, gather_isolated

logger = logging.getLogger(__name__)


class Task1WritingScoringService(MTSWritingScoringService):
    """Independent linguistic criteria overlap perception; TA waits for its dependencies."""

    def __init__(
        self,
        provider: LLMProvider,
        chart_derenderer: ChartDerenderingProvider | None = None,
        chart_timeout: float = 90,
        *,
        max_concurrent_requests: int = 2,
        latency: WritingLatencyMetrics | None = None,
        relevance_enabled: bool = True,
    ) -> None:
        super().__init__(
            provider,
            max_concurrent_requests=max_concurrent_requests,
            latency=latency,
            relevance_enabled=relevance_enabled,
        )
        self.chart_derenderer, self.chart_timeout = chart_derenderer, chart_timeout

    def _normal_completion_budget(self, trait: Trait, stage: AssessmentStage) -> int:
        if trait == "ta" and stage == "scoring":
            return COMPLETION_MAX_TOKENS
        return super()._normal_completion_budget(trait, stage)

    def _repair_message(self, reason, schema, trait, stage):
        if schema is RawTask1FeedbackDraft:
            return {
                "role": "system",
                "content": f"Correction ({reason}): Return one complete observations JSON object "
                "matching the supplied schema, no score or extra fields. Use allowed sources, "
                "criterion-appropriate aspects and exact spans. For TA, observation=null; "
                "select only verified claims. Omit uncertain items; an empty list is valid.",
            }
        return super()._repair_message(reason, schema, trait, stage)

    def _evidence_prompt(
        self, request: Task1ScoringRequest, trait: Trait, analysis: Task1Analysis
    ) -> list[Message]:
        return evidence_prompt(request, trait, analysis)

    def _score_prompt(
        self,
        request: Task1ScoringRequest,
        trait: Trait,
        evidence: EvidenceResult,
        analysis: Task1Analysis,
    ) -> list[Message]:
        return score_prompt(request, trait, evidence, analysis)

    def _analysis_services(self):
        return (
            Task1VisualGroundingService(
                self.provider, self.aux_usage, self.aux_diagnostics, self.latency
            ),
            Task1ClaimService(self.provider, self.aux_usage, self.aux_diagnostics, self.latency),
        )

    async def assess(
        self, request: Task1ScoringRequest, trace: TraceCallback
    ) -> Task1WritingResult | None:
        self._start_assessment()
        trace = self.protected_trace(trace)
        analysis = Task1Analysis(visual_family=visual_family(request.task_type).value)
        grounding, claims = self._analysis_services()

        async def achievement():
            self.states["ta"].stage = "visual_grounding"
            await self._ground(request, analysis, grounding, trace)
            if analysis.confidence != "UNUSABLE" and await self._relevance_gate(
                request, analysis.reference, trace
            ):
                return
            await self._prepare_analysis(request, analysis, grounding, claims, trace)
            await self._task1_criterion(request, "ta", analysis, trace)

        await gather_isolated(
            achievement(),
            *(
                self._task1_criterion(request, trait, analysis, trace)
                for trait in TRAITS
                if trait != "ta"
            ),
        )
        return self._task1_result(analysis)

    async def _prepare_analysis(self, request, analysis, grounding, claim_service, trace):
        # Primary grounding and relevance have finished; now parallelize post-gate work.
        prepared = await gather_isolated(
            self._prepare_reference(request, analysis, grounding, trace),
            self._extract_claims(request, claim_service, trace, analysis),
        )
        if analysis.confidence != "UNUSABLE" and prepared[1] is not None:
            await self._verify_claims(request, prepared[1], analysis, claim_service, trace)

    async def _prepare_reference(self, request, analysis, grounding, trace):
        if analysis.confidence != "UNUSABLE":
            if specialist_eligible(request):
                prepared = await extract_chart(
                    request, self.chart_derenderer, trace, self.chart_timeout, self.latency
                )
                await apply_chart_cross_check(request, analysis, prepared, trace, self.latency)
            await self._derive_facts(analysis, trace)

    async def _ground(self, request, analysis, grounding, trace):
        logger.info(
            "Task1 visual grounding: chart_specialist_enabled=%s",
            str(request.chart_specialist.enabled).lower(),
        )
        await trace(
            "visual_grounding.started", EventPayload(criterion="ta", stage="visual_grounding")
        )
        try:
            with self.latency.stage("visual_grounding", "ta"):
                output = await grounding.ground(request)
        except TraceFailure:
            raise
        except Exception:
            analysis.warnings.append("VISUAL_GROUNDING_FAILED")
            await trace(
                "visual_grounding.failed",
                EventPayload(
                    criterion="ta",
                    stage="visual_grounding",
                    task1_analysis=analysis,
                    error_code="AI_VISUAL_GROUNDING_FAILED",
                ),
            )
        else:
            analysis.reference, analysis.confidence = output.reference, output.reference.confidence
            if analysis.confidence == "LOW":
                analysis.warnings.append("VISUAL_LOW_CONFIDENCE")
            await trace(
                "visual_grounding.completed",
                EventPayload(
                    criterion="ta",
                    stage="visual_grounding",
                    task1_analysis=analysis,
                ),
            )

    async def _extract_claims(
        self, request, claim_service, trace, analysis=None
    ) -> ExtractedClaims | None:
        await trace(
            "claim_extraction.started", EventPayload(criterion="ta", stage="claim_extraction")
        )
        try:
            with self.latency.stage("claim_extraction", "ta"):
                extracted = await claim_service.extract(
                    request, analysis.reference if analysis else None
                )
        except TraceFailure:
            raise
        except Exception:
            if analysis is not None:
                analysis.warnings.append("CLAIM_EXTRACTION_FAILED")
            await trace(
                "claim_extraction.failed",
                EventPayload(
                    criterion="ta",
                    stage="claim_extraction",
                    error_code="AI_CLAIM_EXTRACTION_FAILED",
                    task1_analysis=analysis,
                ),
            )
            return None
        await trace(
            "claim_extraction.completed", EventPayload(criterion="ta", stage="claim_extraction")
        )
        return extracted

    async def _derive_facts(self, analysis, trace):
        try:
            with self.latency.stage("derived_facts", "ta"):
                analysis.derived_facts = derive_facts(analysis.reference.model_copy(deep=True))
        except Exception:
            # Preserve perception; missing facts cannot establish a contradiction.
            logger.warning(
                "Task1 fact derivation failure: stage=derived_facts reason=DERIVED_FACTS_FAILED"
            )
            analysis.warnings.append("DERIVED_FACTS_FAILED")
            await trace(
                "derived_facts.failed",
                EventPayload(
                    criterion="ta",
                    stage="derived_facts",
                    task1_analysis=analysis,
                    error_code="AI_DERIVED_FACTS_FAILED",
                ),
            )
        else:
            await trace(
                "derived_facts.completed",
                EventPayload(
                    criterion="ta",
                    stage="derived_facts",
                    task1_analysis=analysis,
                ),
            )

    async def _verify_claims(self, request, extracted, analysis, claim_service, trace):
        self.states["ta"].stage = "claim_verification"
        await trace(
            "claim_verification.started", EventPayload(criterion="ta", stage="claim_verification")
        )
        try:
            with self.latency.stage("claim_verification", "ta"):
                verified = await claim_service.verify(request, extracted, analysis)
        except TraceFailure:
            raise
        except Exception:
            verified = False
        if not verified:
            analysis.warnings.append("CLAIM_VERIFICATION_FAILED")
            await trace(
                "claim_verification.failed",
                EventPayload(
                    criterion="ta",
                    stage="claim_verification",
                    task1_analysis=analysis,
                    error_code="AI_CLAIM_VERIFICATION_FAILED",
                ),
            )
        else:
            await trace(
                "claim_verification.completed",
                EventPayload(
                    criterion="ta",
                    stage="claim_verification",
                    task1_analysis=analysis,
                ),
            )

    async def _task1_criterion(self, request, trait, analysis, trace):
        if trait == "ta" and analysis.confidence == "UNUSABLE":
            await trace("criterion.started", EventPayload(criterion=trait))
            failure = CriterionFailure(
                error_code="AI_PROVIDER_BAD_RESPONSE",
                error_message="Không thể hoàn tất tiêu chí này.",
                stage="visual_grounding",
            )
            self.states[trait].stage, self.states[trait].failure = failure.stage, failure
            await trace("criterion.failed", EventPayload(criterion=trait, **failure.model_dump()))
            return None
        return await self._run_criterion(
            request,
            trait,
            trace,
            lambda: self._evidence_prompt(request, trait, analysis),
            lambda evidence: self._score_prompt(request, trait, evidence, analysis),
            lambda evidence, score: feedback_prompt(
                request, trait, evidence, analysis, score.score
            ),
            # Frozen evaluation baselines retain their original combined schema.
            assessor=partial(self._assess_task1_criterion, analysis=analysis)
            if self.score_schema is CriterionBandScore
            else None,
        )

    async def _assess_task1_criterion(
        self,
        request,
        trait,
        trace,
        evidence_messages,
        score_messages,
        feedback_messages,
        *,
        analysis,
    ):
        sources = {source.source_id: source for source in request_sources(request)}
        selection = await self._validated(
            evidence_messages, EvidenceSelection, sources, trait, "evidence", trace
        )
        evidence = resolve_evidence(selection, sources)
        # Preserve score input/evidence semantics. Public selector prose is not
        # verified feedback: only backend-resolved quotations/locations are shown.
        display_evidence = evidence.model_copy(deep=True)
        for item in display_evidence.evidence:
            item.assessment = (
                f"Trích dẫn từ đoạn {sources[item.source_id].paragraph_index} của bài viết."
            )
        await trace(
            "criterion.evidence.completed",
            EventPayload(criterion=trait, evidence=display_evidence.evidence),
        )
        score = await self._validated(
            score_messages(evidence), CriterionBandScore, sources, trait, "score", trace
        )
        self.states[trait].band_score = score
        await self._feedback_started(trait, score, display_evidence, trace)
        annotations = []
        feedback_status = "COMPLETED"
        try:
            raw = await self._validated(
                feedback_messages(evidence, score),
                RawTask1FeedbackDraft,
                sources,
                trait,
                "feedback",
                trace,
            )
            draft, issues = normalize_task1_feedback(raw, sources, trait, score.score, analysis)
            for reason, items in (
                ("FEEDBACK_PRESENTATION_NORMALIZED", issues.normalized),
                ("FEEDBACK_OBSERVATION_DROPPED", issues.dropped),
            ):
                if items:
                    self.states[trait].diagnostics.append(
                        OutputDiagnostic(
                            stage="feedback",
                            criterion=trait,
                            reason=reason,
                            attempt=1,
                            validation_issues=items[:8],
                        )
                    )
                    logger.info(
                        "Task1 explanation validation: criterion=%s reason=%s items=%s",
                        trait,
                        reason,
                        len(items),
                    )
            display, grounded_evidence = render_task1_feedback(draft, sources)
            annotations = build_writing_annotations(
                request.response, sources, trait, draft.observations
            )
            if grounded_evidence.evidence:
                display_evidence = grounded_evidence
        except ProviderFailure as exc:
            if (
                exc.code not in {"INVALID_PROVIDER_OUTPUT", "AI_PROVIDER_BAD_RESPONSE"}
                or exc.reason not in FEEDBACK_RECOVERABLE_REASONS
            ):
                raise
            self._explanation_fallback(trait, "feedback", 2)
            display = CriterionFeedbackOutput(
                feedback=FEEDBACK_FALLBACK, strengths=[], improvements=[]
            )
            feedback_status = "UNAVAILABLE"
        result = CriterionResult(
            score=score.score,
            **display.model_dump(),
            evidence=display_evidence.evidence,
            annotations=annotations,
            feedback_status=feedback_status,
        )
        await self._feedback_completed(trait, result, trace)
        return result

    def _task1_result(self, analysis):
        if self.failures:
            return None
        criteria = {trait: self.states[trait].result for trait in TRAITS}
        mean, overall = aggregate_ai_task_two(*(criteria[trait].score for trait in TRAITS))
        return Task1WritingResult(
            criteria=Criteria.model_validate(criteria),
            raw_mean=mean,
            overall_band=overall,
            task1_analysis=analysis,
            relevance=self.relevance,
        )
