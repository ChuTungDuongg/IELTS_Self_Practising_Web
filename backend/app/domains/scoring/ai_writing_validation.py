"""v3 ID resolution; legacy quote recovery is isolated below for old payload tools."""

import unicodedata

from pydantic import ValidationError

from app.domains.scoring.essay_sources import SourceSegment
from app.providers.writing_llm.base import OutputFailureReason, ProviderFailure
from app.schemas.writing_ai import (
    AssessmentStage,
    Evidence,
    EvidenceResult,
    EvidenceSelection,
    ScoringOutput,
)


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
        if stage == "scoring" and (
            kind == "value_error" and not location or location and location[0] == "calibration"
        ):
            return "SCORE_CALIBRATION_INVALID"
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


def validate_calibration(result: ScoringOutput, sources: dict[str, SourceSegment]) -> None:
    # Validate grounding only. Severity is qualitative evidence for LLM holistic
    # descriptor matching, never a deterministic cap, penalty or score formula.
    for item in [*result.calibration.support, *result.calibration.next_band_blockers]:
        if item.source_id not in sources:
            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="SCORE_CALIBRATION_INVALID")


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
    """Legacy v1/v2 compatibility only. Never called by the v3 inference pipeline."""
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
