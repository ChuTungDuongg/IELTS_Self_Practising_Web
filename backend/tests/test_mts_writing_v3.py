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
                assert properties == {"feedback", "strengths", "improvements"}
                value = json.dumps(FEEDBACK)
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
    assert set(provider.schemas[1]["properties"]) == {"score"}
    assert set(provider.schemas[2]["properties"]) == {"feedback", "strengths", "improvements"}
    assert json.loads(provider.calls[2][1]["content"])["fixed_score"] == 6.5
    for index in range(0, 12, 3):
        assert [set(s["properties"]) for s in provider.schemas[index : index + 3]] == [
            {"evidence"},
            {"score"},
            {"feedback", "strengths", "improvements"},
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
    ]:
        assert effective_prompt_version(old) == "mts-task2-v9"
    assert effective_prompt_version("custom") == "mts-task2-v9:custom"


@pytest.mark.parametrize(
    "output,reason",
    [
        ("private malformed", "INVALID_JSON"),
        (
            json.dumps({"evidence": [{"source_id": "P99S1", "assessment": "Nhận xét."}]}),
            "EVIDENCE_UNKNOWN_SOURCE_ID",
        ),
        (
            json.dumps({"evidence": [{"quote": "private copy", "assessment": "Nhận xét."}]}),
            "EVIDENCE_SCHEMA_INVALID",
        ),
        (json.dumps({"evidence": EVIDENCE["evidence"] * 5}), "TOO_MANY_EVIDENCE_ITEMS"),
        (
            json.dumps({"evidence": [{"source_id": "P1S1", "assessment": "x" * 321}]}),
            "EVIDENCE_ITEM_TOO_LONG",
        ),
        (Completion('{"evidence":[', finish_reason="length"), "PROVIDER_FINISH_LENGTH"),
    ],
)
async def test_targeted_repair_and_safe_diagnostics(output, reason, caplog):
    provider = Provider({0: output})
    result, mts, events = await assess(provider)
    assert result.overall_band == 6.5 and len(provider.calls) == 13
    assert reason in provider.calls[1][-1]["content"]
    assert mts.diagnostics[0].reason == reason and mts.diagnostics[0].attempt == 1
    assert mts.diagnostics[0].stage == "evidence"
    assert sum(e == "criterion.retrying" for e, _ in events) == 1
    assert "private" not in caplog.text + str(mts.diagnostics) + str(events)


async def test_lr_failed_after_repair_gra_still_runs_and_aggregate_absent():
    bad = json.dumps({"evidence": [{"source_id": "P99S1", "assessment": "Nhận xét."}]})
    provider = Provider({6: bad, 7: bad})
    result, mts, events = await assess(provider)
    assert result is None
    assert len(provider.calls) == 11
    assert [
        (e, p.criterion) for e, p in events if e in {"criterion.completed", "criterion.failed"}
    ] == [
        ("criterion.completed", "ta"),
        ("criterion.completed", "cc"),
        ("criterion.failed", "lr"),
        ("criterion.completed", "gra"),
    ]
    assert mts.failures["lr"].error_code == "AI_PROVIDER_BAD_RESPONSE"
    assert [d.reason for d in mts.diagnostics] == ["EVIDENCE_UNKNOWN_SOURCE_ID"] * 2


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
    result, mts, _ = await assess(Provider({4: json.dumps({"score": score})}))
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
        assert "already validated and authoritative" in feedback
        assert "Feedback is one concise Vietnamese paragraph" in feedback
        for other in TRAIT_NAMES.values():
            if other != name:
                assert other not in prompt + feedback
        for concept in forbidden[trait]:
            assert concept not in (prompt + feedback).lower()


@pytest.mark.parametrize(
    "field,value",
    [
        ("strengths", ["Nhận xét."] * 4),
        ("improvements", ["Nhận xét."] * 4),
        ("feedback", "x" * 801),
    ],
)
async def test_feedback_display_limits_normalize_without_repair(field, value):
    provider = Provider({2: json.dumps({**FEEDBACK, field: value})})
    result, mts, _ = await assess(provider)
    assert result.overall_band == 6.5 and len(provider.calls) == 12
    assert mts.diagnostics[0].stage == "feedback"
    assert mts.diagnostics[0].reason == "FEEDBACK_PRESENTATION_NORMALIZED"


async def test_two_length_completions_fail_one_criterion_and_continue():
    truncated = Completion('{"evidence":[', finish_reason="length")
    provider = Provider({6: truncated, 7: truncated})
    result, mts, events = await assess(provider)
    assert result is None and len(provider.calls) == 11
    assert [d.reason for d in mts.diagnostics] == ["PROVIDER_FINISH_LENGTH"] * 2
    assert all(d.finish_reason == "length" for d in mts.diagnostics)
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
