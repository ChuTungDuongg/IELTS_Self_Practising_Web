"""Conservative Task 2 observation validation and public display assembly.

Source checks prove location and exact wording, not linguistic truth. No feedback
field participates in scoring; the accepted band is used only for consistency.
"""

import re
import unicodedata
from decimal import Decimal

from pydantic import ValidationError

from app.domains.scoring.ai_writing_normalization import normalize_feedback
from app.domains.scoring.essay_sources import SourceSegment
from app.domains.scoring.task2_explanations import ExplanationIssues
from app.schemas.writing_ai import (
    CriterionFeedbackOutput,
    Evidence,
    EvidenceResult,
    RawTask2FeedbackDraft,
    RawTask2FeedbackObservation,
    Task2FeedbackDraft,
    Task2FeedbackObservation,
    Trait,
    ValidationIssue,
)

_MODEL_LOCATION = re.compile(
    r"\bP[1-9]\d*S[1-9]\d*\b|\b(?:đoạn|câu|paragraph|sentence)\s*\d+", re.IGNORECASE
)
_BAND = re.compile(r"\bband\s*[:=–-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)


def _trivial_normalization(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def normalize_task2_feedback(
    draft: RawTask2FeedbackDraft, sources: dict[str, SourceSegment], trait: Trait, score: Decimal
) -> tuple[Task2FeedbackDraft, ExplanationIssues]:
    issues = ExplanationIssues()
    accepted = []
    if len(draft.observations) > 6:
        issues.normalized.append(ValidationIssue(field="observations", validation_type="too_long"))
    for index, value in enumerate(draft.observations):
        if len(accepted) == 6:
            break
        prefix = f"observations.{index}"
        try:
            item = RawTask2FeedbackObservation.model_validate(value)
        except ValidationError as error:
            issues.invalid_item(prefix, error)
            continue
        source = sources.get(item.source_id)
        if source is None or len(source.text) > 12000:
            issues.drop(f"{prefix}.source_id")
            continue
        # Inspect complete prose BEFORE display truncation: unsafe claims at the
        # end of oversized text must not be hidden by clipping.
        prose = (item.observation, item.suggested_revision or "")
        if any(
            _MODEL_LOCATION.search(text)
            or any(Decimal(match[1].replace(",", ".")) != score for match in _BAND.finditer(text))
            for text in prose
        ):
            issues.drop(f"{prefix}.observation")
            continue
        if item.confidence == "LOW":
            issues.drop(f"{prefix}.confidence")
            continue
        if item.kind in {"ERROR", "LIMITATION"} and item.confidence != "HIGH":
            issues.drop(f"{prefix}.confidence")
            continue
        span, revision = item.original_span, item.suggested_revision
        if span is not None and (not span.strip() or span not in source.text):
            if item.kind not in {"STRENGTH", "LIMITATION"}:
                issues.drop(f"{prefix}.original_span")
                continue
            # A source-linked observation can survive an unusable optional quote;
            # its dependent rewrite cannot. Never clip a quote into exactness.
            issues.normalized.append(
                ValidationIssue(field=f"{prefix}.original_span", validation_type="value_error")
            )
            span = revision = None
        if item.kind == "ERROR" and trait in {"gra", "lr"} and span is None:
            issues.drop(f"{prefix}.original_span")
            continue
        if revision is not None:
            if (
                span is None
                or not revision.strip()
                or _trivial_normalization(span) == _trivial_normalization(revision)
            ):
                issues.drop(f"{prefix}.suggested_revision")
                continue
        if item.kind == "OPTIONAL_REFINEMENT" and (span is None or revision is None):
            issues.drop(f"{prefix}.suggested_revision")
            continue
        text = issues.bound(item.observation, 240, f"{prefix}.observation")
        if not text:
            issues.drop(f"{prefix}.observation", "string_too_short")
            continue
        revision = (
            issues.bound(revision, 240, f"{prefix}.suggested_revision")
            if revision is not None
            else None
        )
        item = Task2FeedbackObservation(
            source_id=item.source_id,
            kind=item.kind,
            observation=text,
            original_span=span,
            suggested_revision=revision,
            confidence=item.confidence,
        )
        if item not in accepted:
            accepted.append(item)
    # Stable source order, independent of the model's observation ordering.
    accepted.sort(key=lambda item: (sources[item.source_id].start, item.kind, item.observation))
    return Task2FeedbackDraft(observations=accepted), issues


def validate_task2_feedback(
    draft: Task2FeedbackDraft, sources: dict[str, SourceSegment], trait: Trait, score: Decimal
) -> Task2FeedbackDraft:
    """Apply the same conservative policy to already-bounded internal drafts."""
    raw = RawTask2FeedbackDraft.model_validate(draft.model_dump())
    return normalize_task2_feedback(raw, sources, trait, score)[0]


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
