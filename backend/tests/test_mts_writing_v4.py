"""Strict score inference and historical optional explanation compatibility."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domains.scoring.ai_writing_normalization import normalize_scoring_output
from app.domains.scoring.ai_writing_validation import sanitize_calibration
from app.domains.scoring.essay_sources import segment_essay
from app.domains.scoring.writing import WritingScoringRequest
from app.providers.writing_llm.base import Completion
from app.schemas.writing_ai import (
    CriterionBandScore,
    EvidenceSelection,
    RawScoringOutput,
    ScoringOutput,
    Task2FeedbackDraft,
)
from app.services.mts_writing import MTSWritingScoringService

ESSAY = "“Fictional parks”—useful, aren’t they?  They  help city life.\r\n\r\nCosts matter–too."
CORE = {
    "score": 8.5,
    "feedback": "Cấu trúc câu đa dạng và phần lớn chính xác; một vài lỗi dấu câu còn xuất hiện.",
    "strengths": ["Sử dụng linh hoạt câu phức."],
    "improvements": ["Rà soát dấu câu ở các mệnh đề dài."],
}
SCORE = {"score": 8.5}
FEEDBACK = {
    "feedback": CORE["feedback"],
    "strengths": CORE["strengths"],
    "improvements": CORE["improvements"],
}
OBSERVATIONS = {
    "observations": [
        {
            "source_id": "P1S1",
            "kind": "STRENGTH",
            "observation": "Cấu trúc câu được kiểm soát.",
            "confidence": "HIGH",
        }
    ]
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
        if "verdict" in schema["properties"]:
            # Keep index-based overrides scoped to the three criterion stages.
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
        index = len(self.calls)
        self.calls.append((messages, schema))
        if index in self.overrides:
            value = self.overrides[index]
            return value if isinstance(value, Completion) else Completion(json.dumps(value))
        properties = set(schema["properties"])
        if properties == {"evidence"}:
            value = {"evidence": [{"source_id": "P1S1", "assessment": "Dẫn chứng liên quan."}]}
        elif properties == {"score"}:
            value = SCORE
        else:
            assert properties == {"observations"}
            value = OBSERVATIONS
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
def test_historical_valid_core_survives_optional_calibration_metadata(metadata):
    raw = RawScoringOutput.model_validate({**CORE, **metadata})
    calibration, reasons = sanitize_calibration(
        raw.calibration, raw.score, {s.source_id: s for s in segment_essay(ESSAY)}
    )
    result, issues = normalize_scoring_output(raw)
    assert result.score == Decimal("8.5") and not issues
    assert result.model_dump(mode="json") == CORE
    assert all(reason.startswith("CALIBRATION_") for reason in reasons)
    assert "private" not in repr(raw) + repr(result) + repr(calibration) + str(reasons)


async def test_three_independent_criterion_stages_complete_with_exact_unicode_evidence():
    provider = CoreProvider()
    result, service, events = await run(provider)
    assert result is not None and result.overall_band == Decimal("8.5")
    assert len(provider.calls) == 12
    assert [set(schema["properties"]) for _, schema in provider.calls] == [
        {"score"},
        {"evidence"},
        {"observations"},
    ] * 4
    assert [p.criterion for e, p in events if e == "criterion.completed"] == [
        "ta",
        "cc",
        "lr",
        "gra",
    ]
    assert not service.failures and not service.diagnostics
    assert result.criteria.gra.evidence[0].quote == "“Fictional parks”—useful, aren’t they?"


def test_primary_evidence_schema_stays_strict_and_scoring_schema_is_small():
    evidence = EvidenceSelection.model_json_schema(mode="serialization")
    scoring = CriterionBandScore.model_json_schema(mode="serialization")
    feedback = Task2FeedbackDraft.model_json_schema(mode="serialization")
    assert set(scoring["required"]) == set(scoring["properties"]) == {"score"}
    assert scoring["additionalProperties"] is False
    assert set(feedback["required"]) == set(feedback["properties"]) == {"observations"}
    assert feedback["additionalProperties"] is False
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
        {"score": 6.3},
        {"score": -0.5},
        {"score": 9.5},
        {},
        {**SCORE, "feedback": CORE["feedback"]},
        {**SCORE, "calibration": CALIBRATION},
        {**SCORE, "calibration": "malformed private metadata"},
        Completion("private invalid JSON", finish_reason="stop"),
        [],
    ],
)
async def test_invalid_score_gets_one_repair_then_only_gra_fails(bad):
    provider = CoreProvider({9: bad, 10: bad})
    result, service, events = await run(provider)
    assert result is None and len(provider.calls) == 11
    assert set(service.failures) == {"gra"}
    assert [p.criterion for e, p in events if e == "criterion.completed"] == ["ta", "cc", "lr"]
    assert sum(e == "criterion.retrying" for e, _ in events) == 1
    assert sum(e == "criterion.failed" for e, _ in events) == 1
    assert all(d.stage == "score" for d in service.diagnostics)
    assert all(set(schema["properties"]) == {"score"} for _, schema in provider.calls[9:])


@pytest.mark.parametrize(
    "bad,repair",
    [
        ({}, True),
        ({"observations": [{**OBSERVATIONS["observations"][0], "observation": "   "}]}, False),
        ({"observations": "Không phải danh sách."}, True),
        ({"observations": [42]}, False),
        ({**OBSERVATIONS, "score": 1}, True),
        (Completion("private invalid JSON", finish_reason="stop"), True),
        (Completion(""), True),
        (Completion('{"observations":', finish_reason="length"), True),
        ([], True),
    ],
)
async def test_invalid_feedback_repairs_only_structure_and_preserves_gra_score(bad, repair):
    provider = CoreProvider({11: bad, 12: bad})
    result, service, events = await run(provider)
    assert result is not None and len(provider.calls) == 12 + int(repair)
    assert result.criteria.gra.score == Decimal("8.5") and result.overall_band == Decimal("8.5")
    assert result.criteria.gra.strengths == result.criteria.gra.improvements == []
    assert "chưa khả dụng" in result.criteria.gra.feedback
    assert result.criteria.gra.evidence[0].quote == "“Fictional parks”—useful, aren’t they?"
    assert not service.failures
    assert [d.stage for d in service.diagnostics] == ["feedback"] * (3 if repair else 2)
    assert service.diagnostics[-1].reason == "FEEDBACK_FALLBACK_USED"
    assert sum(e == "criterion.retrying" for e, _ in events) == int(repair)
    assert not any(e == "criterion.failed" for e, _ in events)
    assert [p.criterion for e, p in events if e == "criterion.completed"] == [
        "ta",
        "cc",
        "lr",
        "gra",
    ]


def test_optional_calibration_is_excluded_from_core_serialization_and_repr():
    parsed = ScoringOutput.model_validate({**CORE, "calibration": {"private": "private content"}})
    assert parsed.model_dump(mode="json") == CORE
    assert "private" not in repr(parsed)


async def test_unknown_auxiliary_id_is_omitted_and_all_criteria_complete():
    bad = {"evidence": [{"source_id": "P99S1", "assessment": "Nhận xét."}]}
    provider = CoreProvider({7: bad})
    result, service, events = await run(provider)
    assert result.overall_band == 8.5 and len(provider.calls) == 12 and not service.failures
    assert [d.reason for d in service.diagnostics] == ["EVIDENCE_ITEM_DROPPED"]
    assert [p.criterion for e, p in events if e == "criterion.completed"] == [
        "ta",
        "cc",
        "lr",
        "gra",
    ]


async def test_truncated_score_is_never_accepted():
    truncated = Completion('{"score":8.5', finish_reason="length")
    provider = CoreProvider({9: truncated, 10: truncated})
    result, service, _ = await run(provider)
    assert result is None and len(provider.calls) == 11
    assert [d.reason for d in service.diagnostics] == ["PROVIDER_FINISH_LENGTH"] * 2
    assert all(d.finish_reason == "length" for d in service.diagnostics)
    assert all(d.stage == "score" for d in service.diagnostics)


async def test_feedback_failure_logs_safe_field_type_and_masks_untrusted_extra_names(caplog):
    caplog.set_level("INFO", logger="app.services.mts_writing")
    invalid = {
        "observations": [
            {
                **OBSERVATIONS["observations"][0],
                "observation": 42,
                "private-secret-key": "private rejected value",
            }
        ]
    }
    result, service, events = await run(CoreProvider({11: invalid, 12: invalid}))
    assert result.criteria.gra.score == Decimal("8.5") and not service.failures
    for diagnostic in service.diagnostics[:1]:
        assert diagnostic.stage == "feedback"
        assert {(i.field, i.validation_type) for i in diagnostic.validation_issues} == {
            ("observations.0.observation", "string_type"),
            ("observations.0.<extra>", "extra_forbidden"),
        }
    assert "field=observations.0.observation validation_type=string_type" in caplog.text
    assert "field=observations.0.<extra> validation_type=extra_forbidden" in caplog.text
    public = str(events)
    assert "validation_type" not in public
    assert "private" not in public
    retained = caplog.text + str(service.diagnostics)
    for forbidden in ["private", CORE["feedback"], ESSAY, "Discuss fictional parks."]:
        assert forbidden not in retained
