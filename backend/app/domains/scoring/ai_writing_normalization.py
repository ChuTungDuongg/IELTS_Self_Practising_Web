"""Deterministic display normalization after strict semantic score validation."""

import re
import unicodedata

from pydantic import ValidationError

from app.domains.scoring.ai_writing_validation import safe_validation_issues
from app.schemas.writing_ai import RawScoringOutput, ScoringOutput, ValidationIssue


def normalize_feedback(text: str, max_chars: int = 800) -> str:
    """Keep an original Unicode prefix; prefer a nearby sentence/word boundary.

    Short text keeps all its content and internal spacing. Long text reserves
    one character for an ellipsis, without generating or rewriting feedback.
    """
    if max_chars < 1:
        raise ValueError("Text limit must be positive")
    text = text.strip()
    if len(text) <= max_chars:
        return text
    budget = max_chars - 1
    prefix = text[:budget]
    # A distant boundary would unnecessarily discard most of a valid paragraph.
    near = budget * 0.8
    sentences = list(re.finditer(r"[.!?。！？][\"'”’)]*(?=\s|$)", prefix))
    words = list(re.finditer(r"\s+", prefix))
    if sentences and sentences[-1].end() >= near:
        end = sentences[-1].end()
    elif words and words[-1].start() >= near:
        end = words[-1].start()
    else:
        end = budget
    # Avoid separating Vietnamese decomposed combining marks from their base.
    if end < len(text) and unicodedata.combining(text[end]):
        while end > 0 and unicodedata.combining(text[end]):
            end -= 1
    return text[:end].rstrip() + "…"


def normalize_bullets(values: list[str], max_items: int = 3, max_chars: int = 240) -> list[str]:
    items = []
    for value in values:
        if len(items) >= max_items:
            break
        if value.strip():
            items.append(normalize_feedback(value, max_chars))
    return items


def normalize_scoring_output(
    raw: RawScoringOutput,
) -> tuple[ScoringOutput, list[ValidationIssue]]:
    """Normalize display bounds, never score or semantic/structural failures.

    First check display bounds to retain safe field/type diagnostics. Only a
    validated raw core can enter this function; no dict/number-to-text coercion.
    """
    data = {
        "score": raw.score,
        "feedback": raw.feedback,
        "strengths": raw.strengths,
        "improvements": raw.improvements,
    }
    try:
        return ScoringOutput.model_validate(data), []
    except ValidationError as error:
        issues = safe_validation_issues(error)
    return ScoringOutput(
        score=raw.score,
        feedback=normalize_feedback(raw.feedback),
        strengths=normalize_bullets(raw.strengths),
        improvements=normalize_bullets(raw.improvements),
    ), issues
