"""One bounded auxiliary classifier. Any output/provider error fails open."""

import asyncio
import json

from pydantic import ValidationError

from app.domains.scoring.ai_writing_validation import (
    resolve_evidence,
    safe_validation_issues,
    validation_reason,
)
from app.domains.scoring.essay_sources import request_sources
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
        if getattr(provider, "reasoned_inference", False):
            # Chat JSON mode does not transmit the vLLM guided schema. Keep this
            # OpenAI prompt change inside its output-policy identity namespace.
            messages[0]["content"] += "\nJSON schema: " + json.dumps(
                WritingRelevanceAssessment.model_json_schema()
            )
        sources = {s.source_id: s for s in request_sources(request)}
        with latency.stage("relevance"):
            for attempt in (1, 2):
                finish, issues = None, []
                try:
                    with latency.attempt("relevance", "ta", attempt) as timing:
                        async with asyncio.timeout(
                            None
                            if getattr(provider, "reasoned_inference", False)
                            else RELEVANCE_TIMEOUT_SECONDS
                        ):
                            completion = await provider.complete(
                                messages + ([correction_message(reason)] if attempt == 2 else []),
                                WritingRelevanceAssessment.model_json_schema(),
                                options=CompletionOptions(
                                    max_tokens=RELEVANCE_MAX_TOKENS,
                                    task="task1"
                                    if getattr(request, "task_number", 2) == 1
                                    else "task2",
                                    stage="relevance",
                                    criterion="ta",
                                    attempt=attempt,
                                ),
                            )
                        latency.completion(
                            timing, completion.finish_reason, completion.usage, completion.attempts
                        )
                    usage.append(completion.usage)
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
                    latency.completion(timing, exc.finish_reason, exc.usage, exc.attempts)
                    if exc.usage:
                        usage.append(exc.usage)
                    if exc.reason is None:
                        raise
                    if exc.reason in {
                        "COMPLETION_BUDGET_EXHAUSTED",
                        "PROVIDER_REFUSAL",
                        "PROVIDER_CONTENT_FILTER",
                    } or (
                        getattr(provider, "reasoned_inference", False)
                        and exc.reason
                        in {
                            "PROVIDER_FINISH_ABORT",
                            "PROVIDER_FINISH_ERROR",
                            "PROVIDER_FINISH_OTHER",
                        }
                    ):
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
