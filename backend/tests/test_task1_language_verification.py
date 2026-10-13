"""Task 1's linguistic truth boundary, using scripted providers only."""

import asyncio
import json
from decimal import Decimal

import pytest
from pydantic import ValidationError
from test_task1_visual import chart, request

from app.domains.scoring.essay_sources import request_sources
from app.providers.writing_llm.base import Completion, ProviderFailure
from app.schemas.task1_claims import Task1Analysis
from app.services.task1_writing import Task1WritingScoringService
from app.services.writing_execution import TraceFailure

OVERVIEW = (
    "Overall, Spanish was by far the most commonly spoken foreign language in both years, "
    "and its share increased further over the decade."
)
COMPARISON = (
    "French and another unspecified language each accounted for 15%, while German and "
    "the ability to speak two other languages were both reported by 10% of students."
)
CHANGE = "the proportion of Spanish speakers had risen by five percentage points"
REAL_ERROR = "The percentage of students were 30%."


def candidate(span=REAL_ERROR, **changes):
    return {
        "source_id": "P1S1",
        "kind": "ERROR",
        "aspect": "grammar",
        "observation": "Động từ cần hòa hợp với chủ ngữ.",
        "original_span": span,
        "suggested_revision": "The percentage of students was 30%.",
        "confidence": "HIGH",
        "claim_id": None,
        **changes,
    }


def decision(index=0, accept=False, reason="VALID_STANDARD_ENGLISH"):
    return {"observation_index": index, "accept": accept, "reason_code": reason}


class Provider:
    def __init__(self, candidates, verification, score=7.5):
        self.candidates, self.verification, self.score = candidates, verification, score
        self.requests = []

    async def complete(self, messages, schema, *, options=None):
        self.requests.append((messages, schema, options))
        properties = schema["properties"]
        if "decisions" in properties:
            if isinstance(self.verification, BaseException):
                raise self.verification
            value = self.verification
        elif "observations" in properties:
            value = {"observations": self.candidates}
        elif "score" in properties:
            value = {"score": self.score}
        else:
            value = {"evidence": [{"source_id": "P1S1", "assessment": "Trích dẫn rõ ràng."}]}
        return value if isinstance(value, Completion) else Completion(json.dumps(value))


async def assess(essay, candidates, verification, trait="gra", score=7.5, trace=None):
    req = request().model_copy(update={"response": essay, "paragraph_mode": "textarea"})
    provider = Provider(candidates, verification, score)
    service = Task1WritingScoringService(provider)
    analysis = Task1Analysis(visual_family="chart_table", confidence="HIGH", reference=chart())
    events = []

    async def record(event, payload):
        events.append((event, payload))
        if trace:
            await trace(event, payload)

    result = await service._task1_criterion(req, trait, analysis, record)
    return result, service, provider, events, req


@pytest.mark.parametrize(
    "trait,essay,revision,kind,reason",
    [
        (
            "gra",
            OVERVIEW,
            "Spanish was the main language in both years.",
            "ERROR",
            "VALID_STANDARD_ENGLISH",
        ),
        (
            "gra",
            COMPARISON,
            "French accounted for 15%; German accounted for 10%.",
            "ERROR",
            "STYLE_ONLY",
        ),
        ("gra", COMPARISON, None, "LIMITATION", "ACCEPTABLE_ALTERNATIVE"),
        ("lr", CHANGE, "increased by 5 percentage points", "ERROR", "ACCEPTABLE_ALTERNATIVE"),
        ("lr", CHANGE, None, "LIMITATION", "INSUFFICIENT_EVIDENCE"),
    ],
)
async def test_false_positive_language_candidates_never_reach_public_feedback(
    trait, essay, revision, kind, reason
):
    result, service, provider, events, _ = await assess(
        essay,
        [
            candidate(
                essay,
                aspect="precision" if trait == "lr" else "grammar",
                kind=kind,
                suggested_revision=revision,
                observation="Cần sửa cách diễn đạt này.",
            )
        ],
        {"decisions": [decision(reason=reason)]},
        trait,
    )
    assert result.score == Decimal("7.5") and not service.failures
    assert result.improvements == result.annotations == []
    assert "Cần sửa" not in result.feedback
    assert "Chưa xác định" in result.feedback
    assert len([s for _, s, _ in provider.requests if "decisions" in s["properties"]]) == 1
    assert not any(e == "criterion.feedback.annotation" for e, _ in events)
    assert next(p.result for e, p in events if e == "criterion.feedback.completed") == result


@pytest.mark.parametrize(
    "trait,essay,span,revision,aspect,message",
    [
        (
            "gra",
            REAL_ERROR,
            REAL_ERROR,
            "The percentage of students was 30%.",
            "grammar",
            "Động từ cần hòa hợp với chủ ngữ.",
        ),
        ("lr", "The goverment acts.", "goverment", "government", "spelling", "Lỗi chính tả."),
    ],
)
async def test_verified_genuine_language_errors_survive_with_exact_annotations(
    trait, essay, span, revision, aspect, message
):
    result, service, provider, events, req = await assess(
        essay,
        [candidate(span, suggested_revision=revision, aspect=aspect, observation=message)],
        {"decisions": [decision(accept=True, reason="CLEAR_LANGUAGE_ERROR")]},
        trait,
    )
    assert result.score == Decimal("7.5") and not service.failures
    assert result.improvements == [message] and len(result.annotations) == 1
    annotation = result.annotations[0]
    assert annotation.original_span == span and annotation.criterion == trait
    encoded = req.response.encode("utf-16-le")
    assert (
        encoded[annotation.start_offset * 2 : annotation.end_offset * 2].decode("utf-16-le") == span
    )
    stages = [next(iter(s["properties"])) for _, s, _ in provider.requests]
    assert stages == ["evidence", "score", "observations", "decisions"]
    assert all("score" not in s["properties"] for _, s, _ in provider.requests[2:])
    names = [e for e, _ in events]
    assert names.index("criterion.feedback.started") < names.index("criterion.feedback.annotation")
    assert names.index("criterion.feedback.annotation") < names.index(
        "criterion.feedback.completed"
    )
    messages, _, options = provider.requests[-1]
    payload = json.loads(messages[1]["content"])
    assert payload["essay"] == req.response and payload["criterion"] == trait
    assert payload["candidates"][0]["source_excerpt"] == essay
    assert payload["candidates"][0]["original_span"] == span
    assert payload["candidates"][0]["suggested_revision"] == revision
    assert "fixed_score" not in payload
    assert options.max_tokens <= 512


@pytest.mark.parametrize(
    "verification",
    [
        ProviderFailure("AI_PROVIDER_TIMEOUT"),
        TimeoutError(),
        RuntimeError("PRIVATE PROVIDER BODY"),
        Completion("not JSON"),
        Completion("{}"),
        {"decisions": []},
        {"decisions": [decision(accept=True, reason="VALID_STANDARD_ENGLISH")]},
        {"decisions": [decision(index=1, accept=True, reason="CLEAR_LANGUAGE_ERROR")]},
        {"decisions": [decision(), decision()]},
        {"decisions": [decision(accept=True, reason="MATERIAL_RECURRENT_LIMITATION")]},
        Completion(
            json.dumps({"decisions": [decision(accept=True, reason="CLEAR_LANGUAGE_ERROR")]}),
            finish_reason="length",
        ),
    ],
)
async def test_verifier_failure_fails_closed_and_keeps_score_and_safe_strength(
    verification, caplog
):
    strength = candidate(
        kind="STRENGTH",
        original_span=None,
        suggested_revision=None,
        observation="Thông tin được trình bày rõ ràng.",
    )
    result, service, provider, _, _ = await assess(
        REAL_ERROR, [candidate(), strength], verification
    )
    assert result.score == Decimal("7.5") and not service.failures
    assert result.feedback_status == "COMPLETED"
    assert result.improvements == result.annotations == []
    assert result.strengths == [strength["observation"]]
    assert any(
        d.reason == "LANGUAGE_FEEDBACK_VERIFICATION_UNAVAILABLE" for d in service.diagnostics
    )
    assert (
        "PRIVATE PROVIDER BODY"
        not in caplog.text + str(service.diagnostics) + result.model_dump_json()
    )
    assert len(provider.requests) == 4


async def test_verified_material_limitation_stays_in_panel_without_inline_decoration():
    item = candidate(
        kind="LIMITATION",
        suggested_revision=None,
        observation="Lỗi hòa hợp lặp lại làm giảm khả năng kiểm soát câu.",
    )
    result, _, _, _, _ = await assess(
        REAL_ERROR,
        [item],
        {"decisions": [decision(accept=True, reason="MATERIAL_RECURRENT_LIMITATION")]},
    )
    assert result.improvements == [item["observation"]]
    assert result.annotations == [] and result.score == Decimal("7.5")


@pytest.mark.parametrize(
    "items",
    [
        [],
        [
            candidate(
                kind="STRENGTH",
                original_span=None,
                suggested_revision=None,
                observation="Câu nêu thông tin rõ ràng.",
            )
        ],
        [
            candidate(
                kind="OPTIONAL_REFINEMENT", aspect="style", observation="Có thể diễn đạt gọn hơn."
            )
        ],
    ],
)
async def test_no_negative_candidates_skips_verifier_and_optional_rewrites(items):
    result, service, provider, _, _ = await assess(REAL_ERROR, items, RuntimeError("must not call"))
    assert result.score == Decimal("7.5") and not service.failures
    assert result.improvements == result.annotations == []
    assert not any("decisions" in s["properties"] for _, s, _ in provider.requests)
    assert "Có thể diễn đạt" not in result.feedback


async def test_verification_batches_candidates_with_original_draft_indexes_and_exact_source():
    essay = f"😀 Clear introduction.\r\n\r\n{REAL_ERROR}\r\nThe goverment acts."
    items = [
        candidate(
            kind="STRENGTH",
            original_span=None,
            suggested_revision=None,
            observation="Mở bài rõ ràng.",
        ),
        candidate(source_id="P2S1"),
        candidate(
            "The goverment acts.",
            source_id="P3S1",
            suggested_revision=None,
            kind="LIMITATION",
            observation="Cách dùng câu cần kiểm soát tốt hơn.",
        ),
    ]
    verification = {
        "decisions": [
            decision(index=1, accept=True, reason="CLEAR_LANGUAGE_ERROR"),
            decision(index=2, reason="CRITERION_MISMATCH"),
        ]
    }
    result, _, provider, _, req = await assess(essay, items, verification)
    assert len(result.annotations) == len(result.improvements) == 1
    payload = json.loads(provider.requests[-1][0][1]["content"])
    assert [c["observation_index"] for c in payload["candidates"]] == [1, 2]
    assert payload["essay"] == essay
    assert payload["candidates"][0]["source_excerpt"] == request_sources(req)[1].text
    encoded = essay.encode("utf-16-le")
    annotation = result.annotations[0]
    assert (
        encoded[annotation.start_offset * 2 : annotation.end_offset * 2].decode("utf-16-le")
        == REAL_ERROR
    )


@pytest.mark.parametrize("failure", [asyncio.CancelledError(), TraceFailure()])
async def test_explicit_cancellation_and_stop_are_not_swallowed(failure):
    with pytest.raises(type(failure)):
        await assess(REAL_ERROR, [candidate()], failure)


async def test_actual_verifier_timeout_omits_negative_feedback(monkeypatch):
    from app.services import task1_language_feedback

    complete = Provider.complete

    async def slow(self, messages, schema, *, options=None):
        if "decisions" in schema["properties"]:
            await asyncio.sleep(100)
        return await complete(self, messages, schema, options=options)

    monkeypatch.setattr(Provider, "complete", slow)
    monkeypatch.setattr(task1_language_feedback, "LANGUAGE_VERIFICATION_TIMEOUT_SECONDS", 0.01)
    result, service, _, _, _ = await assess(REAL_ERROR, [candidate()], {"decisions": []})
    assert result.score == Decimal("7.5") and not service.failures
    assert result.improvements == result.annotations == []
    assert service.diagnostics[-1].reason == "LANGUAGE_FEEDBACK_VERIFICATION_UNAVAILABLE"


@pytest.mark.parametrize("score", [0, 1, 6.5, 7, 7.5, 8, 8.5, 9])
@pytest.mark.parametrize("accepted", [False, True])
async def test_verified_or_rejected_feedback_never_adjusts_any_accepted_score(score, accepted):
    result, service, _, _, _ = await assess(
        REAL_ERROR,
        [candidate()],
        {
            "decisions": [
                decision(
                    accept=accepted,
                    reason="CLEAR_LANGUAGE_ERROR" if accepted else "INSUFFICIENT_EVIDENCE",
                )
            ]
        },
        score=score,
    )
    assert result.score == service.states["gra"].band_score.score == Decimal(str(score))


async def test_missing_one_batched_decision_rejects_all_unverified_negatives():
    items = [
        candidate(),
        candidate(
            kind="LIMITATION",
            suggested_revision=None,
            observation="Kiểm soát cấu trúc còn hạn chế.",
        ),
    ]
    result, service, _, _, _ = await assess(
        REAL_ERROR, items, {"decisions": [decision(accept=True, reason="CLEAR_LANGUAGE_ERROR")]}
    )
    assert result.improvements == result.annotations == [] and result.score == Decimal("7.5")
    assert service.diagnostics[-1].reason == "LANGUAGE_FEEDBACK_VERIFICATION_UNAVAILABLE"


async def test_historical_v11_keeps_its_score_first_contract_without_new_verification():
    from app.evaluation.task1.score_first_v11_prompts import ScoreFirstV11Task1WritingScoringService

    req = request().model_copy(update={"response": REAL_ERROR})
    provider = Provider([candidate()], RuntimeError("must not call"))
    service = ScoreFirstV11Task1WritingScoringService(provider)

    async def trace(_event, _payload):
        pass

    result = await service._task1_criterion(
        req,
        "gra",
        Task1Analysis(visual_family="chart_table", confidence="HIGH", reference=chart()),
        trace,
    )
    assert result.score == Decimal("7.5") and len(result.annotations) == 1
    assert len(provider.requests) == 3 and not service.diagnostics
    assert "7 is not a safe default" not in provider.requests[1][0][0]["content"]


def test_verifier_schema_is_strict_bounded_score_free_and_consistent():
    from app.schemas.task1_feedback import Task1LanguageFeedbackVerification

    schema = Task1LanguageFeedbackVerification.model_json_schema()
    assert set(schema["properties"]) == {"decisions"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["decisions"]["maxItems"] == 4
    for bad in [
        {"decisions": [decision()], "score": 8},
        {"decisions": [decision(index=True)]},
        {"decisions": [{**decision(), "accept": "false"}]},
        {"decisions": [decision(accept=True, reason="STYLE_ONLY")]},
        {"decisions": [decision(accept=False, reason="CLEAR_LANGUAGE_ERROR")]},
        {"decisions": [decision(reason="invented")]},
    ]:
        with pytest.raises(ValidationError):
            Task1LanguageFeedbackVerification.model_validate(bad)


def test_verifier_prompt_is_skeptical_and_requests_only_bounded_decisions():
    from app.domains.scoring.task1_prompts import language_verification_prompt
    from app.schemas.writing_ai import Task2FeedbackDraft

    req = request().model_copy(update={"response": REAL_ERROR})
    sources = {s.source_id: s for s in request_sources(req)}
    item = candidate()
    draft = Task2FeedbackDraft.model_validate(
        {"observations": [{k: v for k, v in item.items() if k not in {"aspect", "claim_id"}}]}
    )
    for trait in ("gra", "lr"):
        system = language_verification_prompt(req, trait, draft, sources)[0]["content"]
        for concept in [
            "Assume the original sentence is acceptable",
            "When uncertain, REJECT",
            "valid standard English",
            "stylistic preference",
            "acceptable synonym",
            "minimal correction",
            "material or recurring",
            "no hidden reasoning",
            "structured JSON",
            "not a scoring pass",
        ]:
            assert concept in system
        assert "JSON schema:" in system


def test_task1_optional_rendering_does_not_change_task2_semantics():
    from app.domains.scoring.task1_feedback import render_task1_feedback
    from app.domains.scoring.task2_feedback import render_task2_feedback
    from app.schemas.writing_ai import Task2FeedbackDraft

    req = request().model_copy(update={"response": REAL_ERROR})
    sources = {s.source_id: s for s in request_sources(req)}
    item = candidate(kind="OPTIONAL_REFINEMENT", observation="Có thể diễn đạt gọn hơn.")
    draft = Task2FeedbackDraft.model_validate(
        {"observations": [{k: v for k, v in item.items() if k not in {"aspect", "claim_id"}}]}
    )
    task1, evidence = render_task1_feedback(draft, sources)
    task2, _ = render_task2_feedback(draft, sources)
    assert task1.improvements == [] and "Có thể diễn đạt" not in task1.feedback
    assert evidence.evidence == []
    assert task2.improvements == ["Gợi ý tùy chọn: Có thể diễn đạt gọn hơn."]
