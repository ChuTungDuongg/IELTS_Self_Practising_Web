"""Provider text constraints differ from the bounded display contract."""

import json

import pytest
from pydantic import ValidationError

from app.providers.writing_llm.vllm import guided_json_schema
from app.schemas.writing_ai import ScoringOutput

CORE = {
    "score": 6.5,
    "feedback": "Từ vựng phù hợp, nhưng một số cách kết hợp từ chưa tự nhiên.",
    "strengths": ["Lựa chọn từ nhìn chung phù hợp."],
    "improvements": ["Rà soát cách kết hợp từ trong ví dụ."],
}


@pytest.mark.parametrize(
    "change,path,error_type",
    [
        ({"feedback": "Nhận xét tiếng Việt. " * 45}, "feedback", "string_too_long"),
        (
            {"strengths": ["Điểm mạnh.", "Diễn đạt tiếng Việt. " * 15]},
            "strengths.1",
            "string_too_long",
        ),
        ({"improvements": ["Cần cải thiện diễn đạt. " * 15]}, "improvements.0", "string_too_long"),
        ({"feedback": "  \n\t"}, "feedback", "string_too_short"),
        ({"strengths": "private rejected content"}, "strengths", "list_type"),
        ({"private-secret-field": "private rejected content"}, "<extra>", "extra_forbidden"),
    ],
)
def test_field_diagnostics_identify_v4_failure_without_retaining_input(change, path, error_type):
    from app.domains.scoring.ai_writing_validation import safe_validation_issues

    with pytest.raises(ValidationError) as error:
        ScoringOutput.model_validate({**CORE, **change})
    issues = safe_validation_issues(error.value)
    assert [(i.field, i.validation_type) for i in issues] == [(path, error_type)]
    assert "private" not in json.dumps([i.model_dump() for i in issues])
    assert CORE["feedback"] not in str(issues)


def test_provider_schema_cannot_enforce_display_string_limits_but_keeps_array_limit():
    backend = ScoringOutput.model_json_schema(mode="serialization")
    provider = guided_json_schema(backend)
    assert backend["properties"]["feedback"]["maxLength"] == 800
    assert "maxLength" not in provider["properties"]["feedback"]
    assert "minLength" not in provider["properties"]["feedback"]
    assert provider["properties"]["strengths"]["maxItems"] == 3
    assert "maxLength" not in provider["properties"]["strengths"]["items"]


@pytest.mark.parametrize(
    "text,limit",
    [
        ("Từ vựng tiếng Việt rõ ràng—chính xác. " * 40, 800),
        ("Tiếng Việt “đúng” và tự nhiên. " * 20, 240),
        ("a\u0301" * 500, 240),
        ("📝" * 500, 240),
        ("x" * 900, 800),
        ("x" * 5, 1),
    ],
    ids=["Vietnamese", "unicode-quotes", "decomposed-accents", "emoji", "long-word", "tiny-bound"],
)
def test_clipping_preserves_original_unicode_prefix_and_bound(text, limit):
    from app.domains.scoring.ai_writing_normalization import normalize_feedback

    normalized = normalize_feedback(text, max_chars=limit)
    assert len(normalized) <= limit and normalized.endswith("…")
    assert text.startswith(normalized[:-1])
    normalized.encode("utf-8").decode("utf-8")
    if "\u0301" in text:
        assert normalized[:-1].endswith("\u0301")


def test_normal_text_is_not_shrunk_or_rewritten_and_boundaries_are_preferred():
    from app.domains.scoring.ai_writing_normalization import normalize_feedback

    normal = "Từ vựng  tiếng Việt—đúng, aren’t they?"
    assert normalize_feedback("  " + normal + " \n") == normal
    sentence = "Ý rõ và có sự phát triển phù hợp."
    assert (
        normalize_feedback(sentence + " Một từ rất dài: " + "x" * 80, max_chars=len(sentence) + 6)
        == sentence + "…"
    )
    assert normalize_feedback("Từ vựng chính xác cần kiểm tra", max_chars=15) == "Từ vựng chính…"


def test_blank_bullets_are_removed_before_item_limit_without_inventing_text():
    from app.domains.scoring.ai_writing_normalization import normalize_bullets

    assert normalize_bullets(["  ", " A ", "\n", "B", " C ", "D"]) == ["A", "B", "C"]


@pytest.mark.parametrize("score", [0, 0.5, 6.5, 7, 7.5, 8.5, 9])
def test_raw_normalization_never_changes_score(score):
    from app.domains.scoring.ai_writing_normalization import normalize_scoring_output
    from app.schemas.writing_ai import RawScoringOutput

    raw = RawScoringOutput.model_validate({**CORE, "score": score, "feedback": "Nhận xét. " * 100})
    bounded, issues = normalize_scoring_output(raw)
    assert bounded.score == raw.score == score
    assert len(bounded.feedback) <= 800 and issues


@pytest.mark.parametrize("value", [42, {}, [], None])
def test_raw_feedback_never_coerces_structural_garbage(value):
    from app.schemas.writing_ai import RawScoringOutput

    with pytest.raises(ValidationError):
        RawScoringOutput.model_validate({**CORE, "feedback": value})
