"""Core IELTS results survive imperfect optional explanation metadata."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domains.scoring.essay_sources import segment_essay
from app.domains.scoring.writing import WritingScoringRequest
from app.providers.writing_llm.base import Completion
from app.schemas.writing_ai import EvidenceSelection, ScoringOutput
from app.services.mts_writing import MTSWritingScoringService

ESSAY = "“Fictional parks”—useful, aren’t they?  They  help city life.\r\n\r\nCosts matter–too."
CORE = {
    "score": 8.5,
    "feedback": "Cấu trúc câu đa dạng và phần lớn chính xác; một vài lỗi dấu câu còn xuất hiện.",
    "strengths": ["Sử dụng linh hoạt câu phức."],
    "improvements": ["Rà soát dấu câu ở các mệnh đề dài."],
}
CALIBRATION = {
    "support": [{"source_id": "P1S2", "assessment": "Cấu trúc câu được kiểm soát."}],
    "next_band": 9,
    "next_band_blockers": [],
    "comparison": "Một vài lỗi nhỏ chưa phù hợp mức cao nhất.",
}


class CoreProvider:
    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.calls = []

    async def complete(self, messages, schema, *, options=None):
        index = len(self.calls)
        self.calls.append((messages, schema))
        if index in self.overrides:
            value = self.overrides[index]
            return value if isinstance(value, Completion) else Completion(json.dumps(value))
        value = (
            {"evidence": [{"source_id": "P1S1", "assessment": "Dẫn chứng liên quan."}]}
            if "evidence" in schema["properties"]
            else CORE
        )
        return Completion(json.dumps(value), finish_reason="stop")


async def run(provider):
    events = []

    async def trace(event, payload):
        events.append((event, payload))

    service = MTSWritingScoringService(provider)
    result = await service.assess(
        WritingScoringRequest(
            attempt_id=uuid4(),
            writing_task_id=uuid4(),
            prompt="Discuss fictional parks.",
            response=ESSAY,
        ),
        trace,
    )
    return result, service, events


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"calibration": {**CALIBRATION, "next_band": 8.5}},
        {"calibration": CALIBRATION},  # Empty blockers, no high-band justification.
        {"calibration": {"comparison": "Các lỗi nhỏ xuất hiện không thường xuyên."}},
        {
            "calibration": {
                **CALIBRATION,
                "support": [{"source_id": "P99S1", "assessment": "Nhận xét."}],
            }
        },
        {"calibration": "malformed private metadata"},
        {"calibration": {"support": "malformed", "comparison": ["private"]}},
    ],
    ids=[
        "missing",
        "wrong-next-band",
        "empty-blockers-high-band",
        "incomplete",
        "unknown-source",
        "wrong-type",
        "malformed-fields",
    ],
)
async def test_valid_gra_core_completes_without_calibration_retry(metadata, caplog):
    provider = CoreProvider({7: {**CORE, **metadata}})
    result, service, events = await run(provider)
    assert result is not None
    assert result.criteria.gra.score == Decimal("8.5")
    assert result.overall_band == Decimal("8.5")
    assert len(provider.calls) == 8  # Four evidence calls and four scoring calls.
    assert [p.criterion for e, p in events if e == "criterion.completed"] == [
        "ta",
        "cc",
        "lr",
        "gra",
    ]
    assert not any(e in {"criterion.retrying", "criterion.failed"} for e, _ in events)
    assert not service.failures
    assert all(d.reason != "SCORE_CALIBRATION_INVALID" for d in service.diagnostics)
    assert result.criteria.gra.evidence[0].quote == "“Fictional parks”—useful, aren’t they?"
    assert "private" not in caplog.text + str(service.diagnostics) + str(events)


def test_primary_evidence_schema_stays_strict_and_scoring_schema_is_small():
    evidence = EvidenceSelection.model_json_schema(mode="serialization")
    scoring = ScoringOutput.model_json_schema(mode="serialization")
    assert set(scoring["required"]) == {"score", "feedback", "strengths", "improvements"}
    assert "calibration" not in scoring["properties"]
    assert evidence["$defs"]["EvidenceChoice"]["required"] == ["source_id", "assessment"]
    assert "quote" not in evidence["$defs"]["EvidenceChoice"]["properties"]


def test_unknown_calibration_sources_are_dropped_without_losing_valid_items():
    from app.domains.scoring.ai_writing_validation import sanitize_calibration

    calibration, reasons = sanitize_calibration(
        {
            **CALIBRATION,
            "next_band": "wrong metadata",
            "support": [
                {"source_id": "P99S1", "assessment": "Nhận xét."},
                *CALIBRATION["support"],
            ],
            "next_band_blockers": [
                {"source_id": "P99S2", "assessment": "Nhận xét.", "severity": "isolated"},
                {"source_id": "P2S1", "assessment": "Dấu câu cần rà soát.", "severity": "isolated"},
            ],
        },
        Decimal("8.5"),
        {s.source_id: s for s in segment_essay(ESSAY)},
    )
    assert calibration is not None and calibration.next_band == 9
    assert [s.source_id for s in calibration.support] == ["P1S2"]
    assert [s.source_id for s in calibration.next_band_blockers] == ["P2S1"]
    assert "CALIBRATION_SOURCE_DROPPED" in reasons
    assert "CALIBRATION_METADATA_NORMALIZED" in reasons


@pytest.mark.parametrize("score,upper", [(6.5, 7), (7, 8), (7.5, 8), (8.5, 9), (9, None)])
def test_next_descriptor_is_metadata_derived_from_accepted_score(score, upper):
    from app.domains.scoring.ai_writing_validation import sanitize_calibration

    calibration, _ = sanitize_calibration({}, Decimal(str(score)), {})
    assert calibration.next_band == upper


@pytest.mark.parametrize(
    "bad",
    [
        {**CORE, "score": 6.3},
        {**CORE, "score": -0.5},
        {**CORE, "score": 9.5},
        {k: v for k, v in CORE.items() if k != "score"},
        {k: v for k, v in CORE.items() if k != "feedback"},
        {**CORE, "feedback": "   "},
        {**CORE, "strengths": "Không phải danh sách."},
        {**CORE, "improvements": [42]},
        Completion("private invalid JSON", finish_reason="stop"),
        [],
    ],
)
async def test_invalid_core_gets_one_repair_then_only_gra_fails(bad):
    provider = CoreProvider({7: bad, 8: bad})
    result, service, events = await run(provider)
    assert result is None and len(provider.calls) == 9
    assert set(service.failures) == {"gra"}
    assert [p.criterion for e, p in events if e == "criterion.completed"] == ["ta", "cc", "lr"]
    assert sum(e == "criterion.retrying" for e, _ in events) == 1
    assert sum(e == "criterion.failed" for e, _ in events) == 1


def test_optional_calibration_is_excluded_from_core_serialization_and_repr():
    parsed = ScoringOutput.model_validate({**CORE, "calibration": {"private": "private content"}})
    assert parsed.model_dump(mode="json") == CORE
    assert "private" not in repr(parsed)


async def test_unknown_primary_id_still_repairs_fails_and_runs_later_criterion():
    bad = {"evidence": [{"source_id": "P99S1", "assessment": "Nhận xét."}]}
    provider = CoreProvider({4: bad, 5: bad})
    result, service, events = await run(provider)
    assert result is None and len(provider.calls) == 8
    assert set(service.failures) == {"lr"}
    assert [d.reason for d in service.diagnostics] == ["EVIDENCE_UNKNOWN_SOURCE_ID"] * 2
    assert [p.criterion for e, p in events if e == "criterion.completed"] == ["ta", "cc", "gra"]


async def test_truncated_scoring_core_is_never_accepted():
    truncated = Completion('{"score":8.5,"feedback":', finish_reason="length")
    provider = CoreProvider({7: truncated, 8: truncated})
    result, service, _ = await run(provider)
    assert result is None and len(provider.calls) == 9
    assert [d.reason for d in service.diagnostics] == ["PROVIDER_FINISH_LENGTH"] * 2
    assert all(d.finish_reason == "length" for d in service.diagnostics)


async def test_scoring_failure_logs_safe_field_type_and_masks_untrusted_extra_names(caplog):
    caplog.set_level("INFO", logger="app.services.mts_writing")
    invalid = {**CORE, "feedback": 42, "private-secret-key": "private rejected value"}
    result, service, events = await run(CoreProvider({7: invalid, 8: invalid}))
    assert result is None
    for diagnostic in service.diagnostics:
        assert {(i.field, i.validation_type) for i in diagnostic.validation_issues} == {
            ("feedback", "string_type"),
            ("<extra>", "extra_forbidden"),
        }
    assert "field=feedback validation_type=string_type" in caplog.text
    assert "field=<extra> validation_type=extra_forbidden" in caplog.text
    public = str(events)
    assert "validation_type" not in public
    assert "private" not in public
    retained = caplog.text + str(service.diagnostics)
    for forbidden in ["private", CORE["feedback"], ESSAY, "Discuss fictional parks."]:
        assert forbidden not in retained
