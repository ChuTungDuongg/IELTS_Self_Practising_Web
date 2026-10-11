"""Text-only source claim extraction and verification after visual perception."""

import json

from app.domains.scoring.essay_sources import request_sources
from app.domains.scoring.task1_prompts import DATA_GUARD
from app.domains.scoring.task1_verification import verify_claim
from app.providers.writing_llm.base import ProviderFailure
from app.schemas.task1_claims import (
    ExtractedClaims,
    SemanticVerification,
    Task1Analysis,
    VerifiedClaim,
)
from app.schemas.task1_visual import ChartTableVisualReference, VisualReference, unique
from app.services.task1_grounding import Task1StructuredCompletion
from app.services.task1_input import Task1ScoringRequest


class Task1ClaimService(Task1StructuredCompletion):
    async def extract(
        self, request: Task1ScoringRequest, reference: VisualReference | None = None
    ) -> ExtractedClaims:
        sources = {s.source_id: s for s in request_sources(request)}
        identity = (
            [
                {
                    "component_id": component.id,
                    "kind": component.kind,
                    "state": component.state,
                    "categories": component.categories,
                    "series_names": [s.name for s in component.series],
                    "row_headers": component.row_headers,
                    "column_headers": component.column_headers,
                }
                for component in reference.components
            ]
            if isinstance(reference, ChartTableVisualReference)
            else []
        )

        def validate(output: ExtractedClaims) -> None:
            unique([claim.claim_id for claim in output.claims])
            if any(source not in sources for claim in output.claims for source in claim.source_ids):
                raise ValueError("Unknown essay source")

        return await self.structured(
            [
                {
                    "role": "system",
                    "content": f"{DATA_GUARD} Extract at most 12 visually checkable claims, including overview and potentially inaccurate claims. Do not extract grammar, cohesion or vocabulary quality. Use exact allowed essay source_ids. claim is a concise Vietnamese description; source quotes are resolved by backend. For deterministic checks, subject/other/category/state names must reproduce the relevant English labels, never invent component_id; leave it null unless known. visual_identity provides label identities only: extract assertions from the essay, never from the image labels. For a single-series pie with an explicit state, subject is the slice label and category is the state/year, not the generic series name. Cross-state pie checks leave component_id null; numeric changes use category/end_category, and direct comparisons use category/other_category. Split multi-part numeric assertions into individual claims. percentage_change is signed relative change, absolute_change is signed end-start; numeric value/rank needs an explicit category. Relations use labels; before means reachable directed order, connected means directed flow. If structured checking is not possible, set check=null. Schema: {json.dumps(ExtractedClaims.model_json_schema(mode='serialization'))}",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task_type": request.task_type.value,
                            "visual_identity": identity,
                            "essay_sources": [
                                {"source_id": source.source_id, "text": source.text}
                                for source in sources.values()
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            ExtractedClaims,
            validate,
            stage="claim_extraction",
        )

    async def verify(
        self, request: Task1ScoringRequest, extracted: ExtractedClaims, analysis: Task1Analysis
    ) -> bool:
        sources = {source.source_id: source for source in request_sources(request)}
        pending = []
        for claim in extracted.claims:
            verdict, explanation, evidence = verify_claim(
                claim, analysis.reference, analysis.derived_facts
            )
            selected = [sources[source] for source in claim.source_ids]
            quote = request.response[
                min(source.start for source in selected) : max(source.end for source in selected)
            ]
            analysis.claims.append(
                VerifiedClaim(
                    claim_id=claim.claim_id,
                    source_ids=claim.source_ids,
                    quote=quote,
                    claim=claim.claim,
                    verdict=verdict,
                    explanation=explanation,
                    evidence=evidence,
                )
            )
            if (
                claim.check is None
                and analysis.confidence in {"HIGH", "MEDIUM"}
                and not (analysis.cross_check and analysis.cross_check.disagreement_count)
            ):
                pending.append(claim)
        if not pending:
            return True
        try:

            def validate(output: SemanticVerification) -> None:
                unique([item.claim_id for item in output.items])
                if {item.claim_id for item in output.items} != {
                    claim.claim_id for claim in pending
                }:
                    raise ValueError("Missing or unknown claim")

            output = await self.structured(
                [
                    {
                        "role": "system",
                        "content": f"{DATA_GUARD} Verify only these semantic claims against the supplied structured reference. No image reinterpretation or arithmetic. Unknown/null/uncertain information means INSUFFICIENT_EVIDENCE, not contradiction. Return each claim_id exactly once, concise Vietnamese explanations. Schema: {json.dumps(SemanticVerification.model_json_schema(mode='serialization'))}",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "reference": analysis.reference.model_dump(mode="json"),
                                "claims": [claim.model_dump(mode="json") for claim in pending],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                SemanticVerification,
                validate,
                repair=False,
                stage="claim_verification",
            )
            for result in output.items:
                item = next(item for item in analysis.claims if item.claim_id == result.claim_id)
                item.verdict, item.explanation = result.verdict, result.explanation[:400]
            return True
        except ProviderFailure:
            return False
