import logging

from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.domains.scoring.task1_facts import derive_facts
from app.domains.scoring.task1_prompts import evidence_prompt, score_prompt
from app.domains.writing.visual_families import visual_family
from app.providers.chart_derendering import ChartDerenderingProvider
from app.providers.writing_llm.base import LLMProvider, Message
from app.schemas.task1_claims import ExtractedClaims, Task1Analysis
from app.schemas.writing_ai import (
    TRAITS,
    Criteria,
    CriterionFailure,
    EventPayload,
    EvidenceResult,
    Task1WritingResult,
    Trait,
)
from app.services.mts_writing import MTSWritingScoringService, TraceCallback
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
    ) -> None:
        super().__init__(provider, max_concurrent_requests=max_concurrent_requests, latency=latency)
        self.chart_derenderer, self.chart_timeout = chart_derenderer, chart_timeout

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
        # None of these image/text extraction turns depend on each other's output.
        prepared = await gather_isolated(
            self._prepare_reference(request, analysis, grounding, trace),
            self._extract_claims(request, claim_service, trace, analysis),
        )
        if analysis.confidence != "UNUSABLE" and prepared[1] is not None:
            await self._verify_claims(request, prepared[1], analysis, claim_service, trace)

    async def _prepare_reference(self, request, analysis, grounding, trace):
        work = [self._ground(request, analysis, grounding, trace)]
        if specialist_eligible(request):
            work.append(
                extract_chart(
                    request, self.chart_derenderer, trace, self.chart_timeout, self.latency
                )
            )
        prepared = await gather_isolated(*work)
        if analysis.confidence != "UNUSABLE":
            if specialist_eligible(request):
                await apply_chart_cross_check(request, analysis, prepared[1], trace, self.latency)
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
                extracted = await claim_service.extract(request)
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
        )

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
        )
