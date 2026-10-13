"""A small fail-closed linguistic check, independent of the accepted band."""

import asyncio
import logging

from app.domains.scoring.task1_feedback import apply_language_verification
from app.domains.scoring.task1_prompts import language_verification_prompt
from app.providers.writing_llm.base import CompletionOptions, ProviderFailure, validate_finish
from app.schemas.task1_feedback import Task1LanguageFeedbackVerification
from app.schemas.writing_ai import OutputDiagnostic
from app.services.writing_execution import TraceFailure

logger = logging.getLogger(__name__)
LANGUAGE_VERIFICATION_MAX_TOKENS = 384
LANGUAGE_VERIFICATION_TIMEOUT_SECONDS = 30


async def verify_language_feedback(provider, request, trait, draft, sources, state, latency):
    if trait not in {"lr", "gra"} or not any(
        item.kind in {"ERROR", "LIMITATION"} for item in draft.observations
    ):
        return draft
    try:
        with latency.stage("feedback", trait):
            with latency.attempt("feedback", trait, 1) as timing:
                try:
                    async with asyncio.timeout(LANGUAGE_VERIFICATION_TIMEOUT_SECONDS):
                        completion = await provider.complete(
                            language_verification_prompt(request, trait, draft, sources),
                            Task1LanguageFeedbackVerification.model_json_schema(),
                            options=CompletionOptions(max_tokens=LANGUAGE_VERIFICATION_MAX_TOKENS),
                        )
                except ProviderFailure as exc:
                    latency.completion(timing, exc.finish_reason, exc.usage)
                    if exc.usage:
                        state.usage.append(exc.usage)
                    raise
                latency.completion(timing, completion.finish_reason, completion.usage)
            state.usage.append(completion.usage)
            validate_finish(completion.finish_reason)
            verification = Task1LanguageFeedbackVerification.model_validate_json(completion.text)
            return apply_language_verification(draft, verification)
    except TraceFailure:
        raise
    except Exception:
        # Cancellation still propagates; content, provider bodies and decisions
        # never enter the learner DTO or diagnostic. No auxiliary retries.
        state.diagnostics.append(
            OutputDiagnostic(
                stage="feedback",
                criterion=trait,
                reason="LANGUAGE_FEEDBACK_VERIFICATION_UNAVAILABLE",
                attempt=1,
            )
        )
        logger.info("Task1 language verification unavailable: criterion=%s", trait)
        return draft.model_copy(
            update={
                "observations": [item for item in draft.observations if item.kind == "STRENGTH"]
            }
        )
