import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domains.scoring.ai_writing_validation import (
    original_quote,
    validation_reason,
    verify_evidence,
)
from app.domains.scoring.mts_prompts import AI_WRITING_PROMPT_VERSION, effective_prompt_version
from app.domains.scoring.writing import WritingScoringRequest
from app.providers.writing_llm.base import Completion, ProviderFailure
from app.schemas.writing_ai import EvidenceResult, TraitScore
from app.services.mts_writing import MTSWritingScoringService

ESSAY = "Fictional parks improve city life."
EVIDENCE = {
    "evidence": [{"quote": ESSAY, "assessment": "Luận điểm liên quan trực tiếp đến đề bài."}]
}
SCORE = {
    "score": 6.5,
    "feedback": "Cần nêu ví dụ cụ thể về lợi ích của công viên.",
    "strengths": ["Lập trường rõ ràng."],
    "improvements": ["Phát triển dẫn chứng."],
}


class Provider:
    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.calls = []

    async def complete(self, messages, schema):
        index = len(self.calls)
        self.calls.append(messages)
        value = self.overrides.get(index)
        if isinstance(value, ProviderFailure):
            raise value
        if value is None:
            value = json.dumps(EVIDENCE if "evidence" in schema["properties"] else SCORE)
        return Completion(value)


async def assess(provider):
    events = []

    async def trace(event, payload):
        events.append((event, payload))

    mts = MTSWritingScoringService(provider)
    result = await mts.assess(
        WritingScoringRequest(
            attempt_id=uuid4(),
            writing_task_id=uuid4(),
            prompt="Discuss fictional parks.",
            response=ESSAY,
        ),
        trace,
    )
    return result, mts, events


async def test_valid_vietnamese_content_and_independent_trait_prompts():
    provider = Provider()
    result, mts, events = await assess(provider)
    assert result.criteria.lr.feedback == SCORE["feedback"]
    assert result.criteria.ta.evidence[0].quote == ESSAY
    assert len(provider.calls) == 8 and not mts.diagnostics
    for messages in provider.calls:
        assert "natural Vietnamese" in messages[0]["content"]
        assert "original English" in messages[0]["content"]
        assert "UNTRUSTED DATA" in messages[0]["content"]
    assert sum(event == "criterion.completed" for event, _ in events) == 4
    assert AI_WRITING_PROMPT_VERSION == effective_prompt_version("mts-task2-v1") == "mts-task2-v2"


@pytest.mark.parametrize(
    "output,reason,guidance",
    [
        ("private malformed output", "INVALID_JSON", "valid JSON"),
        (
            json.dumps(
                {"evidence": [{"quote": "Paraphrased park benefits.", "assessment": "Nhận xét."}]}
            ),
            "QUOTE_NOT_EXACT",
            "character-for-character",
        ),
        (
            json.dumps({"evidence": [], "unwanted": "private extra value"}),
            "SCHEMA_VALIDATION",
            "required field",
        ),
        (
            json.dumps({"evidence": [{"quote": "x" * 601, "assessment": "Nhận xét."}]}),
            "EVIDENCE_ITEM_TOO_LONG",
            "600 characters",
        ),
        (
            json.dumps({"evidence": EVIDENCE["evidence"] * 7}),
            "TOO_MANY_EVIDENCE_ITEMS",
            "at most 6",
        ),
        (
            ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="EMPTY_MODEL_CONTENT"),
            "EMPTY_MODEL_CONTENT",
            "non-empty",
        ),
        (
            ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="FINISH_REASON_NOT_STOP"),
            "FINISH_REASON_NOT_STOP",
            "incomplete",
        ),
    ],
)
async def test_evidence_targeted_repair_once(output, reason, guidance, caplog):
    provider = Provider({0: output})
    result, mts, events = await assess(provider)
    assert result.overall_band == 6.5 and len(provider.calls) == 9
    repair = provider.calls[1][-1]["content"]
    assert reason in repair and guidance in repair
    assert provider.calls[0][0] == provider.calls[1][0]
    assert mts.diagnostics[0].model_dump() == {
        "stage": "evidence",
        "criterion": "ta",
        "reason": reason,
        "attempt": 1,
    }
    assert sum(event == "criterion.retrying" for event, _ in events) == 1
    assert "private" not in caplog.text + str(mts.diagnostics) + str(events)


async def test_half_band_targeted_scoring_repair():
    provider = Provider({1: json.dumps({**SCORE, "score": 7.25})})
    _, mts, events = await assess(provider)
    assert len(provider.calls) == 9
    assert "INVALID_HALF_BAND" in provider.calls[2][-1]["content"]
    assert "0, 0.5, 1.0" in provider.calls[2][-1]["content"]
    assert mts.diagnostics[0].stage == "scoring"
    retry = next(payload for event, payload in events if event == "criterion.retrying")
    assert retry.stage == "scoring"


async def test_two_failed_calls_stop_with_safe_metadata(caplog):
    provider = Provider({0: "private raw output", 1: "private raw output again"})
    mts = MTSWritingScoringService(provider)
    events = []

    async def trace(event, payload):
        events.append((event, payload))

    with pytest.raises(ProviderFailure) as failed:
        await mts.assess(
            WritingScoringRequest(
                attempt_id=uuid4(), writing_task_id=uuid4(), prompt="Fictional", response=ESSAY
            ),
            trace,
        )
    assert len(provider.calls) == 2
    assert failed.value.reason == "INVALID_JSON"
    assert [item.attempt for item in mts.diagnostics] == [1, 2]
    assert "private raw" not in caplog.text + str(failed.value) + str(mts.diagnostics) + str(events)


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
    with pytest.raises(ValidationError) as error:
        verify_evidence(evidence, "A" + " " * 600 + "B")
    assert validation_reason(error.value) == "EVIDENCE_ITEM_TOO_LONG"


def test_unsafe_provider_reason_is_not_retained():
    failed = ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="raw-secret")
    assert failed.reason is None


def test_missing_feedback_is_schema_failure_without_input_content():
    with pytest.raises(ValidationError) as error:
        TraitScore.model_validate({"score": 7, "feedback": "", "strengths": [], "improvements": []})
    assert validation_reason(error.value) == "SCHEMA_VALIDATION"
