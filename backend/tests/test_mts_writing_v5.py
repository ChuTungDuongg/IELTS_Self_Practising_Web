"""Realistic Vietnamese provider verbosity must not require a repair call."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domains.scoring.ai_writing_normalization import (
    normalize_criterion_feedback,
    normalize_scoring_output,
)
from app.domains.scoring.writing import WritingScoringRequest
from app.providers.writing_llm.base import Completion
from app.schemas.writing_ai import RawCriterionFeedbackOutput, RawScoringOutput
from app.services.mts_writing import MTSWritingScoringService

CORE = {
    "score": 6.5,
    "feedback": "Từ vựng nhìn chung phù hợp, nhưng vài cách kết hợp từ thiếu tự nhiên.",
    "strengths": ["Diễn đạt rõ ý chính."],
    "improvements": ["Rà soát cách kết hợp từ."],
}
SCORE = {"score": 6.5}
FEEDBACK = {
    "feedback": CORE["feedback"],
    "strengths": CORE["strengths"],
    "improvements": CORE["improvements"],
}
OBSERVATIONS = {
    "observations": [
        {
            "source_id": "P1S2",
            "kind": "STRENGTH",
            "observation": "Diễn đạt rõ ý chính.",
            "confidence": "HIGH",
        }
    ]
}
VERBOSE = (
    "Bài viết sử dụng từ vựng phù hợp để trình bày quan điểm về công viên; "
    "tuy nhiên, một số cách kết hợp từ còn thiếu tự nhiên và làm giảm độ chính xác. "
    "Bạn nên chọn từ cụ thể hơn và kiểm tra dạng từ trong các câu hỗ trợ. "
) * 5
ESSAY = "Fictional parks improve city life. They  support communities."


class Provider:
    def __init__(self, lr_feedback, lr_score=None):
        self.lr_feedback = lr_feedback
        self.lr_score = SCORE if lr_score is None else lr_score
        self.calls = []

    async def complete(self, messages, schema, *, options=None):
        if "verdict" in schema["properties"]:
            # Keep call counts scoped to the three criterion stages.
            return Completion(
                json.dumps(
                    {
                        "verdict": "ON_TOPIC",
                        "confidence": "HIGH",
                        "source_ids": [],
                        "reason": "Có liên hệ với đề bài.",
                    }
                )
            )
        self.calls.append((messages, schema))
        lr = "Criterion: Lexical Resource." in messages[0]["content"]
        properties = set(schema["properties"])
        if properties == {"evidence"}:
            output = {"evidence": [{"source_id": "P1S2", "assessment": "Dẫn chứng liên quan."}]}
        elif properties == {"score"}:
            output = self.lr_score if lr else SCORE
        else:
            assert properties == {"observations"}
            output = self.lr_feedback if lr else OBSERVATIONS
        return (
            output
            if isinstance(output, Completion)
            else Completion(json.dumps(output), finish_reason="stop")
        )


async def assess(output, score=None):
    provider = Provider(output, score)
    service = MTSWritingScoringService(provider)
    events = []

    async def trace(event, payload):
        events.append((event, payload))

    result = await service.assess(
        WritingScoringRequest(
            attempt_id=uuid4(),
            writing_task_id=uuid4(),
            prompt="Discuss fictional parks.",
            response=ESSAY,
        ),
        trace,
    )
    return result, provider, service, events


async def test_bounded_lr_observations_build_concise_vietnamese_display_without_repair(caplog):
    caplog.set_level("INFO", logger="app.services.mts_writing")
    observations = [
        {
            "source_id": "P1S2",
            "kind": kind,
            "confidence": "HIGH",
            "observation": VERBOSE[:237] + f"{index}.",
        }
        for index, kind in enumerate(["STRENGTH"] * 3 + ["LIMITATION"] * 3)
    ]
    result, provider, service, events = await assess({"observations": observations})
    assert result is not None and result.criteria.lr.score == Decimal("6.5")
    assert result.overall_band == Decimal("6.5") and len(provider.calls) == 12
    lr = result.criteria.lr
    assert len(lr.feedback) <= 800
    assert len(lr.strengths) <= 3 and all(0 < len(s) <= 240 for s in lr.strengths)
    assert len(lr.improvements) <= 3 and all(0 < len(s) <= 240 for s in lr.improvements)
    assert len(lr.strengths) == len(lr.improvements) == 3
    assert lr.feedback.endswith("…") and lr.feedback.startswith(VERBOSE[:50])
    assert all(item.startswith("Đoạn 1: ") for item in lr.strengths + lr.improvements)
    assert lr.evidence[0].quote == "They  support communities."
    assert [p.criterion for e, p in events if e == "criterion.completed"] == [
        "ta",
        "cc",
        "lr",
        "gra",
    ]
    assert not any(e in {"criterion.retrying", "criterion.failed"} for e, _ in events)
    assert not service.diagnostics
    assert "AI validation failure" not in caplog.text
    assert VERBOSE not in caplog.text + str(service.diagnostics)
    assert "FEEDBACK_PRESENTATION_NORMALIZED" not in str(events)


@pytest.mark.parametrize(
    "bad",
    [
        {"observations": [{**OBSERVATIONS["observations"][0], "observation": "  \n\t"}]},
        {"observations": [{**OBSERVATIONS["observations"][0], "observation": 42}]},
        {"observations": "invalid"},
        {"observations": {}},
        {"observations": [42]},
        {"observations": [None]},
        {**OBSERVATIONS, "unknown": "private"},
        {**OBSERVATIONS, "score": 6.3},
        {**OBSERVATIONS, "score": 10},
        {
            "observations": [
                {**OBSERVATIONS["observations"][0], "observation": "Bài viết phù hợp Band 5."}
            ]
        },
        {"observations": [{**OBSERVATIONS["observations"][0], "observation": VERBOSE}]},
    ],
)
async def test_invalid_lr_feedback_repairs_once_preserves_fixed_score_and_runs_gra(bad):
    result, provider, service, events = await assess(bad)
    assert result is not None and not service.failures
    assert result.criteria.lr.score == Decimal("6.5")
    assert result.overall_band == Decimal("6.5")
    assert result.criteria.lr.strengths == result.criteria.lr.improvements == []
    assert "chưa khả dụng" in result.criteria.lr.feedback
    assert result.criteria.lr.evidence[0].quote == "They  support communities."
    assert len(provider.calls) == 13
    assert sum(e == "criterion.retrying" for e, _ in events) == 1
    assert not any(e == "criterion.failed" for e, _ in events)
    assert any(e == "criterion.completed" and p.criterion == "gra" for e, p in events)
    assert [d.stage for d in service.diagnostics] == ["feedback"] * 3
    assert service.diagnostics[-1].reason == "FEEDBACK_FALLBACK_USED"
    assert all(getattr(result.criteria, t).score == Decimal("6.5") for t in ("ta", "cc", "gra"))


@pytest.mark.parametrize(
    "score", [{"score": 6.3}, {"score": 10}, {}, {**SCORE, "feedback": VERBOSE}]
)
async def test_invalid_lr_score_still_repairs_once_fails_and_runs_gra(score):
    result, provider, service, events = await assess(OBSERVATIONS, score)
    assert result is None and set(service.failures) == {"lr"}
    assert len(provider.calls) == 11
    assert sum(e == "criterion.retrying" for e, _ in events) == 1
    assert any(e == "criterion.failed" and p.criterion == "lr" for e, p in events)
    assert any(e == "criterion.completed" and p.criterion == "gra" for e, p in events)
    assert all(d.stage == "score" for d in service.diagnostics)
    lr_calls = [
        (m, s) for m, s in provider.calls if "Criterion: Lexical Resource." in m[0]["content"]
    ]
    assert [set(s["properties"]) for _, s in lr_calls] == [{"score"}, {"score"}]


@pytest.mark.parametrize(
    "change,path,error_type",
    [
        ({"feedback": VERBOSE}, "feedback", "string_too_long"),
        ({"strengths": ["Một điểm mạnh.", VERBOSE]}, "strengths.1", "string_too_long"),
        ({"improvements": [VERBOSE]}, "improvements.0", "string_too_long"),
        ({"strengths": ["Điểm mạnh."] * 4}, "strengths", "too_long"),
        ({"improvements": ["Cần cải thiện."] * 4}, "improvements", "too_long"),
        ({"strengths": ["  ", "Điểm mạnh."]}, "strengths.0", "string_too_short"),
    ],
)
def test_historical_raw_scoring_display_normalization_preserves_accepted_score(
    change, path, error_type
):
    raw = RawScoringOutput.model_validate({**CORE, **change})
    result, issues = normalize_scoring_output(raw)
    assert result.score == Decimal("6.5")
    assert len(result.feedback) <= 800
    assert len(result.strengths) <= 3 and all(0 < len(s) <= 240 for s in result.strengths)
    assert len(result.improvements) <= 3 and all(0 < len(s) <= 240 for s in result.improvements)
    assert (path, error_type) in [(i.field, i.validation_type) for i in issues]
    raw_feedback = RawCriterionFeedbackOutput.model_validate({**FEEDBACK, **change})
    feedback, feedback_issues = normalize_criterion_feedback(raw_feedback, Decimal("6.5"))
    assert feedback.model_dump() == result.model_dump(exclude={"score"})
    assert (path, error_type) in [(i.field, i.validation_type) for i in feedback_issues]


def test_raw_feedback_normalization_preserves_vietnamese_and_internal_whitespace():
    text = "  Từ vựng  rõ ràng; aren’t “parks” useful?  "
    raw = RawCriterionFeedbackOutput.model_validate(
        {"feedback": text, "strengths": [text], "improvements": []}
    )
    result, issues = normalize_criterion_feedback(raw, Decimal("6.5"))
    assert result.feedback == text.strip()
    assert result.strengths == [text.strip()]
    assert not issues
