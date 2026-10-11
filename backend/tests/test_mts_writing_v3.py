import json
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domains.scoring.ai_writing_normalization import normalize_scoring_output
from app.domains.scoring.ai_writing_validation import resolve_evidence, sanitize_calibration
from app.domains.scoring.essay_sources import segment_essay
from app.domains.scoring.mts_prompts import effective_prompt_version
from app.domains.scoring.writing import WritingScoringRequest
from app.providers.writing_llm.base import Completion, ProviderFailure
from app.schemas.writing_ai import EvidenceSelection, RawScoringOutput
from app.services.mts_writing import MTSWritingScoringService

ESSAY = "“Fictional parks”—useful, aren’t they?  They  help city life.\r\n\r\nCosts matter–too."
EVIDENCE = {"evidence": [{"source_id": "P1S2", "assessment": "Luận điểm liên quan đến đề bài."}]}
SCORE = {"score": 6.5}
FEEDBACK = {
    "feedback": "Luận điểm rõ nhưng cần phát triển ví dụ để đạt mức cao hơn.",
    "strengths": ["Lập trường rõ ràng."],
    "improvements": ["Phát triển dẫn chứng."],
}
LEGACY_SCORE = {
    **SCORE,
    **FEEDBACK,
    "calibration": {
        "support": [{"source_id": "P1S2", "assessment": "Luận điểm có liên hệ rõ."}],
        "next_band": 7.0,
        "next_band_blockers": [
            {
                "source_id": "P2S1",
                "severity": "recurring",
                "assessment": "Các ý hỗ trợ còn rời rạc.",
            }
        ],
        "comparison": "Liên kết ý chưa ổn định để đạt mức kế tiếp.",
        "high_band_justification": None,
    },
}
OBSERVATIONS = {
    "observations": [
        {
            "source_id": "P1S2",
            "kind": "STRENGTH",
            "observation": "Luận điểm liên quan đến đề bài.",
            "confidence": "HIGH",
        }
    ]
}


class Provider:
    def __init__(self, overrides=None):
        self.overrides, self.calls = overrides or {}, []
        self.schemas = []

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
        self.calls.append(messages)
        self.schemas.append(schema)
        value = self.overrides.get(index)
        if isinstance(value, ProviderFailure):
            raise value
        if isinstance(value, Completion):
            return value
        if value is None:
            properties = set(schema["properties"])
            if properties == {"evidence"}:
                value = json.dumps(EVIDENCE)
            elif properties == {"score"}:
                value = json.dumps(SCORE)
            else:
                assert properties == {"observations"}
                value = json.dumps(OBSERVATIONS)
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


def test_lookup_multiple_ids_preserves_exact_original_unicode_whitespace():
    sources = {s.source_id: s for s in segment_essay(ESSAY)}
    selected = EvidenceSelection.model_validate(
        {
            "evidence": [
                {
                    "source_id": "P1S1",
                    "assessment": "Nhận xét.",
                    "focus": "Different punctuation is harmless",
                },
                {"source_id": "P1S2", "assessment": "Nhận xét."},
            ]
        }
    )
    resolved = resolve_evidence(selected, sources)
    assert [e.quote for e in resolved.evidence] == [
        "“Fictional parks”—useful, aren’t they?",
        "They  help city life.",
    ]
    assert [e.source_id for e in resolved.evidence] == ["P1S1", "P1S2"]
    for item in resolved.evidence:
        s = sources[item.source_id]
        assert item.quote == ESSAY[s.start : s.end]


async def test_vietnamese_independent_prompts_and_cache_version():
    provider = Provider()
    result, mts, events = await assess(provider)
    assert result.criteria.lr.evidence[0].quote == "They  help city life."
    assert len(provider.calls) == 12 and not mts.diagnostics
    for messages in provider.calls:
        assert "Vietnamese" in messages[0]["content"] and "UNTRUSTED DATA" in messages[0]["content"]
    data = json.loads(provider.calls[0][1]["content"])
    assert "[P1S2] They  help city life." in data["segmented_essay"]
    assert set(provider.schemas[0]["properties"]) == {"score"}
    assert set(data) == {"question", "segmented_essay"}
    assert set(provider.schemas[2]["properties"]) == {"observations"}
    assert json.loads(provider.calls[2][1]["content"])["fixed_score"] == 6.5
    for index in range(0, 12, 3):
        assert [set(s["properties"]) for s in provider.schemas[index : index + 3]] == [
            {"score"},
            {"evidence"},
            {"observations"},
        ]
    assert sum(e == "criterion.completed" for e, _ in events) == 4
    for old in [
        "mts-task2-v1",
        "mts-task2-v2",
        "mts-task2-v3",
        "mts-task2-v4",
        "mts-task2-v5",
        "mts-task2-v6",
        "mts-task2-v7",
        "mts-task2-v8",
        "mts-task2-v9",
        "mts-task2-v10",
    ]:
        assert effective_prompt_version(old) == "mts-task2-v11"
    assert effective_prompt_version("custom") == "mts-task2-v11:custom"


@pytest.mark.parametrize(
    "output,reason,repair",
    [
        ("private malformed", "INVALID_JSON", True),
        (
            json.dumps({"evidence": [{"source_id": "P99S1", "assessment": "Nhận xét."}]}),
            "EVIDENCE_ITEM_DROPPED",
            False,
        ),
        (
            json.dumps({"evidence": [{"quote": "private copy", "assessment": "Nhận xét."}]}),
            "EVIDENCE_ITEM_DROPPED",
            False,
        ),
        (
            json.dumps({"evidence": EVIDENCE["evidence"] * 5}),
            "EVIDENCE_PRESENTATION_NORMALIZED",
            False,
        ),
        (
            json.dumps({"evidence": [{"source_id": "P1S1", "assessment": "x" * 321}]}),
            "EVIDENCE_PRESENTATION_NORMALIZED",
            False,
        ),
        (Completion('{"evidence":[', finish_reason="length"), "PROVIDER_FINISH_LENGTH", True),
    ],
)
async def test_evidence_repairs_structure_but_normalizes_items_locally(
    output, reason, repair, caplog
):
    provider = Provider({1: output})
    result, mts, events = await assess(provider)
    assert result.overall_band == 6.5 and len(provider.calls) == 12 + int(repair)
    if repair:
        assert reason in provider.calls[2][-1]["content"]
    assert mts.diagnostics[0].reason == reason and mts.diagnostics[0].attempt == 1
    assert mts.diagnostics[0].stage == "evidence"
    assert sum(e == "criterion.retrying" for e, _ in events) == int(repair)
    assert "private" not in caplog.text + str(mts.diagnostics) + str(events)


async def test_unusable_lr_evidence_keeps_fixed_score_and_later_criteria():
    bad = json.dumps({"evidence": [{"source_id": "P99S1", "assessment": "Nhận xét."}]})
    provider = Provider({7: bad})
    result, mts, events = await assess(provider)
    assert result.overall_band == 6.5
    assert len(provider.calls) == 12
    assert [
        (e, p.criterion) for e, p in events if e in {"criterion.completed", "criterion.failed"}
    ] == [
        ("criterion.completed", "ta"),
        ("criterion.completed", "cc"),
        ("criterion.completed", "lr"),
        ("criterion.completed", "gra"),
    ]
    assert not mts.failures
    assert [d.reason for d in mts.diagnostics] == ["EVIDENCE_ITEM_DROPPED"]


@pytest.mark.parametrize(
    "score,next_band,severity",
    [
        (4, 5, "substantial"),
        (7, 8, "recurring"),
        (7.5, 8, "isolated"),
        (8.5, 9, "isolated"),
        (9, None, None),
    ],
)
async def test_synthetic_cc_descriptor_fit_profiles_have_no_deterministic_score_adjustment(
    score, next_band, severity
):
    value = {
        **LEGACY_SCORE,
        "score": score,
        "calibration": {
            "support": [
                {"source_id": "P1S1", "assessment": "Quan điểm rõ."},
                {"source_id": "P1S2", "assessment": "Ý nối tiếp có kiểm soát."},
            ],
            "next_band": next_band,
            "next_band_blockers": []
            if severity is None
            else [
                {
                    "source_id": "P2S1",
                    "severity": severity,
                    "assessment": "Mức hạn chế đã quan sát.",
                }
            ],
            "comparison": "Đối chiếu mức liền kề dựa trên dẫn chứng.",
            "high_band_justification": "Nhiều vị trí có liên kết được kiểm soát."
            if score >= 7.5
            else None,
        },
    }
    result, mts, _ = await assess(Provider({3: json.dumps({"score": score})}))
    assert result.criteria.cc.score == score
    assert not mts.diagnostics
    raw = RawScoringOutput.model_validate(value)
    calibration, reasons = sanitize_calibration(
        raw.calibration, raw.score, {s.source_id: s for s in segment_essay(ESSAY)}
    )
    historical, issues = normalize_scoring_output(raw)
    assert historical.score == Decimal(str(score))
    assert calibration.next_band == next_band
    assert not reasons and not issues


@pytest.mark.parametrize(
    "mutation", ["missing_justification", "wrong_next_band", "no_blockers", "unknown_source"]
)
def test_historical_high_band_optional_explanation_artifacts_never_gate_score(mutation):
    c = {
        **LEGACY_SCORE["calibration"],
        "next_band": 9,
        "support": [
            {"source_id": "P1S1", "assessment": "Liên kết rõ."},
            {"source_id": "P1S2", "assessment": "Trình tự ý có kiểm soát."},
        ],
        "next_band_blockers": [
            {
                "source_id": "P2S1",
                "severity": "isolated",
                "assessment": "Một liên kết chưa tự nhiên.",
            }
        ],
        "high_band_justification": "Liên kết tốt ở nhiều vị trí.",
    }
    if mutation == "missing_justification":
        c["high_band_justification"] = None
    if mutation == "wrong_next_band":
        c["next_band"] = 8.5
    if mutation == "no_blockers":
        c["next_band_blockers"] = []
    if mutation == "unknown_source":
        c["support"][0]["source_id"] = "P99S1"
    raw = RawScoringOutput.model_validate({**LEGACY_SCORE, "score": 8.5, "calibration": c})
    calibration, reasons = sanitize_calibration(
        raw.calibration, raw.score, {s.source_id: s for s in segment_essay(ESSAY)}
    )
    result, issues = normalize_scoring_output(raw)
    assert result.score == Decimal("8.5") and calibration.next_band == 9
    assert not issues
    assert all(reason.startswith("CALIBRATION_") for reason in reasons)
    if mutation == "unknown_source":
        assert [item.source_id for item in calibration.support] == ["P1S2"]
        assert "CALIBRATION_SOURCE_DROPPED" in reasons


def test_long_original_sentence_survives_without_legacy_copy_limit():
    essay = "Parks " + "help  " * 200 + "cities."
    selected = EvidenceSelection.model_validate(
        {"evidence": [{"source_id": "P1S1", "assessment": "Nhận xét."}]}
    )
    resolved = resolve_evidence(selected, {s.source_id: s for s in segment_essay(essay)})
    assert resolved.evidence[0].quote == essay


def test_prompt_scope_descriptor_fit_interpolation_and_vietnamese_fields():
    from app.domains.scoring.mts_prompts import TRAIT_NAMES, feedback_messages, scoring_messages
    from app.schemas.writing_ai import EvidenceResult

    forbidden = {
        "ta": ["collocation", "grammatical range"],
        "cc": ["spelling", "word formation"],
        "lr": ["grammatical range", "task coverage"],
        "gra": ["collocation", "task coverage"],
    }
    for trait, name in TRAIT_NAMES.items():
        prompt = scoring_messages("Fictional question", ESSAY, trait, EvidenceResult(evidence=[]))[
            0
        ]["content"]
        assert name in prompt
        assert "official IELTS Writing Task 2 Band Descriptors" in prompt
        assert "interpolation between adjacent official whole-band descriptors" in prompt
        assert "Do not favor the higher or lower band by default" in prompt
        assert "Return ONLY one field: score" in prompt
        assert json.loads(prompt.split("JSON schema: ")[1])["required"] == ["score"]
        feedback = feedback_messages(
            "Fictional question", ESSAY, trait, EvidenceResult(evidence=[]), Decimal("6.5")
        )[0]["content"]
        assert "immutable metadata for consistency" in feedback
        assert "Return only observations" in feedback
        assert json.loads(feedback.split("JSON schema: ")[1])["required"] == ["observations"]
        for other in TRAIT_NAMES.values():
            if other != name:
                assert other not in prompt + feedback
        for concept in forbidden[trait]:
            assert concept not in (prompt + feedback).lower()


@pytest.mark.parametrize(
    "kinds",
    [
        ["STRENGTH"] * 6,
        ["LIMITATION"] * 6,
        ["STRENGTH"] * 3 + ["LIMITATION"] * 3,
    ],
)
async def test_backend_observation_display_limits_remain_bounded_without_repair(kinds):
    value = {
        "observations": [
            {
                "source_id": "P1S2",
                "kind": kind,
                "confidence": "HIGH",
                "observation": f"Nhận xét phù hợp {index}. " + "x" * 210,
            }
            for index, kind in enumerate(kinds)
        ]
    }
    provider = Provider({2: json.dumps(value)})
    result, mts, _ = await assess(provider)
    assert result.overall_band == 6.5 and len(provider.calls) == 12
    assert len(result.criteria.ta.feedback) <= 800
    assert len(result.criteria.ta.strengths) <= 3 and len(result.criteria.ta.improvements) <= 3
    assert all(
        len(item) <= 240 for item in result.criteria.ta.strengths + result.criteria.ta.improvements
    )
    assert not mts.diagnostics


async def test_two_auxiliary_evidence_length_failures_keep_score_and_continue():
    truncated = Completion('{"evidence":[', finish_reason="length")
    provider = Provider({7: truncated, 8: truncated})
    result, mts, events = await assess(provider)
    assert result.overall_band == 6.5 and len(provider.calls) == 13 and not mts.failures
    assert [d.reason for d in mts.diagnostics] == ["PROVIDER_FINISH_LENGTH"] * 2 + [
        "EVIDENCE_FALLBACK_USED"
    ]
    assert all(d.finish_reason == "length" for d in mts.diagnostics[:2])
    assert any(e == "criterion.completed" and p.criterion == "gra" for e, p in events)


def test_low_band_guidance_preserves_distinct_criterion_meanings():
    from app.domains.scoring.mts_prompts import scoring_messages
    from app.schemas.writing_ai import EvidenceResult

    prompts = {
        trait: scoring_messages("Fictional", ESSAY, trait, EvidenceResult(evidence=[]))[0][
            "content"
        ]
        for trait in ["ta", "cc", "lr", "gra"]
    }
    assert "wholly unrelated" in prompts["ta"]
    assert "isolated words" in prompts["lr"]
    assert "no assessable language" in prompts["gra"]
    assert "limited flexibility" in prompts["gra"]
    assert "rarely obstruct meaning" in prompts["gra"]
    assert "wholly unrelated" not in prompts["cc"] + prompts["lr"] + prompts["gra"]


def test_historical_band_nine_unavailable_higher_descriptor_metadata_is_normalized_only():
    value = {
        **LEGACY_SCORE,
        "score": 9,
        "calibration": {
            **LEGACY_SCORE["calibration"],
            "next_band": None,
            "high_band_justification": "Dẫn chứng phù hợp mức cao nhất.",
        },
    }
    raw = RawScoringOutput.model_validate(value)
    calibration, reasons = sanitize_calibration(
        raw.calibration, raw.score, {s.source_id: s for s in segment_essay(ESSAY)}
    )
    result, issues = normalize_scoring_output(raw)
    assert result.score == 9 and calibration.next_band is None
    assert calibration.next_band_blockers == [] and not issues
    assert reasons == ["CALIBRATION_METADATA_NORMALIZED"]
