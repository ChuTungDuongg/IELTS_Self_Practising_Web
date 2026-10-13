"""Shared deterministic annotations. SourceSegment offsets remain Python indices.

Public offsets use UTF-16 code units into exact saved text: no Unicode, newline,
or whitespace normalization. Grounding proves location, not linguistic truth.
"""

import hashlib
import json
import re

from app.domains.scoring.essay_sources import SourceSegment
from app.schemas.writing_ai import (
    AnnotationCategory,
    Task2FeedbackObservation,
    Trait,
    WritingAnnotation,
)

_CATEGORY_TERMS: tuple[tuple[AnnotationCategory, str], ...] = (
    ("spelling", r"spelling|chính tả"),
    ("word_formation", r"word.formation|cấu tạo từ|dạng từ"),
    ("punctuation", r"punctuation|dấu câu|dấu chấm|dấu phẩy|khoảng trắng"),
    ("collocation", r"collocation|kết hợp từ"),
    ("word_choice", r"word.choice|lựa chọn từ|dùng từ"),
)


def annotation_category(trait: Trait, message: str) -> AnnotationCategory | None:
    if trait not in {"gra", "lr"}:
        return None
    for category, pattern in _CATEGORY_TERMS:
        if re.search(pattern, message, re.I):
            if (trait == "gra" and category == "punctuation") or (
                trait == "lr" and category != "punctuation"
            ):
                return category
    return "grammar" if trait == "gra" else "lexical_precision"


def _utf16_offset(text: str) -> int:
    return len(text.encode("utf-16-le", errors="surrogatepass")) // 2


def build_writing_annotations(
    essay: str,
    sources: dict[str, SourceSegment],
    trait: Trait,
    observations: list[Task2FeedbackObservation],
) -> list[WritingAnnotation]:
    """Convert validated observations only; ambiguous spans stay in panel prose."""
    accepted: dict[tuple, WritingAnnotation] = {}
    priority = {"ERROR": 0, "LIMITATION": 1, "OPTIONAL_REFINEMENT": 2}
    for item in sorted(observations, key=lambda i: (priority.get(i.kind, 3), i.observation)):
        span = item.original_span
        source = sources.get(item.source_id)
        if (
            item.kind == "STRENGTH"
            or item.confidence == "LOW"
            or (item.kind == "ERROR" and item.confidence != "HIGH")
            or not span
            or source is None
            or source.start < 0
            or source.end <= source.start
            or essay[source.start : source.end] != source.text
        ):
            continue
        relative = source.text.find(span)
        # Include overlapping matches: 'aaa' contains two occurrences of 'aa'.
        if relative < 0 or source.text.find(span, relative + 1) >= 0:
            continue
        start, end = source.start + relative, source.start + relative + len(span)
        if essay[start:end] != span:
            continue
        start_offset, end_offset = _utf16_offset(essay[:start]), _utf16_offset(essay[:end])
        identity = (
            trait,
            item.kind,
            item.source_id,
            start_offset,
            end_offset,
            span,
            item.suggested_revision,
        )
        # Same issue at the same location does not need competing paraphrases.
        location = (start_offset, end_offset, item.suggested_revision)
        if location in accepted:
            continue
        identifier = hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest()[
            :24
        ]
        accepted[location] = WritingAnnotation(
            id=f"wa_{identifier}",
            criterion=trait,
            kind=item.kind,
            source_id=item.source_id,
            start_offset=start_offset,
            end_offset=end_offset,
            original_span=span,
            suggested_revision=item.suggested_revision,
            message=item.observation,
            confidence=item.confidence,
            category=annotation_category(trait, item.observation),
        )
    return sorted(accepted.values(), key=lambda a: (a.start_offset, a.end_offset, a.id))[:4]
