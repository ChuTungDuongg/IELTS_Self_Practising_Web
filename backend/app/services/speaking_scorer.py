"""Holistic score-first scorer; durable ownership belongs to the worker callback."""

import json
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from decimal import Decimal

from pydantic import ValidationError

from app.domains.scoring.ielts_band import round_to_half
from app.domains.scoring.speaking_prompts import system_prompt
from app.providers.speaking_llm.base import Completion, CompletionOptions, SpeakingLLMProvider
from app.schemas.speaking_ai import FluencyEvidence
from app.schemas.speaking_grading import (
    CRITERIA,
    CriterionBandScore,
    CriterionEvidence,
    CriterionFeedback,
    CriterionResponseEvidence,
    CriterionResult,
    GradingPronunciationEvidence,
    SpeakingAttemptEvidence,
    SpeakingCriterion,
    SpeakingResponseEvidence,
)

_FLUENCY_LIMITATIONS = {
    "LEXICAL_DISFLUENCY_PROXIES",
    "WORD_TIMING_INCOMPLETE",
    "RECOVERY_GAP_BOUNDARIES_UNAVAILABLE",
}
_PR_LIMITATIONS = {
    "PHONEME_ALIGNMENT_UNAVAILABLE",
    "LINGUISTIC_STRESS_UNAVAILABLE",
    "LISTENER_EFFORT_UNAVAILABLE",
    "ASR_CONFIDENCE_PROXY_ONLY",
    "PITCH_ENERGY_PROXIES",
    "RECOVERY_GAP_BOUNDARIES_UNAVAILABLE",
    "ALIGNMENT_INCOMPLETE",
    "AUDIO_UNAVAILABLE",
    "AUDIO_QUALITY_UNAVAILABLE",
    "LOW_EVIDENCE",
}


def build_attempt_evidence(responses: Iterable[Mapping]) -> SpeakingAttemptEvidence:
    """Project explicitly authored/ASR/P5 fields; runtime notes cannot cross this boundary."""
    rows = []
    for response in responses:
        # The outer allowlist is deliberate: ORM/runtime dictionaries also hold notes/paths.
        row = {
            key: response[key] for key in SpeakingResponseEvidence.model_fields if key in response
        }
        feature = row.get("features")
        if feature is not None and hasattr(feature, "model_dump"):
            row["features"] = feature.model_dump(
                exclude={
                    "quality": {
                        "metrics": {
                            "silence_seconds",
                            "speech_ratio",
                            "silence_ratio",
                        }
                    }
                }
            )
        elif isinstance(feature, dict):
            # Persisted P5 dumps can contain these computed presentation fields.
            # Remove only those known derivatives; unknown nested fields still fail validation.
            quality = feature.get("quality")
            if isinstance(quality, dict) and isinstance(quality.get("metrics"), dict):
                metrics = {
                    key: value
                    for key, value in quality["metrics"].items()
                    if key not in {"silence_seconds", "speech_ratio", "silence_ratio"}
                }
                row["features"] = {**feature, "quality": {**quality, "metrics": metrics}}
        rows.append(row)
    return SpeakingAttemptEvidence.model_validate({"responses": rows})


def _pronunciation(row):
    source = row.features.pronunciation
    values = {name: getattr(source, name) for name in GradingPronunciationEvidence.model_fields}
    values["limitations"] = [value for value in source.limitations if value in _PR_LIMITATIONS]
    if source.status == "LOW_EVIDENCE" and "LOW_EVIDENCE" not in values["limitations"]:
        values["limitations"].append("LOW_EVIDENCE")
    return GradingPronunciationEvidence.model_validate(values)


def criterion_evidence(
    criterion: SpeakingCriterion,
    evidence: SpeakingAttemptEvidence,
) -> CriterionEvidence:
    if criterion not in CRITERIA:
        raise ValueError("Unsupported Speaking criterion")
    evidence = SpeakingAttemptEvidence.model_validate(evidence)
    responses = []
    for row in evidence.responses:
        values = {
            key: getattr(row, key)
            for key in (
                "response_id",
                "prompt_id",
                "part_number",
                "prompt_type",
                "prompt_text",
                "cue_points",
                "verbatim",
                "clean",
                "words",
            )
        }
        if criterion == "gra":
            # Punctuation/line boundaries only: preserve candidate words and grammar.
            # The final item contains the remaining text when the 200-item cap is reached.
            values["utterances"] = [
                segment.strip()
                for segment in re.split(
                    r"(?<=[.!?])\s+|\n+",
                    row.verbatim,
                    maxsplit=199,
                )
                if segment.strip()
            ]
        if row.features:
            values["quality_state"] = row.features.quality.state
            if criterion == "fc":
                fluency = row.features.fluency.model_dump()
                fluency["version"] = "fluency-v1"
                fluency["limitations"] = [
                    item for item in fluency["limitations"] if item in _FLUENCY_LIMITATIONS
                ]
                values["fluency"] = FluencyEvidence.model_validate(fluency)
            if criterion == "pr":
                values["pronunciation"] = _pronunciation(row)
        responses.append(CriterionResponseEvidence(**values))
    projected = CriterionEvidence(criterion=criterion, responses=responses)
    if len(projected.model_dump_json()) > 600000:
        raise ValueError("Attempt evidence budget exceeded")
    return projected


def pronunciation_assessable(evidence: SpeakingAttemptEvidence) -> bool:
    """No band rule: check actual audio evidence, not a claimed AVAILABLE flag."""
    for row in evidence.responses:
        feature = row.features
        if feature is None:
            return False
        quality, pronunciation = feature.quality, feature.pronunciation
        if not quality.assessable or quality.state != "AUDIO_OK":
            return False
        metrics = quality.metrics
        if metrics is None or metrics.duration_seconds <= 0 or metrics.speech_seconds <= 0:
            return False
        if pronunciation.status == "UNAVAILABLE":
            return False
        # LOW_EVIDENCE can still contain meaningful measured prosody, e.g. partial
        # alignment. Neither transcript-only confidence nor RMS alone is sufficient.
        if (
            pronunciation.acoustic_frame_count < 2
            or pronunciation.rms is None
            or pronunciation.rms <= 0
            or pronunciation.energy_cv is None
            or not (
                pronunciation.word_duration_cv is not None
                or pronunciation.word_energy_cv is not None
                or (
                    pronunciation.voiced_pitch_frames > 0
                    and pronunciation.pitch_mean_hz is not None
                )
            )
        ):
            return False
    return True


def speaking_overall(criteria: Mapping[str, float | Decimal | None]):
    """Equal criterion weights only; no question/Part arithmetic exists here."""
    if any(criteria.get(criterion) is None for criterion in CRITERIA):
        return None, None
    validated = []
    for criterion in CRITERIA:
        value = criteria[criterion]
        validated.append(
            CriterionBandScore(score=float(value) if isinstance(value, Decimal) else value)
        )
    raw_mean = sum(Decimal(str(item.score)) for item in validated) / Decimal(4)
    return float(raw_mean), float(round_to_half(raw_mean))


class _InvalidOutput(Exception):
    """No provider bodies or arbitrary exception strings retained."""


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidOutput()
        result[key] = value
    return result


def _invalid_constant(_):
    raise _InvalidOutput()


def _validate_output(completion, schema, maximum_bytes):
    if not isinstance(completion, Completion) or completion.finish_reason != "stop":
        raise _InvalidOutput()
    if not isinstance(completion.text, str) or len(completion.text.encode()) > maximum_bytes:
        raise _InvalidOutput()
    try:
        value = json.loads(
            completion.text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_invalid_constant,
        )
        return schema.model_validate(value)
    except (ValueError, ValidationError, TypeError, RecursionError):
        raise _InvalidOutput() from None


class SpeakingScorer:
    def __init__(
        self,
        provider: SpeakingLLMProvider,
        *,
        score_max_tokens=192,
        feedback_max_tokens=1024,
    ):
        if type(score_max_tokens) is not int or not 128 <= score_max_tokens <= 256:
            raise ValueError("Invalid Speaking score output cap")
        if type(feedback_max_tokens) is not int or not 256 <= feedback_max_tokens <= 2048:
            raise ValueError("Invalid Speaking feedback output cap")
        self.provider = provider
        self.score_options = CompletionOptions(max_tokens=score_max_tokens)
        self.feedback_options = CompletionOptions(max_tokens=feedback_max_tokens)

    async def score_criterion(
        self,
        criterion: SpeakingCriterion,
        evidence: SpeakingAttemptEvidence,
        checkpoint: Callable[[CriterionResult], Awaitable[None]],
    ) -> CriterionResult:
        projected = criterion_evidence(criterion, evidence)
        if any(
            row.features is not None
            and (not row.features.quality.assessable or row.features.quality.state != "AUDIO_OK")
            for row in evidence.responses
        ):
            return CriterionResult(
                criterion=criterion,
                status="UNAVAILABLE",
                feedback_status="UNAVAILABLE",
                error_code="SPEAKING_AUDIO_UNASSESSABLE",
                evidence=projected,
            )
        if criterion == "pr" and not pronunciation_assessable(evidence):
            return CriterionResult(
                criterion=criterion,
                status="UNAVAILABLE",
                feedback_status="UNAVAILABLE",
                error_code="SPEAKING_PR_UNASSESSABLE",
                evidence=projected,
            )
        for repair in (False, True):
            messages = [
                {"role": "system", "content": system_prompt(criterion, repair=repair)},
                {"role": "user", "content": projected.model_dump_json(exclude_none=True)},
            ]
            try:
                completion = await self.provider.complete(
                    messages,
                    CriterionBandScore.model_json_schema(),
                    options=self.score_options,
                )
            except Exception:
                return CriterionResult(
                    criterion=criterion,
                    status="FAILED",
                    feedback_status="UNAVAILABLE",
                    error_code="SPEAKING_AI_PROVIDER_FAILED",
                    evidence=projected,
                )
            try:
                score = _validate_output(completion, CriterionBandScore, 1024)
                break
            except _InvalidOutput:
                if repair:
                    return CriterionResult(
                        criterion=criterion,
                        status="FAILED",
                        feedback_status="UNAVAILABLE",
                        error_code="SPEAKING_AI_INVALID_SCORE",
                        evidence=projected,
                    )
        stored = CriterionResult(
            criterion=criterion,
            status="SCORE_READY",
            score=score.score,
            evidence=projected,
        )
        # Do not catch checkpoint failures: no feedback may start before durable commit.
        await checkpoint(stored)
        return await self.feedback_for_scored(criterion, evidence, stored)

    async def feedback_for_scored(
        self,
        criterion: SpeakingCriterion,
        evidence: SpeakingAttemptEvidence,
        stored: CriterionResult,
    ) -> CriterionResult:
        """Resume after a worker restart without re-scoring a checkpointed band."""
        stored = CriterionResult.model_validate(stored)
        projected = criterion_evidence(criterion, evidence)
        if stored.score is None or stored.criterion != criterion or stored.evidence != projected:
            raise ValueError("Stored Speaking score evidence does not match")
        messages = [
            {"role": "system", "content": system_prompt(criterion, feedback=True)},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "persisted_score": stored.score,
                        "evidence": projected.model_dump(mode="json", exclude_none=True),
                    }
                ),
            },
        ]
        try:
            completion = await self.provider.complete(
                messages,
                CriterionFeedback.model_json_schema(),
                options=self.feedback_options,
            )
            feedback = _validate_output(completion, CriterionFeedback, 12000)
        except Exception:
            return CriterionResult(
                criterion=criterion,
                status="FEEDBACK_FAILED",
                score=stored.score,
                feedback_status="FAILED",
                error_code="SPEAKING_AI_FEEDBACK_FAILED",
                feedback=CriterionFeedback(
                    feedback="Your score was saved. Feedback is temporarily unavailable.",
                    strengths=[],
                    improvements=[],
                ),
                evidence=projected,
            )
        return CriterionResult(
            criterion=criterion,
            status="COMPLETED",
            score=stored.score,
            feedback_status="READY",
            feedback=feedback,
            evidence=projected,
        )
