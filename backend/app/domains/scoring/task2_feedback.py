"""Conservative Task 2 observation validation and public display assembly.

Source checks prove location and exact wording, not linguistic truth. No feedback
field participates in scoring; the accepted band is used only for consistency.
"""

import re
import unicodedata
from decimal import Decimal

from app.domains.scoring.ai_writing_normalization import normalize_feedback
from app.domains.scoring.essay_sources import SourceSegment
from app.providers.writing_llm.base import ProviderFailure
from app.schemas.writing_ai import (
    CriterionFeedbackOutput,
    Evidence,
    EvidenceResult,
    Task2FeedbackDraft,
    Trait,
)

_MODEL_LOCATION = re.compile(
    r"\bP[1-9]\d*S[1-9]\d*\b|\b(?:đoạn|câu|paragraph|sentence)\s*\d+", re.IGNORECASE
)
_BAND = re.compile(r"\bband\s*[:=–-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)


def _trivial_normalization(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def validate_task2_feedback(
    draft: Task2FeedbackDraft, sources: dict[str, SourceSegment], trait: Trait, score: Decimal
) -> Task2FeedbackDraft:
    accepted = []
    for item in draft.observations:
        source = sources.get(item.source_id)
        if source is None:
            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="EVIDENCE_UNKNOWN_SOURCE_ID")
        if item.original_span is not None and item.original_span not in source.text:
            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="QUOTE_NOT_EXACT")
        if item.original_span is not None and not item.original_span.strip():
            continue
        for text in (item.observation, item.suggested_revision or ""):
            if _MODEL_LOCATION.search(text):
                raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="FEEDBACK_SCHEMA_INVALID")
            if any(Decimal(m[1].replace(",", ".")) != score for m in _BAND.finditer(text)):
                raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="FEEDBACK_SCORE_MISMATCH")
        if item.confidence == "LOW":
            continue
        if item.kind in {"ERROR", "LIMITATION"} and item.confidence != "HIGH":
            continue
        if item.kind == "ERROR" and trait in {"gra", "lr"} and item.original_span is None:
            continue
        if item.suggested_revision is not None:
            if item.original_span is None or _trivial_normalization(
                item.original_span
            ) == _trivial_normalization(item.suggested_revision):
                continue
        if item.kind == "OPTIONAL_REFINEMENT" and (
            item.original_span is None or item.suggested_revision is None
        ):
            continue
        if item not in accepted:
            accepted.append(item)
    # Stable source order, independent of the model's observation ordering.
    accepted.sort(key=lambda item: (sources[item.source_id].start, item.kind, item.observation))
    return Task2FeedbackDraft(observations=accepted)


def render_task2_feedback(
    draft: Task2FeedbackDraft, sources: dict[str, SourceSegment]
) -> tuple[CriterionFeedbackOutput, EvidenceResult]:
    strengths, improvements, texts, evidence = [], [], [], []
    for item in draft.observations:
        source = sources[item.source_id]
        if item.kind == "OPTIONAL_REFINEMENT":
            # Never present model-authored error prose under an optional label.
            text = f"Gợi ý tùy chọn: có thể diễn đạt «{item.original_span}» thành «{item.suggested_revision}» nếu phù hợp với ý định của bạn."
        else:
            text = item.observation
            if item.suggested_revision is not None:
                text += f" Có thể sửa thành «{item.suggested_revision}»."
        text = normalize_feedback(text, 240)
        bullet = normalize_feedback(f"Đoạn {source.paragraph_index}: {text}", 240)
        target = strengths if item.kind == "STRENGTH" else improvements
        if len(target) < 3:
            target.append(bullet)
            texts.append(text)
            evidence.append(
                Evidence(source_id=source.source_id, quote=source.text, assessment=bullet)
            )
    summary = (
        normalize_feedback(" ".join(texts), 800)
        if texts
        else "Chưa xác định được nhận xét cụ thể đủ chắc chắn cho tiêu chí này."
    )
    return CriterionFeedbackOutput(
        feedback=summary, strengths=strengths, improvements=improvements
    ), EvidenceResult(evidence=evidence)
