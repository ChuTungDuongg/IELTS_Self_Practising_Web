"""Holistic score-first scorer; durable ownership belongs to the worker callback."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import replace
from decimal import Decimal
from typing import get_args

from pydantic import ValidationError

from app.domains.scoring.ielts_band import round_to_half
from app.domains.scoring.speaking_prompts import system_prompt
from app.providers.speaking_llm.base import Completion, CompletionOptions, SpeakingLLMProvider
from app.providers.writing_llm.base import (
    OutputFailureReason,
    ProviderFailure,
    safe_completion_usage,
    safe_finish_reason,
    safe_inference_attempts,
)
from app.schemas.speaking_ai import FluencyEvidence
from app.schemas.speaking_grading import (
    CRITERIA,
    CriterionBandScore,
    CriterionEvidence,
    CriterionFeedback,
    CriterionFeedbackInput,
    CriterionResponseEvidence,
    CriterionResult,
    GradingHybridPronunciationEvidence,
    GradingPronunciationEvidence,
    SpeakingAttemptEvidence,
    SpeakingCriterion,
    SpeakingResponseEvidence,
)

_FLUENCY_LIMITATIONS = {
    "RECOVERY_GAPS_UNKNOWN",
    "ASR_DISFLUENCIES_NOT_GUARANTEED",
    "PLAYBACK_MAPPING_UNAVAILABLE",
    "VAD_UNAVAILABLE",
    "VAD_SPEECH_ESTIMATE",
    "VAD_WORD_TIMING_DISAGREEMENT",
    "VAD_CAPACITY_EXCEEDED",
    "LEXICAL_DISFLUENCY_PROXIES",
    "WORD_TIMING_INCOMPLETE",
    "RECOVERY_GAP_BOUNDARIES_UNAVAILABLE",
}
_PR_LIMITATIONS = {
    "PROVIDER_MEASUREMENT_NOT_GROUND_TRUTH",
    "ACCENT_FALSE_POSITIVES_UNCALIBRATED",
    "LOW_ACCURACY_DOES_NOT_IDENTIFY_SUBSTITUTION",
    "SPEECH_ANALYSIS_PARTIAL",
    "ASSESSED_DURATION_IS_RECOGNIZED_WINDOW",
    "PR_BAND_COVERAGE_UNCALIBRATED",
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

ProviderCallObserver = Callable[[dict], Awaitable[None]]


def safe_provider_call(record: Mapping) -> dict:
    """Keep only bounded, source-free completion accounting and fixed diagnostics."""
    criterion, stage = record.get("criterion"), record.get("stage")
    if criterion not in CRITERIA or stage not in ("score", "score_repair", "feedback"):
        raise ValueError("Invalid Speaking provider accounting stage")
    safe = {
        "criterion": criterion,
        "stage": stage,
        "finish_reason": safe_finish_reason(record.get("finish_reason")),
        "usage": safe_completion_usage(record.get("usage")),
    }
    code = record.get("provider_error_code")
    if code is not None:
        safe["provider_error_code"] = (
            code
            if isinstance(code, str) and code in ProviderFailure.MESSAGES
            else "SPEAKING_AI_PROVIDER_FAILED"
        )
    reason = record.get("reason")
    if isinstance(reason, str) and reason in get_args(OutputFailureReason):
        safe["reason"] = reason
    attempts = safe_inference_attempts(record.get("provider_attempts"))
    if attempts:
        safe["provider_attempts"] = attempts
    return safe


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


def _stratified_observations(records, budget):
    """Cover kinds/metrics and the whole timeline, never select only low provider scores."""
    groups = {}
    for record in records:
        groups.setdefault((record.kind, record.metric), []).append(record)
    selected = []
    for index, key in enumerate(sorted(groups)):
        group = sorted(groups[key], key=lambda o: (o.start_ms or 0, o.evidence_id))
        count = min(
            len(group), budget // max(1, len(groups)) + (index < budget % max(1, len(groups)))
        )
        if count == 1:
            selected.append(group[len(group) // 2])
            continue
        selected.extend(group[i * (len(group) - 1) // max(1, count - 1)] for i in range(count))
    return sorted(selected, key=lambda o: (o.start_ms or 0, o.evidence_id))


def _pronunciation(row, *, observation_budget=400):
    source = row.features.pronunciation
    values = {
        name: getattr(source, name)
        for name in GradingPronunciationEvidence.model_fields
        if hasattr(source, name)
    }
    values["limitations"] = [value for value in source.limitations if value in _PR_LIMITATIONS]
    if row.features.profile == "legacy":
        # Keep the historic projection stable when resuming an already checkpointed score.
        values["provider"] = values["version"] = None
    if source.status == "LOW_EVIDENCE" and "LOW_EVIDENCE" not in values["limitations"]:
        values["limitations"].append("LOW_EVIDENCE")
    if row.features.profile == "speaking_hybrid_v1":
        selected = _stratified_observations(source.observations, observation_budget)
        values.update(
            observations=selected,
            observation_count=len(source.observations),
            observations_selected=len(selected),
        )
        if len(selected) < len(source.observations):
            values["limitations"].append("OBSERVATIONS_STRATIFIED_SAMPLE")
        return GradingHybridPronunciationEvidence.model_validate(
            {
                key: value
                for key, value in values.items()
                if key in GradingHybridPronunciationEvidence.model_fields
            }
        )
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
                fluency["limitations"] = [
                    item for item in fluency["limitations"] if item in _FLUENCY_LIMITATIONS
                ]
                values["fluency"] = FluencyEvidence.model_validate(fluency)
            if criterion == "pr":
                values["pronunciation"] = _pronunciation(
                    row, observation_budget=max(1, 300 // len(evidence.responses))
                )
            if row.features.profile == "speaking_hybrid_v1":
                analyses = row.features.speech_analysis
                values["transcript_limitations"] = [
                    "ASR_IS_NOT_GROUND_TRUTH",
                    "ASR_DISFLUENCIES_NOT_GUARANTEED",
                ]
                if any(r.status != "COMPLETE" for r in analyses):
                    values["transcript_limitations"].append("SPEECH_ANALYSIS_PARTIAL")
                values["uncertain_word_ids"] = [
                    w.evidence_id
                    for r in analyses
                    for w in r.words
                    if w.recognition_confidence is not None and w.recognition_confidence < 0.6
                ]
                if criterion in {"gra", "lr", "fc"}:
                    mappings = {str(m.segment_id): m for m in row.features.timeline}
                    values["recognized_words"] = [
                        w.model_copy(
                            update={
                                "start_ms": w.start_ms
                                + mappings[a.source.segment_id].normalized_start_ms
                                if w.start_ms is not None and a.source.segment_id in mappings
                                else w.start_ms,
                                "end_ms": w.end_ms
                                + mappings[a.source.segment_id].normalized_start_ms
                                if w.end_ms is not None and a.source.segment_id in mappings
                                else w.end_ms,
                            }
                        )
                        for a in analyses
                        for w in a.words
                    ]
                    values["uncertain_regions"] = [
                        u.model_copy(
                            update={
                                "start_ms": u.start_ms
                                + mappings[a.source.segment_id].normalized_start_ms
                                if u.start_ms is not None and a.source.segment_id in mappings
                                else u.start_ms,
                                "end_ms": u.end_ms
                                + mappings[a.source.segment_id].normalized_start_ms
                                if u.end_ms is not None and a.source.segment_id in mappings
                                else u.end_ms,
                            }
                        )
                        for a in analyses
                        for u in a.uncertain_regions
                    ]
                if any(w.recognition_confidence is None for r in analyses for w in r.words):
                    values["transcript_limitations"].append("RECOGNITION_CONFIDENCE_UNKNOWN")
                if criterion == "gra":
                    values["utterances"] = [
                        u.lexical_text for r in analyses for u in r.utterances if u.lexical_text
                    ][:200] or None
        responses.append(CriterionResponseEvidence(**values))
    projected = CriterionEvidence(criterion=criterion, responses=responses)
    if len(projected.model_dump_json()) > 600000:
        raise ValueError("Attempt evidence budget exceeded")
    return projected


def pronunciation_assessable(evidence: SpeakingAttemptEvidence) -> bool:
    """No band rule: check actual audio evidence, not a claimed AVAILABLE flag."""
    if any(r.features and r.features.profile == "speaking_hybrid_v1" for r in evidence.responses):
        features = [r.features for r in evidence.responses]
        if any(
            not f
            or f.profile != "speaking_hybrid_v1"
            or not f.quality.assessable
            or f.pronunciation.status == "UNAVAILABLE"
            or not f.speech_analysis
            or any(a.status != "COMPLETE" for a in f.speech_analysis)
            for f in features
        ):
            return False
        duration = sum((f.pronunciation.assessed_speech_ms or 0) for f in features)
        word_count = sum(len(a.words) for f in features for a in f.speech_analysis)
        weighted_coverage = sum(
            (f.pronunciation.evidence_coverage or 0) * sum(len(a.words) for a in f.speech_analysis)
            for f in features
        ) / max(1, word_count)
        return (
            duration >= 20000
            and word_count >= 20
            and weighted_coverage >= 0.6
            and all(f.pronunciation.observations for f in features)
        )
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


def fluency_assessable(evidence: SpeakingAttemptEvidence) -> bool:
    hybrid = any(
        r.features and r.features.profile == "speaking_hybrid_v1" for r in evidence.responses
    )
    if not hybrid:
        return True  # Preserve historical legacy scoring behavior.
    return (
        all(
            r.features
            and r.features.profile == "speaking_hybrid_v1"
            and r.features.quality.assessable
            and r.features.fluency.temporal_eligible
            and r.features.speech_analysis
            and all(a.status == "COMPLETE" for a in r.features.speech_analysis)
            for r in evidence.responses
        )
        and sum(r.features.fluency.detected_speech_ms or 0 for r in evidence.responses) >= 5000
    )


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
        on_provider_call: ProviderCallObserver | None = None,
    ):
        if type(score_max_tokens) is not int or not 128 <= score_max_tokens <= 256:
            raise ValueError("Invalid Speaking score output cap")
        if type(feedback_max_tokens) is not int or not 256 <= feedback_max_tokens <= 2048:
            raise ValueError("Invalid Speaking feedback output cap")
        self.provider = provider
        self.score_options = CompletionOptions(max_tokens=score_max_tokens)
        self.feedback_options = CompletionOptions(max_tokens=feedback_max_tokens)
        self.on_provider_call = on_provider_call

    async def _observe_call(self, criterion, stage, outcome, observer):
        callback = observer if observer is not None else self.on_provider_call
        if callback is None:
            return
        record = {"criterion": criterion, "stage": stage}
        if isinstance(outcome, (Completion, ProviderFailure, asyncio.CancelledError)):
            record.update(
                usage=getattr(outcome, "usage", {}),
                finish_reason=getattr(outcome, "finish_reason", None),
                provider_attempts=getattr(outcome, "attempts", ()),
            )
        if isinstance(outcome, ProviderFailure):
            record.update(provider_error_code=outcome.code, reason=outcome.reason)
        elif isinstance(outcome, Exception):
            record["provider_error_code"] = "SPEAKING_AI_PROVIDER_FAILED"
        # Persistence/lease failures are deliberately outside provider error handling.
        await callback(safe_provider_call(record))

    async def score_criterion(
        self,
        criterion: SpeakingCriterion,
        evidence: SpeakingAttemptEvidence,
        checkpoint: Callable[[CriterionResult], Awaitable[None]],
        *,
        on_provider_call: ProviderCallObserver | None = None,
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
            from app.services.speaking_feedback import unavailable_feedback

            return CriterionResult(
                criterion=criterion,
                status="UNAVAILABLE",
                feedback_status="READY",
                error_code="SPEAKING_PR_UNASSESSABLE",
                feedback=unavailable_feedback("pr", evidence),
                evidence=projected,
            )
        if criterion == "fc" and not fluency_assessable(evidence):
            from app.services.speaking_feedback import unavailable_feedback

            return CriterionResult(
                criterion=criterion,
                status="UNAVAILABLE",
                feedback_status="READY",
                feedback=unavailable_feedback("fc", evidence),
                error_code="SPEAKING_FC_UNASSESSABLE",
                evidence=projected,
            )
        for repair in (False, True):
            messages = [
                {
                    "role": "system",
                    "content": system_prompt(
                        criterion,
                        repair=repair,
                        hybrid=any(
                            r.features and r.features.profile == "speaking_hybrid_v1"
                            for r in evidence.responses
                        ),
                    ),
                },
                {"role": "user", "content": projected.model_dump_json(exclude_none=True)},
            ]
            try:
                completion = await self.provider.complete(
                    messages,
                    CriterionBandScore.model_json_schema(),
                    options=replace(
                        self.score_options,
                        task="speaking",
                        stage="score",
                        criterion=criterion,
                        attempt=2 if repair else 1,
                    ),
                )
            except asyncio.CancelledError as error:
                if getattr(error, "usage", None) or getattr(error, "attempts", None):
                    await self._observe_call(
                        criterion, "score_repair" if repair else "score", error, on_provider_call
                    )
                raise
            except Exception as error:
                await self._observe_call(
                    criterion, "score_repair" if repair else "score", error, on_provider_call
                )
                return CriterionResult(
                    criterion=criterion,
                    status="FAILED",
                    feedback_status="UNAVAILABLE",
                    error_code="SPEAKING_AI_PROVIDER_FAILED",
                    evidence=projected,
                )
            await self._observe_call(
                criterion, "score_repair" if repair else "score", completion, on_provider_call
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
        return await self.feedback_for_scored(
            criterion, evidence, stored, on_provider_call=on_provider_call
        )

    async def feedback_for_scored(
        self,
        criterion: SpeakingCriterion,
        evidence: SpeakingAttemptEvidence,
        stored: CriterionResult,
        *,
        on_provider_call: ProviderCallObserver | None = None,
    ) -> CriterionResult:
        """Resume after a worker restart without re-scoring a checkpointed band."""
        stored = CriterionResult.model_validate(stored)
        projected = criterion_evidence(criterion, evidence)
        if stored.score is None or stored.criterion != criterion or stored.evidence != projected:
            raise ValueError("Stored Speaking score evidence does not match")
        messages = [
            {
                "role": "system",
                "content": system_prompt(
                    criterion,
                    feedback=True,
                    hybrid=any(
                        r.features and r.features.profile == "speaking_hybrid_v1"
                        for r in evidence.responses
                    ),
                ),
            },
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
                CriterionFeedbackInput.model_json_schema(),
                options=replace(
                    self.feedback_options, task="speaking", stage="feedback", criterion=criterion
                ),
            )
        except asyncio.CancelledError as error:
            if getattr(error, "usage", None) or getattr(error, "attempts", None):
                await self._observe_call(criterion, "feedback", error, on_provider_call)
            raise
        except Exception as error:
            await self._observe_call(criterion, "feedback", error, on_provider_call)
            completion = None
        else:
            await self._observe_call(criterion, "feedback", completion, on_provider_call)
        try:
            feedback_input = _validate_output(completion, CriterionFeedbackInput, 30000)
            from app.services.speaking_feedback import resolve_feedback

            feedback = resolve_feedback(criterion, evidence, feedback_input)
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
