"""Runtime explanation regressions: strict scores, local item sanitization only."""

import asyncio
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from test_task1_visual import Task1FakeProvider
from test_task1_visual import request as task1_request
from test_writing_completion_budgets import BudgetProvider, assess, stage_calls

from app.domains.scoring.writing import WritingScoringRequest
from app.providers.writing_llm.base import Completion, ProviderFailure
from app.services.mts_writing import FEEDBACK_FALLBACK
from app.services.task1_writing import Task1WritingScoringService
from app.services.writing_execution import TraceFailure

ESSAY = "Neighbours share tools. Gardens provide shared routines. Costs need planning. Residents cooperate."
LONG = "Lời giải thích tiếng Việt có dấu. " * 25


def request():
    return WritingScoringRequest(
        attempt_id=uuid4(),
        writing_task_id=uuid4(),
        prompt="Discuss fictional community gardens.",
        response=ESSAY,
    )


def observation(**changes):
    return {
        "source_id": "P1S1",
        "kind": "STRENGTH",
        "observation": "Ý chính được diễn đạt rõ ràng.",
        "confidence": "HIGH",
        "original_span": None,
        "suggested_revision": None,
        **changes,
    }


def changed_observation(**changes):
    return {**observation(), **changes}


def evidence_event(events):
    return next(
        p.evidence for e, p in events if e == "criterion.evidence.completed" and p.criterion == "ta"
    )


@pytest.mark.parametrize("count", [1, 4])
async def test_stopped_oversized_evidence_normalizes_without_a_retry(count, caplog):
    items = [
        dict(
            source_id=f"P1S{i + 1}",
            assessment=LONG if i == count - 1 else "Dẫn chứng phù hợp.",
            focus=LONG,
        )
        for i in range(count)
    ]
    provider = BudgetProvider(evidence=[{"evidence": items}])
    result, service, events = await assess(provider, request=request())
    assert result is not None and result.criteria.ta.score == Decimal("6.5")
    assert not service.failures and len(provider.calls) == 12
    assert not any(e == "criterion.retrying" for e, _ in events)
    selected = evidence_event(events)
    assert len(selected) == count and all(len(e.assessment) <= 320 for e in selected)
    assert [e.source_id for e in selected] == [f"P1S{i + 1}" for i in range(count)]
    assert any(d.reason == "EVIDENCE_PRESENTATION_NORMALIZED" for d in service.diagnostics)
    assert LONG not in caplog.text + str(service.diagnostics)


@pytest.mark.parametrize(
    "items",
    [
        [dict(source_id="P1S1", assessment=" \n\t")],
        [
            dict(source_id="P99S1", assessment="Dẫn chứng."),
            None,
            {"source_id": "P1S1", "assessment": 42},
        ],
    ],
)
async def test_unusable_evidence_is_empty_and_cannot_block_valid_score(items):
    provider = BudgetProvider(evidence=[{"evidence": items}])
    result, service, events = await assess(provider, request=request())
    assert result is not None and not service.failures and result.overall_band == Decimal("6.5")
    assert len(provider.calls) == 12 and evidence_event(events) == []
    feedback_payload = json.loads(stage_calls(provider, "feedback")[0][0][1]["content"])
    assert feedback_payload["selected_source_ids"] == []


async def test_invalid_evidence_items_do_not_hide_valid_items_or_exceed_four():
    items = (
        [None, dict(source_id="P99S1", assessment="Dẫn chứng.")]
        + [dict(source_id=f"P1S{i + 1}", assessment="Dẫn chứng.") for i in range(4)]
        + [dict(source_id="P1S1", assessment="Lặp lại.")]
    )
    provider = BudgetProvider(evidence=[{"evidence": items}])
    result, _, events = await assess(provider, request=request())
    assert result is not None and len(provider.calls) == 12
    assert [item.source_id for item in evidence_event(events)] == [f"P1S{i + 1}" for i in range(4)]


@pytest.mark.parametrize(
    "bad",
    [
        {"source_id": "P99S1"},
        {"kind": "ERROR", "original_span": "invented source wording"},
        {"kind": "ERROR", "original_span": "Neighbours", "confidence": "MEDIUM"},
        {"kind": "LIMITATION", "confidence": "LOW"},
        {"observation": "Sai ở đoạn 2 câu 3."},
        {"observation": "Weak P2S3."},
        {"observation": "Có thể đạt Band 8."},
        {
            "kind": "OPTIONAL_REFINEMENT",
            "original_span": "invented wording",
            "suggested_revision": "Other words.",
        },
    ],
)
async def test_bad_feedback_item_is_local_and_valid_strength_survives(bad):
    provider = BudgetProvider(
        feedback=[{"observations": [observation(), changed_observation(**bad)]}]
    )
    result, service, events = await assess(provider, request=request())
    assert result is not None and result.criteria.ta.strengths and not service.failures
    assert len(provider.calls) == 12 and not any(e == "criterion.retrying" for e, _ in events)
    assert result.criteria.ta.improvements == []
    assert any(d.reason == "FEEDBACK_OBSERVATION_DROPPED" for d in service.diagnostics)


@pytest.mark.parametrize("trait", ["lr", "gra"])
@pytest.mark.parametrize("span", ["invented wording", None, " "])
async def test_all_ungrounded_language_errors_fall_back_without_score_loss(trait, span):
    class Provider(BudgetProvider):
        async def complete(self, messages, schema, *, options=None):
            if "observations" in schema["properties"]:
                self.calls.append((messages, schema, options))
                return Completion(
                    json.dumps(
                        {
                            "observations": [
                                changed_observation(
                                    kind="ERROR",
                                    original_span=span,
                                    observation="PRIVATE incorrect error.",
                                )
                            ]
                        }
                    )
                )
            return await super().complete(messages, schema, options=options)

    provider = Provider()
    result, service, events = await assess(provider, request=request())
    card = getattr(result.criteria, trait)
    assert card.score == Decimal("6.5") and card.feedback == FEEDBACK_FALLBACK
    assert card.strengths == card.improvements == [] and not service.failures
    assert len(provider.calls) == 12 and "PRIVATE" not in card.model_dump_json()
    assert not any(e == "criterion.retrying" for e, _ in events)


@pytest.mark.parametrize("kind", ["STRENGTH", "LIMITATION"])
async def test_imperfect_optional_span_drops_only_quote_and_revision(kind):
    provider = BudgetProvider(
        feedback=[
            {
                "observations": [
                    changed_observation(
                        kind=kind,
                        original_span="not exact",
                        suggested_revision="Cannot be grounded.",
                    )
                ]
            }
        ]
    )
    result, _, _ = await assess(provider, request=request())
    assert result is not None and observation()["observation"] in result.criteria.ta.feedback
    assert "Cannot be grounded" not in result.model_dump_json() and len(provider.calls) == 12


@pytest.mark.parametrize("field", ["observation", "suggested_revision"])
async def test_long_feedback_display_strings_are_bounded_without_retry(field):
    value = changed_observation(**{field: LONG})
    if field == "suggested_revision":
        value.update(kind="OPTIONAL_REFINEMENT", original_span="share tools")
    provider = BudgetProvider(feedback=[{"observations": [value]}])
    result, service, _ = await assess(provider, request=request())
    assert result is not None and len(provider.calls) == 12 and not service.failures
    card = result.criteria.ta
    assert all(0 < len(s) <= 240 for s in card.strengths + card.improvements)
    reason = (
        "FEEDBACK_OBSERVATION_DROPPED"
        if field == "suggested_revision"
        else "FEEDBACK_PRESENTATION_NORMALIZED"
    )
    assert any(d.reason == reason for d in service.diagnostics)
    if field == "suggested_revision":
        assert card.annotations == [] and card.improvements == []


@pytest.mark.parametrize("stage", ["evidence", "feedback"])
async def test_structurally_invalid_explanations_retry_once_then_keep_score(stage):
    for bad in (
        Completion("broken JSON"),
        {stage if stage == "evidence" else "observations": {}},
        Completion("{}", finish_reason="length"),
    ):
        provider = BudgetProvider(**{stage: [bad, bad]})
        result, service, events = await assess(provider, request=request())
        assert result is not None and result.criteria.ta.score == Decimal("6.5")
        assert len(provider.calls) == 13 and len(stage_calls(provider, "score")) == 4
        assert sum(e == "criterion.retrying" for e, _ in events) == 1
        assert not service.failures
        assert any(
            d.reason
            == ("EVIDENCE_FALLBACK_USED" if stage == "evidence" else "FEEDBACK_FALLBACK_USED")
            for d in service.diagnostics
        )


async def test_invalid_score_is_still_fatal_after_one_repair():
    provider = BudgetProvider(score=[{"score": 6.3}, {"score": 6.3}])
    result, service, _ = await assess(provider, request=request())
    assert result is None and set(service.failures) == {"ta"}
    assert len(stage_calls(provider, "score")) == 5 and len(stage_calls(provider, "evidence")) == 3


@pytest.mark.parametrize("stage", ["evidence", "feedback"])
@pytest.mark.parametrize(
    "code", ["AI_PROVIDER_AUTH_FAILED", "AI_PROVIDER_TIMEOUT", "AI_PROVIDER_HTTP_ERROR"]
)
async def test_real_provider_failures_remain_failures(stage, code):
    provider = BudgetProvider(**{stage: [ProviderFailure(code)]})
    result, service, _ = await assess(provider, request=request())
    assert result is None and service.failures["ta"].error_code == code


@pytest.mark.parametrize("stage", ["evidence", "feedback"])
@pytest.mark.parametrize("failure", [asyncio.CancelledError, TraceFailure, RuntimeError])
async def test_cancellation_stop_and_application_errors_are_not_explanation_fallback(
    stage, failure
):
    class Provider(BudgetProvider):
        async def complete(self, messages, schema, *, options=None):
            if (stage == "evidence" and "evidence" in schema["properties"]) or (
                stage == "feedback" and "observations" in schema["properties"]
            ):
                raise failure()
            return await super().complete(messages, schema, options=options)

    if failure is RuntimeError:
        result, service, _ = await assess(Provider(), request=request())
        assert result is None and service.failures
    else:
        with pytest.raises(failure):
            await assess(Provider(), request=request())


async def test_task1_evidence_remains_strict_on_oversized_assessments():
    class Provider(Task1FakeProvider):
        async def complete(self, messages, schema, *, options=None):
            if "evidence" in schema["properties"]:
                return Completion(
                    json.dumps({"evidence": [{"source_id": "P1S1", "assessment": LONG}]})
                )
            return await super().complete(messages, schema, options=options)

    result, service, _ = await assess(
        Provider(), service_type=Task1WritingScoringService, request=task1_request()
    )
    assert result is None and len(service.failures) == 4
    assert all(d.reason == "EVIDENCE_ITEM_TOO_LONG" for d in service.diagnostics)


def test_raw_provider_schema_guides_structure_and_local_sanitizer_enforces_bounds():
    from pydantic import ValidationError

    from app.domains.scoring.essay_sources import segment_essay
    from app.domains.scoring.task2_explanations import normalize_task2_evidence
    from app.domains.scoring.task2_feedback import normalize_task2_feedback
    from app.providers.writing_llm.vllm import guided_json_schema
    from app.schemas.writing_ai import RawTask2EvidenceSelection, RawTask2FeedbackDraft

    sources = {s.source_id: s for s in segment_essay(ESSAY)}
    raw = RawTask2EvidenceSelection.model_validate(
        {"evidence": [{"source_id": "P1S1", "assessment": LONG, "focus": LONG}]}
    )
    selected, _ = normalize_task2_evidence(raw, sources)
    assert (
        selected.evidence[0].assessment.endswith("…")
        and len(selected.evidence[0].assessment) <= 320
    )
    assert len(selected.evidence[0].focus) <= 160
    raw = RawTask2FeedbackDraft.model_validate(
        {
            "observations": [
                changed_observation(
                    kind="OPTIONAL_REFINEMENT", original_span="share tools", suggested_revision=LONG
                )
            ]
        }
    )
    selected, _ = normalize_task2_feedback(raw, sources, "gra", Decimal("6.5"))
    assert selected.observations == []  # Never clip a rewrite into a partial suggestion.
    guided = guided_json_schema(RawTask2FeedbackDraft.model_json_schema())
    item = guided["properties"]["observations"]["items"]
    assert item["properties"]["observation"]["type"] == "string"
    assert item["properties"]["confidence"]["enum"] == ["HIGH", "MEDIUM", "LOW"]
    assert item["additionalProperties"] is False
    assert "maxLength" not in json.dumps(guided) and "score" not in guided["properties"]
    with pytest.raises(ValidationError):
        RawTask2FeedbackDraft(observations=[], score=9)


@pytest.mark.parametrize("span", [None, "invented wording"])
@pytest.mark.parametrize(
    "trait,name", [("lr", "Lexical Resource"), ("gra", "Grammatical Range and Accuracy")]
)
async def test_language_error_drop_preserves_other_valid_observations(trait, name, span):
    class Provider(BudgetProvider):
        async def complete(self, messages, schema, *, options=None):
            if (
                "observations" in schema["properties"]
                and f"Criterion: {name}." in messages[0]["content"]
            ):
                self.calls.append((messages, schema, options))
                return Completion(
                    json.dumps(
                        {
                            "observations": [
                                observation(),
                                changed_observation(
                                    kind="ERROR",
                                    original_span=span,
                                    observation="PRIVATE error claim.",
                                ),
                            ]
                        }
                    )
                )
            return await super().complete(messages, schema, options=options)

    provider = Provider()
    result, service, _ = await assess(provider, request=request())
    card = getattr(result.criteria, trait)
    assert card.score == Decimal("6.5") and len(card.strengths) == 1 and card.improvements == []
    assert "PRIVATE" not in card.model_dump_json() and len(provider.calls) == 12
    assert not service.failures


async def test_auxiliary_normalization_never_changes_score_requests_or_recomputes_scores():
    providers = [
        BudgetProvider(evidence=[value])
        for value in (
            {"evidence": [{"source_id": "P1S1", "assessment": LONG}]},
            {"evidence": [{"source_id": "P1S1", "assessment": "   "}]},
            {"evidence": [{"source_id": "P99S1", "assessment": "Wrong source."}]},
        )
    ]
    req = request()
    for provider in providers:
        result, _, _ = await assess(provider, request=req)
        assert result.overall_band == Decimal("6.5") and len(provider.calls) == 12
    calls = [stage_calls(provider, "score") for provider in providers]
    assert len(calls[0]) == 4 and calls[0] == calls[1] == calls[2]


def test_feedback_length_errors_are_not_classified_as_evidence_errors():
    from pydantic import ValidationError

    from app.domains.scoring.ai_writing_validation import validation_reason
    from app.schemas.writing_ai import EvidenceSelection

    with pytest.raises(ValidationError) as failure:
        EvidenceSelection(evidence=[{"source_id": "P1S1", "assessment": LONG}])
    assert validation_reason(failure.value, "evidence") == "EVIDENCE_ITEM_TOO_LONG"
    assert validation_reason(failure.value, "feedback") == "FEEDBACK_SCHEMA_INVALID"


@pytest.mark.parametrize("kind", ["ERROR", "OPTIONAL_REFINEMENT"])
def test_original_span_is_never_truncated_into_a_matching_quote(kind):
    from app.domains.scoring.essay_sources import segment_essay
    from app.domains.scoring.task2_feedback import normalize_task2_feedback
    from app.schemas.writing_ai import RawTask2FeedbackDraft

    # Its long prefix exists, but the complete span has fabricated suffix text.
    essay = "x" * 11999 + "."
    sources = {s.source_id: s for s in segment_essay(essay)}
    raw = RawTask2FeedbackDraft(
        observations=[
            changed_observation(
                kind=kind,
                original_span=essay + " fabricated",
                suggested_revision="A different sentence.",
            )
        ]
    )
    value, issues = normalize_task2_feedback(raw, sources, "gra", Decimal("6.5"))
    assert not value.observations and issues.dropped


def test_feedback_item_cap_does_not_let_invalid_items_hide_valid_observations():
    from app.domains.scoring.essay_sources import segment_essay
    from app.domains.scoring.task2_feedback import normalize_task2_feedback
    from app.schemas.writing_ai import RawTask2FeedbackDraft

    sources = {s.source_id: s for s in segment_essay(ESSAY)}
    raw = RawTask2FeedbackDraft(
        observations=[None]
        + [changed_observation(observation=f"Ý hỗ trợ rõ ràng {i}.") for i in range(8)]
    )
    value, issues = normalize_task2_feedback(raw, sources, "gra", Decimal("6.5"))
    assert len(value.observations) == 4 and issues.normalized and issues.dropped


def test_high_confidence_language_error_retains_its_exact_span_and_kind():
    from app.domains.scoring.essay_sources import segment_essay
    from app.domains.scoring.task2_feedback import normalize_task2_feedback
    from app.schemas.writing_ai import RawTask2FeedbackDraft

    sources = {s.source_id: s for s in segment_essay("Residents shares tools.")}
    raw = RawTask2FeedbackDraft(
        observations=[
            changed_observation(
                kind="ERROR",
                observation="Động từ chưa hòa hợp với chủ ngữ.",
                original_span="shares",
                suggested_revision="share",
            )
        ]
    )
    value, issues = normalize_task2_feedback(raw, sources, "gra", Decimal("6.5"))
    assert value.observations[0].kind == "ERROR" and value.observations[0].original_span == "shares"
    assert not issues.normalized and not issues.dropped


async def test_source_quotes_exceeding_public_bounds_do_not_block_score():
    req = request()
    req.response = "x" * 12001 + "."
    provider = BudgetProvider()
    result, service, events = await assess(provider, request=req)
    assert (
        result.overall_band == Decimal("6.5") and len(provider.calls) == 12 and not service.failures
    )
    assert evidence_event(events) == []
    assert result.criteria.gra.feedback == FEEDBACK_FALLBACK


@pytest.mark.parametrize("ending", [" paragraph 8.", " Band 8."])
async def test_unsafe_prose_is_checked_before_presentation_truncation(ending):
    provider = BudgetProvider(
        feedback=[{"observations": [observation(), changed_observation(observation=LONG + ending)]}]
    )
    result, service, _ = await assess(provider, request=request())
    assert len(provider.calls) == 12 and len(result.criteria.ta.strengths) == 1
    assert any(d.reason == "FEEDBACK_OBSERVATION_DROPPED" for d in service.diagnostics)


@pytest.mark.parametrize("finish", ["abort", "error", "content_filter"])
@pytest.mark.parametrize("stage", ["evidence", "feedback"])
async def test_non_stop_provider_failures_cannot_use_best_effort_fallback(stage, finish):
    invalid = Completion("{}", finish_reason=finish)
    result, service, _ = await assess(
        BudgetProvider(**{stage: [invalid, invalid]}), request=request()
    )
    assert result is None and service.failures["ta"]
    assert not any(
        d.reason in {"EVIDENCE_FALLBACK_USED", "FEEDBACK_FALLBACK_USED"}
        for d in service.diagnostics
    )
