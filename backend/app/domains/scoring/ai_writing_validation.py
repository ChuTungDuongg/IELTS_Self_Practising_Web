"""Safe validation reasons and conservative recovery of original essay quotations."""

import unicodedata

from pydantic import ValidationError

from app.providers.writing_llm.base import OutputFailureReason, ProviderFailure
from app.schemas.writing_ai import EvidenceResult


def validation_reason(error: ValidationError) -> OutputFailureReason:
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
    return "SCHEMA_VALIDATION"


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
    # Revalidate lengths after recovering original whitespace/Unicode spans.
    return EvidenceResult(
        evidence=[
            {"quote": original_quote(essay, item.quote), "assessment": item.assessment}
            for item in result.evidence
        ]
    )
