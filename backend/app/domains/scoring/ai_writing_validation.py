"""Strict primary grounding and non-fatal optional explanation sanitization."""

import unicodedata
from decimal import Decimal
from typing import get_args

from pydantic import ValidationError
from pydantic_core import ErrorType

from app.domains.scoring.essay_sources import SourceSegment
from app.providers.writing_llm.base import (
    CalibrationDiagnosticReason,
    OutputFailureReason,
    ProviderFailure,
)
from app.schemas.writing_ai import (
    AssessmentStage,
    BandComparison,
    BandSupport,
    Evidence,
    EvidenceResult,
    EvidenceSelection,
    NextBandBlocker,
    ValidationIssue,
)


def safe_validation_issues(error: ValidationError) -> list[ValidationIssue]:
    """Expose fixed field names/indexes and built-in types, never rejected data.

    Extra-field locations come from model output and could themselves contain
    secrets or essay text. Mask unknown names instead of logging them verbatim.
    """
    fields = {
        "score",
        "feedback",
        "strengths",
        "improvements",
        "evidence",
        "source_id",
        "assessment",
        "focus",
        "quote",
        "calibration",
    }
    error_types = get_args(ErrorType)
    issues = []
    for item in error.errors(include_url=False, include_context=False, include_input=False)[:8]:
        path = []
        for part in item["loc"]:
            if isinstance(part, int) and part >= 0:
                path.append(str(part))
            elif isinstance(part, str) and part in fields:
                path.append(part)
            else:
                path.append("<extra>")
                break
        issues.append(
            ValidationIssue(
                field=".".join(path)[:120] if path else "<root>",
                validation_type=item["type"] if item["type"] in error_types else "validation_error",
            )
        )
    return issues


def validation_reason(
    error: ValidationError, stage: AssessmentStage | None = None
) -> OutputFailureReason:
    # Inspect types/field paths only. Never retain Pydantic input/context/messages.
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        location, kind = item["loc"], item["type"]
        if kind == "json_invalid":
            return "INVALID_JSON"
        if location and location[0] == "score":
            return "INVALID_HALF_BAND"
        if location == ("evidence",) and kind == "too_long":
            return "TOO_MANY_EVIDENCE_ITEMS"
        if location and location[0] == "evidence" and kind == "string_too_long":
            return "EVIDENCE_ITEM_TOO_LONG"
    if stage:
        return "EVIDENCE_SCHEMA_INVALID" if stage == "evidence" else "SCORE_SCHEMA_INVALID"
    return "SCHEMA_VALIDATION"


def resolve_evidence(
    selection: EvidenceSelection, sources: dict[str, SourceSegment]
) -> EvidenceResult:
    evidence = []
    for item in selection.evidence:
        source = sources.get(item.source_id)
        if source is None:
            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="EVIDENCE_UNKNOWN_SOURCE_ID")
        evidence.append(
            Evidence(source_id=source.source_id, quote=source.text, assessment=item.assessment)
        )
    return EvidenceResult(evidence=evidence)


def _calibration_items[Support: BandSupport](
    raw: object,
    model: type[Support],
    limit: int,
    sources: dict[str, SourceSegment],
    reasons: list[CalibrationDiagnosticReason],
) -> list[Support]:
    if not isinstance(raw, list):
        reasons.append("CALIBRATION_DROPPED")
        return []
    items = []
    if len(raw) > limit:
        reasons.append("CALIBRATION_DROPPED")
    for value in raw[:limit]:
        try:
            item = model.model_validate(value)
        except ValidationError:
            reasons.append("CALIBRATION_DROPPED")
            continue
        if item.source_id not in sources:
            reasons.append("CALIBRATION_SOURCE_DROPPED")
            continue
        items.append(item)
    return items


def sanitize_calibration(
    value: object, score: Decimal, sources: dict[str, SourceSegment]
) -> tuple[BandComparison | None, list[CalibrationDiagnosticReason]]:
    """Parse optional metadata separately, without changing/rejecting a score.

    Only safe reason codes escape. Malformed explanation text can discard the
    metadata entirely; unknown support/blocker IDs discard only those items.
    No comparison artifacts are required at any score, including high bands.
    """
    if value is None:
        return None, []
    if not isinstance(value, dict):
        return None, ["CALIBRATION_DROPPED"]
    reasons: list[CalibrationDiagnosticReason] = []
    upper = Decimal(int(score) + 1) if score < 9 else None
    if value.get("next_band") != upper:
        reasons.append("CALIBRATION_METADATA_NORMALIZED")
    data = {
        "next_band": upper,
        "support": _calibration_items(value.get("support", []), BandSupport, 3, sources, reasons),
        "next_band_blockers": _calibration_items(
            value.get("next_band_blockers", []), NextBandBlocker, 2, sources, reasons
        ),
        "comparison": value.get("comparison"),
        "high_band_justification": value.get("high_band_justification"),
    }
    if upper is None and data["next_band_blockers"]:
        data["next_band_blockers"] = []
        reasons.append("CALIBRATION_METADATA_NORMALIZED")
    try:
        result = BandComparison.model_validate(data)
    except ValidationError:
        result = None
        reasons.append("CALIBRATION_DROPPED")
    return result, list(dict.fromkeys(reasons))


def _canonical(text: str) -> tuple[str, list[tuple[int, int]]]:
    """NFD + ordinary whitespace only, retaining original character spans.

    NFD permits canonically equivalent composed/decomposed Unicode, without
    compatibility folding or changing punctuation. Each match is checked again
    against the original span so a partial grapheme cannot become a false quote.
    """
    output, spans = [], []
    index = 0
    while index < len(text):
        end = index + 1
        if text[index] in " \t\r\n":
            while end < len(text) and text[end] in " \t\r\n":
                end += 1
            normalized = " "
        else:
            while end < len(text) and unicodedata.combining(text[end]):
                end += 1
            normalized = unicodedata.normalize("NFD", text[index:end])
        output.extend(normalized)
        spans.extend([(index, end)] * len(normalized))
        index = end
    return "".join(output), spans


def original_quote(essay: str, quote: str) -> str:
    """Legacy v1/v2 compatibility only. Never called by source-ID inference."""
    if not quote.strip():
        raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="QUOTE_NOT_EXACT")
    if quote in essay:
        return quote
    source, spans = _canonical(essay)
    needle, _ = _canonical(quote)
    offset = source.find(needle)
    while offset >= 0:
        actual = essay[spans[offset][0] : spans[offset + len(needle) - 1][1]]
        if _canonical(actual)[0] == needle:
            return actual
        offset = source.find(needle, offset + 1)
    raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="QUOTE_NOT_EXACT")


def verify_evidence(result: EvidenceResult, essay: str) -> EvidenceResult:
    """Legacy quote payload tooling; v3 uses resolve_evidence instead."""
    # Revalidate lengths after recovering original whitespace/Unicode spans.
    resolved = EvidenceResult(
        evidence=[
            {"quote": original_quote(essay, item.quote), "assessment": item.assessment}
            for item in result.evidence
        ]
    )
    if any(len(item.quote) > 600 for item in resolved.evidence):
        # The old contract had a 600-character quote limit.
        raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="EVIDENCE_ITEM_TOO_LONG")
    return resolved
