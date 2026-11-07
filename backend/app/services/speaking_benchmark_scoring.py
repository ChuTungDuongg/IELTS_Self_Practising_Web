"""Durable score-first orchestration over the sole production SpeakingScorer."""

from app.schemas.speaking_grading import CRITERIA, CriterionResult
from app.services.speaking_audio import fingerprint
from app.services.speaking_scorer import SpeakingScorer, criterion_evidence, speaking_overall


async def score_attempt(evidence, provider, ledger, config, settings):
    scorer = SpeakingScorer(
        provider,
        score_max_tokens=settings.speaking_ai_score_max_tokens,
        feedback_max_tokens=settings.speaking_ai_feedback_max_tokens,
    )
    results = {}
    for criterion in CRITERIA:
        identity = fingerprint(
            [config["scorer"], criterion_evidence(criterion, evidence).model_dump(mode="json")]
        )
        cached = await ledger.cached(f"criterion:{criterion}:final", identity)
        if cached:
            value = CriterionResult.model_validate(cached)
        else:
            score = await ledger.cached(f"criterion:{criterion}:score", identity)

            async def checkpoint(value, criterion=criterion, identity=identity):
                await ledger.save_cpu(
                    f"criterion:{criterion}:score", identity, value.model_dump(mode="json")
                )

            value = (
                await scorer.feedback_for_scored(
                    criterion, evidence, CriterionResult.model_validate(score)
                )
                if score
                else await scorer.score_criterion(criterion, evidence, checkpoint)
            )
            # A failed feedback has a reusable score, but must remain eligible for
            # explicit recovery in a new run instead of being cached as success.
            if value.status in {"COMPLETED", "UNAVAILABLE"}:
                await ledger.save_cpu(
                    f"criterion:{criterion}:final", identity, value.model_dump(mode="json")
                )
        results[criterion] = value
    bands = {key: value.score for key, value in results.items()}
    _, overall = speaking_overall(bands)
    bands["overall"] = float(overall) if overall is not None else None
    return {
        "bands": bands,
        "criteria": {
            key: value.model_dump(mode="json", exclude={"evidence"})
            for key, value in results.items()
        },
        "limitations": [value.error_code for value in results.values() if value.error_code],
        "advisory": True,
    }
