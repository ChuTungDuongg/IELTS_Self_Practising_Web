"""Legacy v1/v2 payload tools only; new inference is tested in test_mts_writing_v3."""

import pytest
from pydantic import ValidationError

from app.domains.scoring.ai_writing_validation import (
    original_quote,
    validation_reason,
    verify_evidence,
)
from app.providers.writing_llm.base import ProviderFailure
from app.schemas.writing_ai import EvidenceResult, TraitScore

ESSAY = "Fictional parks improve city life."


@pytest.mark.parametrize(
    "essay,quote,expected",
    [
        ("  Exact quote.  ", " Exact quote. ", " Exact quote. "),
        ("A café helps.", "A cafe\u0301 helps.", "A café helps."),
        ("A cafe\u0301 helps.", "A café helps.", "A cafe\u0301 helps."),
        (
            "Parks\r\nimprove  city\tlife.",
            "Parks improve city life.",
            "Parks\r\nimprove  city\tlife.",
        ),
    ],
)
def test_conservative_matching_displays_original_substring(essay, quote, expected):
    assert original_quote(essay, quote) == expected
    evidence = verify_evidence(
        EvidenceResult.model_validate(
            {"evidence": [{"quote": quote, "assessment": "Dẫn chứng phù hợp."}]}
        ),
        essay,
    )
    assert evidence.evidence[0].quote == expected
    assert evidence.evidence[0].quote in essay


@pytest.mark.parametrize(
    "essay,quote",
    [
        (ESSAY, "Parks make cities better."),
        ("It's clear.", "It’s clear."),
        ("A cafe\u0301 helps.", "A cafe helps."),
        ("Parks improve city life.", "Parks…city life."),
        (ESSAY, "   "),
    ],
)
def test_paraphrases_punctuation_changes_and_incomplete_unicode_rejected(essay, quote):
    with pytest.raises(ProviderFailure) as failed:
        original_quote(essay, quote)
    assert failed.value.reason == "QUOTE_NOT_EXACT"


def test_original_whitespace_expansion_is_still_length_limited():
    evidence = EvidenceResult.model_validate(
        {"evidence": [{"quote": "A B", "assessment": "Nhận xét."}]}
    )
    with pytest.raises(ProviderFailure) as error:
        verify_evidence(evidence, "A" + " " * 600 + "B")
    assert error.value.reason == "EVIDENCE_ITEM_TOO_LONG"


def test_unsafe_provider_reason_is_not_retained():
    failed = ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="raw-secret")
    assert failed.reason is None


def test_missing_feedback_is_schema_failure_without_input_content():
    with pytest.raises(ValidationError) as error:
        TraitScore.model_validate({"score": 7, "feedback": "", "strengths": [], "improvements": []})
    assert validation_reason(error.value) == "SCHEMA_VALIDATION"
