import logging

from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.domains.scoring.task1_facts import derive_facts
from app.domains.scoring.task1_prompts import evidence_prompt, score_prompt
from app.domains.writing.visual_families import visual_family
from app.providers.chart_derendering import ChartDerenderingProvider
from app.providers.writing_llm.base import LLMProvider, ProviderFailure
from app.schemas.task1_claims import Task1Analysis
from app.schemas.writing_ai import (
    TRAITS,
    Criteria,
    CriterionFailure,
    EventPayload,
    Task1WritingResult,
)
from app.services.mts_writing import MTSWritingScoringService, TraceCallback
from app.services.task1_chart_cross_check import cross_check_chart
from app.services.task1_claims import Task1ClaimService
from app.services.task1_grounding import Task1VisualGroundingService
from app.services.task1_input import Task1ScoringRequest

logger = logging.getLogger(__name__)


class Task1WritingScoringService(MTSWritingScoringService):
    """Independent criteria over one perception result; all score math stays shared."""

    def __init__(
        self,
        provider: LLMProvider,
        chart_derenderer: ChartDerenderingProvider | None = None,
        chart_timeout: float = 90,
    ) -> None:
        super().__init__(provider)
        self.chart_derenderer, self.chart_timeout = chart_derenderer, chart_timeout

    async def assess(
        self, request: Task1ScoringRequest, trace: TraceCallback
    ) -> Task1WritingResult | None:
        self.usage, self.diagnostics, self.failures = [], [], {}
        analysis = Task1Analysis(visual_family=visual_family(request.task_type).value)
        grounding = Task1VisualGroundingService(self.provider, self.usage, self.diagnostics)
        claim_service = Task1ClaimService(self.provider, self.usage, self.diagnostics)
        self.current_criterion, self.current_stage = "ta", "visual_grounding"
        logger.info(
            "Task1 visual grounding: chart_specialist_enabled=%s",
            str(request.chart_specialist.enabled).lower(),
        )
        await trace(
            "visual_grounding.started", EventPayload(criterion="ta", stage="visual_grounding")
        )
        try:
            output = await grounding.ground(request)
        except ProviderFailure:
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
                EventPayload(criterion="ta", stage="visual_grounding", task1_analysis=analysis),
            )
            self.current_stage = "chart_cross_check"
            await cross_check_chart(
                request, analysis, self.chart_derenderer, trace, self.chart_timeout
            )
            self.current_stage = "derived_facts"
            try:
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
                    EventPayload(criterion="ta", stage="derived_facts", task1_analysis=analysis),
                )
        if analysis.confidence != "UNUSABLE":
            self.current_stage = "claim_extraction"
            await trace(
                "claim_extraction.started", EventPayload(criterion="ta", stage="claim_extraction")
            )
            try:
                claims = await claim_service.extract(request)
                await trace(
                    "claim_extraction.completed",
                    EventPayload(criterion="ta", stage="claim_extraction"),
                )
                self.current_stage = "claim_verification"
                await trace(
                    "claim_verification.started",
                    EventPayload(criterion="ta", stage="claim_verification"),
                )
                if not await claim_service.verify(request, claims, analysis):
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
                            criterion="ta", stage="claim_verification", task1_analysis=analysis
                        ),
                    )
            except ProviderFailure:
                analysis.warnings.append("CLAIM_EXTRACTION_FAILED")
                await trace(
                    "claim_extraction.failed",
                    EventPayload(
                        criterion="ta",
                        stage="claim_extraction",
                        task1_analysis=analysis,
                        error_code="AI_CLAIM_EXTRACTION_FAILED",
                    ),
                )
        criteria = {}
        for trait in TRAITS:
            self.current_criterion, self.current_stage = trait, "evidence"
            await trace("criterion.started", EventPayload(criterion=trait))
            try:
                if trait == "ta" and analysis.confidence == "UNUSABLE":
                    self.current_stage = "visual_grounding"
                    raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE")
                result = await self.assess_criterion(
                    request,
                    trait,
                    trace,
                    evidence_prompt(request, trait, analysis),
                    lambda evidence, trait=trait: score_prompt(request, trait, evidence, analysis),
                )
                criteria[trait] = result
                await trace("criterion.completed", EventPayload(criterion=trait, result=result))
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
        if self.failures:
            return None
        mean, overall = aggregate_ai_task_two(*(criteria[trait].score for trait in TRAITS))
        return Task1WritingResult(
            criteria=Criteria.model_validate(criteria),
            raw_mean=mean,
            overall_band=overall,
            task1_analysis=analysis,
        )
