"""One bounded auxiliary classifier. Any output/provider error fails open."""

import asyncio

from pydantic import ValidationError

from app.domains.scoring.ai_writing_validation import (
    resolve_evidence,
    safe_validation_issues,
    validation_reason,
)
from app.domains.scoring.essay_sources import segment_essay
from app.domains.scoring.mts_prompts import correction_message
from app.domains.scoring.writing_relevance import relevance_messages
from app.providers.writing_llm.base import (
    CompletionOptions,
    ProviderFailure,
    safe_finish_reason,
    validate_finish,
)
from app.schemas.writing_ai import (
    EventPayload,
    EvidenceChoice,
    EvidenceSelection,
    OutputDiagnostic,
    WritingRelevanceAssessment,
    WritingRelevanceResult,
)

RELEVANCE_MAX_TOKENS = 768
RELEVANCE_TIMEOUT_SECONDS = 30


async def classify_relevance(provider, request, reference, trace, usage, diagnostics, latency):
    await trace("relevance.started", EventPayload(criterion="ta", stage="relevance"))
    reason = "SCHEMA_VALIDATION"
    attempt = 1
    try:
        messages = relevance_messages(request, reference)
        sources = {s.source_id: s for s in segment_essay(request.response)}
        with latency.stage("relevance"):
            for attempt in (1, 2):
                finish, issues = None, []
                try:
                    with latency.attempt("relevance", "ta", attempt) as timing:
                        async with asyncio.timeout(RELEVANCE_TIMEOUT_SECONDS):
                            completion = await provider.complete(
                                messages + ([correction_message(reason)] if attempt == 2 else []),
                                WritingRelevanceAssessment.model_json_schema(),
                                options=CompletionOptions(max_tokens=RELEVANCE_MAX_TOKENS),
                            )
                        latency.completion(timing, completion.finish_reason, completion.usage)
                    usage.append(
                        {
                            k: timing[k]
                            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                            if k in timing
                        }
                    )
                    finish = safe_finish_reason(completion.finish_reason)
                    validate_finish(completion.finish_reason)
                    output = WritingRelevanceAssessment.model_validate_json(completion.text)
                    evidence = resolve_evidence(
                        EvidenceSelection(
                            evidence=[
                                EvidenceChoice(source_id=i, assessment=output.reason)
                                for i in output.source_ids
                            ]
                        ),
                        sources,
                    )
                    result = WritingRelevanceResult(
                        verdict=output.verdict,
                        confidence=output.confidence,
                        reason=output.reason,
                        evidence=evidence.evidence,
                        short_circuit_applied=output.verdict == "WHOLLY_UNRELATED"
                        and output.confidence == "HIGH",
                    )
                    break
                except ValidationError as exc:
                    reason, issues = validation_reason(exc), safe_validation_issues(exc)
                except ProviderFailure as exc:
                    if exc.reason is None:
                        raise
                    reason, finish = exc.reason, exc.finish_reason or finish
                diagnostics.append(
                    OutputDiagnostic(
                        stage="relevance",
                        criterion="ta",
                        reason=reason,
                        attempt=attempt,
                        finish_reason=finish,
                        validation_issues=issues,
                    )
                )
            else:
                result = None
    except Exception:
        # Never serialize arbitrary exception text or provider content.
        diagnostics.append(
            OutputDiagnostic(
                stage="relevance",
                criterion="ta",
                reason="RELEVANCE_AUXILIARY_FAILED",
                attempt=attempt,
            )
        )
        result = None
    # Trace/persistence failures remain run failures, outside the fail-open boundary.
    if result is None:
        await trace(
            "relevance.failed",
            EventPayload(criterion="ta", stage="relevance", error_code="AI_RELEVANCE_FAILED"),
        )
    else:
        await trace(
            "relevance.completed", EventPayload(criterion="ta", stage="relevance", relevance=result)
        )
    return result
