"""Realistic Vietnamese provider verbosity must not require a repair call."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domains.scoring.writing import WritingScoringRequest
from app.providers.writing_llm.base import Completion
from app.services.mts_writing import MTSWritingScoringService

CORE = {
    "score": 6.5,
    "feedback": "Từ vựng nhìn chung phù hợp, nhưng vài cách kết hợp từ thiếu tự nhiên.",
    "strengths": ["Diễn đạt rõ ý chính."],
    "improvements": ["Rà soát cách kết hợp từ."],
}
VERBOSE = (
    "Bài viết sử dụng từ vựng phù hợp để trình bày quan điểm về công viên; "
    "tuy nhiên, một số cách kết hợp từ còn thiếu tự nhiên và làm giảm độ chính xác. "
    "Bạn nên chọn từ cụ thể hơn và kiểm tra dạng từ trong các câu hỗ trợ. "
) * 5
ESSAY = "Fictional parks improve city life. They  support communities."


class Provider:
    def __init__(self, lr_score):
        self.lr_score = lr_score
        self.calls = []

    async def complete(self, messages, schema):
        self.calls.append((messages, schema))
        evidence = "evidence" in schema["properties"]
        lr = "Criterion: Lexical Resource." in messages[0]["content"]
        output = (
            {"evidence": [{"source_id": "P1S2", "assessment": "Dẫn chứng liên quan."}]}
            if evidence
            else self.lr_score
            if lr
            else CORE
        )
        return Completion(json.dumps(output), finish_reason="stop")


async def assess(output):
    provider = Provider(output)
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
async def test_verbose_lr_completes_without_repair_and_retains_safe_normalization_diagnostics(
    change, path, error_type, caplog
):
    caplog.set_level("INFO", logger="app.services.mts_writing")
    result, provider, service, events = await assess({**CORE, **change})
    assert result is not None and result.criteria.lr.score == Decimal("6.5")
    assert result.overall_band == Decimal("6.5") and len(provider.calls) == 8
    lr = result.criteria.lr
    assert len(lr.feedback) <= 800
    assert len(lr.strengths) <= 3 and all(0 < len(s) <= 240 for s in lr.strengths)
    assert len(lr.improvements) <= 3 and all(0 < len(s) <= 240 for s in lr.improvements)
    assert lr.evidence[0].quote == "They  support communities."
    assert [p.criterion for e, p in events if e == "criterion.completed"] == [
        "ta",
        "cc",
        "lr",
        "gra",
    ]
    assert not any(e in {"criterion.retrying", "criterion.failed"} for e, _ in events)
    assert service.diagnostics[0].reason == "SCORE_PRESENTATION_NORMALIZED"
    assert (path, error_type) in [
        (i.field, i.validation_type) for i in service.diagnostics[0].validation_issues
    ]
    assert "AI validation failure" not in caplog.text
    assert VERBOSE not in caplog.text + str(service.diagnostics)
    assert "SCORE_PRESENTATION_NORMALIZED" not in str(events)


@pytest.mark.parametrize(
    "change",
    [
        {"score": 6.3},
        {"score": 10},
        {"feedback": "  \n\t"},
        {"feedback": 42},
        {"strengths": "invalid"},
        {"improvements": {}},
        {"strengths": [42]},
        {"improvements": [None]},
        {"unknown": "private"},
    ],
)
async def test_invalid_semantic_lr_still_repairs_once_fails_and_runs_gra(change):
    result, provider, service, events = await assess({**CORE, **change})
    assert result is None and set(service.failures) == {"lr"}
    assert len(provider.calls) == 9
    assert sum(e == "criterion.retrying" for e, _ in events) == 1
    assert any(e == "criterion.failed" and p.criterion == "lr" for e, p in events)
    assert any(e == "criterion.completed" and p.criterion == "gra" for e, p in events)
