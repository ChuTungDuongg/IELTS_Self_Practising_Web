"""Conservative Task 2 observation validation and public display assembly.

Source checks prove location and exact wording, not linguistic truth. No feedback
field participates in scoring; the accepted band is used only for consistency.
"""

import re
import unicodedata
from decimal import Decimal

from pydantic import ValidationError

from app.domains.scoring.essay_sources import SourceSegment, segment_essay
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
_STYLE_ONLY = re.compile(
    r"Oxford comma|serial comma|more (?:elegant|sophisticated|formal)|"
    r"(?:fancier|sophisticated) (?:word|synonym)|merely for (?:variety|variation)|"
    r"câu.{0,20}(?:quá dài|dài hơn)|trang trọng hơn|từ.{0,20}(?:cao cấp|học thuật) hơn",
    re.I,
)
_LEXICAL_ERROR = re.compile(r"spelling|word.formation|chính tả|cấu tạo từ|sai dạng từ", re.I)
_GRAMMAR_ERROR = re.compile(
    r"subject.verb agreement|verb (?:tense|form)|article error|clause structure|"
    r"hòa hợp.{0,30}(?:chủ ngữ|động từ)|chia động từ|thì động từ|mạo từ|dấu câu",
    re.I,
)
_OPTIONAL_ERROR_PROSE = re.compile(r"\b(?:error|wrong|incorrect|ungrammatical)\b|sai|lỗi", re.I)
_VARIANTS = {
    "colour": "color",
    "colours": "colors",
    "grey": "gray",
    "centre": "center",
    "centres": "centers",
    "labour": "labor",
    "neighbour": "neighbor",
    "neighbours": "neighbors",
    "behaviour": "behavior",
    "organise": "organize",
    "organised": "organized",
    "organisation": "organization",
    "analyse": "analyze",
    "travelling": "traveling",
    "travelled": "traveled",
    "programme": "program",
}
_COMMON_SYNONYMS = {
    frozenset(pair)
    for pair in [
        ("important", "significant"),
        ("help", "assist"),
        ("use", "utilise"),
        ("use", "utilize"),
        ("big", "large"),
        ("show", "demonstrate"),
        ("increase", "rise"),
        ("decrease", "fall"),
        ("many", "numerous"),
    ]
}


def _complete_text(text: str, limit: int) -> str:
    """Retain whole sentences only when an individual observation is oversized."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    ends = [
        source.end
        for source in segment_essay(text)
        if source.end <= limit and re.search(r"[.!?。！？][\"'”’»)}\]]*$", source.text)
    ]
    return text[: ends[-1]] if ends else ""


def _variant_normalization(text: str) -> str:
    return re.sub(r"\b[a-z]+\b", lambda m: _VARIANTS.get(m[0], m[0]), text.casefold())


def _unsupported_language_claim(item, source: SourceSegment, trait: Trait) -> bool:
    """Conservative false-positive guards, never a grammar checker or score rule.

    These reject recognizable unsupported claims; HIGH confidence alone cannot
    establish linguistic truth. Unknown valid alternatives are guarded in prompts.
    """
    if trait not in {"gra", "lr"} or item.kind == "STRENGTH":
        return False
    text, span, revision = item.observation, item.original_span, item.suggested_revision
    if (trait == "gra" and _LEXICAL_ERROR.search(text)) or (
        trait == "lr" and _GRAMMAR_ERROR.search(text)
    ):
        return True
    if _STYLE_ONLY.search(text):
        return True
    if span and revision:
        if _variant_normalization(span) == _variant_normalization(revision):
            return True
        if frozenset((span.casefold().strip(), revision.casefold().strip())) in _COMMON_SYNONYMS:
            return True
        # Optional serial-comma conventions are not errors or useful rewrites.
        if span.replace(",", "") == revision.replace(",", "") and re.search(
            r",?\s+(?:and|or)\b", span
        ):
            return True
    if trait == "gra":
        if (
            re.search(r"gerund|danh động từ|missing.{0,30}subject|thiếu.{0,30}chủ ngữ", text, re.I)
            and re.search(
                r"\b[A-Za-z]+ing\b.{0,100}\b(?:is|was|can|may|helps|requires)\b", source.text, re.I
            )
            and re.search(r"subject|chủ ngữ|missing|thiếu", text, re.I)
        ):
            return True
        if re.search(
            r"copular|linking verb|động từ nối|missing.{0,30}(?:verb|complement)|thiếu.{0,30}(?:động từ|bổ ngữ)",
            text,
            re.I,
        ) and re.search(
            r"\b(?:remain|remains|seem|seems|become|becomes|feel|feels|look|looks)\s+"
            r"(?:(?:a|an|the)\s+)?"
            r"(?:stable|reasonable|important|useful|clear|healthy|popular|effective)\b",
            source.text,
            re.I,
        ):
            return True
    return False


def select_feedback_observations(items, sources):
    """Select useful distinct items before source ordering; model order is irrelevant."""
    priority = {"ERROR": 0, "LIMITATION": 1, "STRENGTH": 2, "OPTIONAL_REFINEMENT": 3}
    selected, identities = [], set()
    for item in sorted(
        items,
        key=lambda i: (
            priority[i.kind],
            i.confidence != "HIGH",
            sources[i.source_id].start,
            i.original_span or "",
            i.observation,
            i.suggested_revision or "",
        ),
    ):
        identity = (
            (item.source_id, item.original_span, item.suggested_revision)
            if item.original_span is not None
            else (item.source_id, item.kind, item.observation.casefold())
        )
        source = sources[item.source_id].text
        if item.original_span and item.suggested_revision:
            offset = source.find(item.original_span)
            if offset >= 0 and source.find(item.original_span, offset + 1) < 0:
                # Two nested spans that produce the identical corrected source
                # describe the same issue, without fuzzy linguistic matching.
                corrected = (
                    source[:offset]
                    + item.suggested_revision
                    + source[offset + len(item.original_span) :]
                )
                identity = (item.source_id, "correction", corrected)
        if identity in identities:
            continue
        identities.add(identity)
        selected.append(item)
        if len(selected) == 4:
            break
    return sorted(
        selected, key=lambda i: (sources[i.source_id].start, priority[i.kind], i.observation)
    )


def _trivial_normalization(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def normalize_task2_feedback(
    draft: RawTask2FeedbackDraft, sources: dict[str, SourceSegment], trait: Trait, score: Decimal
) -> tuple[Task2FeedbackDraft, ExplanationIssues]:
    issues = ExplanationIssues()
    accepted = []
    if len(draft.observations) > 4:
        issues.normalized.append(ValidationIssue(field="observations", validation_type="too_long"))
    for index, value in enumerate(draft.observations):
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
        if _unsupported_language_claim(item, source, trait):
            issues.drop(f"{prefix}.observation")
            continue
        if item.kind in {"ERROR", "LIMITATION"} and item.confidence != "HIGH":
            issues.drop(f"{prefix}.confidence")
            continue
        span, revision = item.original_span, item.suggested_revision
        if span is not None and (not span.strip() or len(span) > 12000 or span not in source.text):
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
                or len(revision.strip()) > 240
                or _trivial_normalization(span) == _trivial_normalization(revision)
            ):
                issues.drop(f"{prefix}.suggested_revision")
                continue
        if item.kind == "OPTIONAL_REFINEMENT" and (span is None or revision is None):
            issues.drop(f"{prefix}.suggested_revision")
            continue
        text = _complete_text(item.observation, 240)
        if text != " ".join(item.observation.split()):
            issues.normalized.append(
                ValidationIssue(field=f"{prefix}.observation", validation_type="string_too_long")
            )
        if not text:
            issues.drop(f"{prefix}.observation", "string_too_short")
            continue
        if item.kind == "OPTIONAL_REFINEMENT":
            if _OPTIONAL_ERROR_PROSE.search(item.observation):
                issues.drop(f"{prefix}.observation")
                continue
            text = _complete_text(text, 240 - len("Gợi ý tùy chọn: "))
            if not text:
                issues.drop(f"{prefix}.observation", "string_too_long")
                continue
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
    return Task2FeedbackDraft(observations=select_feedback_observations(accepted, sources)), issues


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
            text = f"Gợi ý tùy chọn: {item.observation}"
        else:
            text = item.observation
        target = strengths if item.kind == "STRENGTH" else improvements
        target.append(text)
        texts.append(text)
        evidence.append(
            Evidence(
                source_id=source.source_id,
                quote=source.text,
                assessment=f"Đoạn {source.paragraph_index}: {text}",
            )
        )
    summary_items = []
    priority = {"ERROR": 0, "LIMITATION": 1, "STRENGTH": 2, "OPTIONAL_REFINEMENT": 3}
    summary_texts = [
        text
        for _, text in sorted(
            zip(draft.observations, texts, strict=True), key=lambda pair: priority[pair[0].kind]
        )
    ]
    for text in summary_texts[:2]:
        if len(" ".join([*summary_items, text])) > 800:
            break
        summary_items.append(text)
    summary = (
        " ".join(summary_items)
        or "Chưa xác định được nhận xét cụ thể đủ chắc chắn cho tiêu chí này."
    )
    return CriterionFeedbackOutput(
        feedback=summary, strengths=strengths, improvements=improvements
    ), EvidenceResult(evidence=evidence)
