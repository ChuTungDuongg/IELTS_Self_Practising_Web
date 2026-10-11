"""Score reliability through real orchestration and scripted provider failures."""

import asyncio
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from test_task1_visual import Task1FakeProvider
from test_task1_visual import request as task1_request

from app.domains.scoring.mts_prompts import TRAIT_NAMES, effective_prompt_version
from app.domains.scoring.writing import WritingScoringRequest
from app.providers.writing_llm.base import Completion, ProviderFailure
from app.schemas.writing_ai import TRAITS, AIWritingResult
from app.services.mts_writing import MTSWritingScoringService
from app.services.task1_input import (
    TASK1_PROMPT_VERSION,
    TASK1_SCORING_PROMPT_VERSION,
    TASK1_VISUAL_CONTRACT_VERSION,
)
from app.services.task1_writing import Task1WritingScoringService
from app.services.writing_ai import input_fingerprint
from app.services.writing_execution import TraceFailure

FEEDBACK = {"feedback": "Nội dung rõ ràng ở tiêu chí này.", "strengths": [], "improvements": []}
LENGTH = Completion('{"score":7,"feedback":"' + "verbose " * 100, finish_reason="length")


class Provider(Task1FakeProvider):
    def __init__(self, *, failed_trait="ta", feedback=LENGTH, score=7, relevance=False):
        super().__init__()
        self.failed_trait, self.feedback, self.score = failed_trait, feedback, score
        self.relevance = relevance
        self.requests = []

    async def complete(self, messages, schema, *, options=None):
        properties = schema["properties"]
        self.requests.append((messages, schema, options))
        if "verdict" in properties and self.relevance:
            return Completion(
                json.dumps(
                    {
                        "verdict": "WHOLLY_UNRELATED",
                        "confidence": "HIGH",
                        "source_ids": ["P1S1"],
                        "reason": "Bài viết nói về chủ đề khác.",
                    }
                )
            )
        if not {"score", "feedback"} & properties.keys():
            return await super().complete(messages, schema, options=options)
        trait = next(
            t
            for t in TRAITS
            if (
                f"Criterion: {'Task Achievement' if t == 'ta' else TRAIT_NAMES[t]}."
                in messages[0]["content"]
                or f"Criterion: {TRAIT_NAMES[t]}." in messages[0]["content"]
            )
        )
        # Reproduce the current combined contract: the score is available but
        # its verbose explanation prevents the completion from finishing.
        if "feedback" in properties and trait == self.failed_trait:
            value = self.feedback
        elif "score" in properties:
            value = (
                {"score": self.score}
                if properties.keys() == {"score"}
                else {
                    "score": self.score,
                    **FEEDBACK,
                }
            )
        else:
            value = FEEDBACK
        if isinstance(value, BaseException):
            raise value
        return value if isinstance(value, Completion) else Completion(json.dumps(value))


async def grade(provider, task=2, trace=None):
    events = []

    async def record(event, payload):
        events.append((event, payload))
        if trace:
            await trace(event, payload)

    request = (
        task1_request()
        if task == 1
        else WritingScoringRequest(
            attempt_id=uuid4(),
            writing_task_id=uuid4(),
            prompt="Discuss fictional city parks.",
            response="Parks help communities. Costs matter.",
        )
    )
    service = (Task1WritingScoringService if task == 1 else MTSWritingScoringService)(provider)
    return await service.assess(request, record), service, events, request


@pytest.mark.parametrize("task", [1, 2])
@pytest.mark.parametrize("failed_trait", TRAITS)
async def test_valid_score_survives_two_feedback_length_failures(task, failed_trait, caplog):
    provider = Provider(failed_trait=failed_trait)
    result, service, events, request = await grade(provider, task)
    assert result is not None, "Verbose feedback must never discard the independently valid band"
    assert not service.failures
    assert all(getattr(result.criteria, t).score == 7 for t in TRAITS)
    criterion = getattr(result.criteria, failed_trait)
    assert "chưa khả dụng" in criterion.feedback and "tham khảo" in criterion.feedback
    assert criterion.strengths == criterion.improvements == []
    assert criterion.evidence[0].source_id == "P1S1"
    assert criterion.evidence[0].quote == request.response.split(".")[0] + "."
    assert {p.criterion for e, p in events if e == "criterion.completed"} == set(TRAITS)
    assert not any(e == "criterion.failed" for e, _ in events)
    assert [(d.stage, d.reason, d.attempt) for d in service.diagnostics] == [
        ("feedback", "PROVIDER_FINISH_LENGTH", 1),
        ("feedback", "PROVIDER_FINISH_LENGTH", 2),
        ("feedback", "FEEDBACK_FALLBACK_USED", 2),
    ]
    assert LENGTH.text not in caplog.text + str(service.diagnostics)
    if task == 1:
        assert result.task1_analysis.reference is not None
        assert result.task1_analysis.claims[0].verdict == "SUPPORTED"
        ta = next(
            m
            for m, s, _ in provider.requests
            if s["properties"].keys() == {"score"}
            and "Criterion: Task Achievement." in m[0]["content"]
        )
        payload = json.loads(ta[1]["content"])
        assert payload["visual_reference"] and payload["derived_facts"]
        assert payload["claim_verification"][0]["verdict"] == "SUPPORTED"
        assert "Task 2" not in ta[0]["content"]


@pytest.mark.parametrize(
    "feedback",
    [
        Completion("invalid JSON"),
        Completion(""),
        {"feedback": "   ", "strengths": [], "improvements": []},
        {**FEEDBACK, "strengths": [42]},
        {**FEEDBACK, "score": 6},
        {**FEEDBACK, "feedback": "Bài viết phù hợp Band 6."},
        {**FEEDBACK, "feedback": "Bài viết phù hợp Band: 6."},
    ],
)
async def test_invalid_feedback_cannot_override_fixed_band(feedback):
    result, service, _, _ = await grade(Provider(feedback=feedback))
    assert result.criteria.ta.score == 7 and not service.failures
    assert result.criteria.ta.strengths == result.criteria.ta.improvements == []
    assert any(d.reason == "FEEDBACK_FALLBACK_USED" for d in service.diagnostics)


async def test_feedback_repair_recovers_without_rescoring():
    class RepairProvider(Provider):
        async def complete(self, messages, schema, *, options=None):
            if "feedback" in schema["properties"] and len(messages) == 3:
                self.requests.append((messages, schema, options))
                return Completion(json.dumps(FEEDBACK))
            return await super().complete(messages, schema, options=options)

    provider = RepairProvider(feedback=Completion("broken JSON"))
    result, service, _, _ = await grade(provider)
    assert result.criteria.ta.score == 7 and result.criteria.ta.feedback == FEEDBACK["feedback"]
    assert not service.failures
    assert len([s for _, s, _ in provider.requests if "score" in s["properties"]]) == 4
    assert [(d.stage, d.reason) for d in service.diagnostics] == [("feedback", "INVALID_JSON")]


@pytest.mark.parametrize("score", [6.5, 7, 8.5, 9, 0, 1])
async def test_score_schema_and_tiny_budget_preserve_valid_half_bands(score):
    provider = Provider(failed_trait=None, score=score)
    result, service, _, _ = await grade(provider)
    assert result.criteria.ta.score == Decimal(str(score)) and not service.diagnostics
    scores = [(m, s, o) for m, s, o in provider.requests if "score" in s["properties"]]
    feedbacks = [(m, s, o) for m, s, o in provider.requests if "feedback" in s["properties"]]
    assert len(scores) == len(feedbacks) == 4
    for messages, schema, options in scores:
        assert set(schema["properties"]) == set(schema["required"]) == {"score"}
        assert schema["additionalProperties"] is False
        assert 128 <= options.max_tokens <= 256
        assert json.loads(messages[0]["content"].split("JSON schema: ")[1])["required"] == ["score"]
    for messages, schema, options in feedbacks:
        assert set(schema["properties"]) == {"feedback", "strengths", "improvements"}
        assert schema["additionalProperties"] is False
        assert 800 <= options.max_tokens <= 1400
        assert json.loads(messages[1]["content"])["fixed_score"] == score
    assert AIWritingResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("score", [6.3, -0.5, 9.5])
async def test_invalid_score_fails_after_only_one_tiny_score_repair(score):
    provider = Provider(score=score)
    result, service, _, _ = await grade(provider)
    assert result is None and set(service.failures) == set(TRAITS)
    calls = [(m, s, o) for m, s, o in provider.requests if "score" in s["properties"]]
    assert len(calls) == 8 and all(o.max_tokens <= 256 for _, _, o in calls)
    assert all(set(s["properties"]) == {"score"} for _, s, _ in calls)
    assert not any("feedback" in s["properties"] for _, s, _ in provider.requests)
    assert all(state.result is None for state in service.states.values())
    assert all(d.reason == "INVALID_HALF_BAND" for d in service.diagnostics)


@pytest.mark.parametrize("bad", [{"score": 7, "feedback": "extra prose"}, {}])
async def test_score_schema_error_repair_remains_score_only(bad):
    class RepairProvider(Provider):
        async def complete(self, messages, schema, *, options=None):
            if "score" in schema["properties"] and len(messages) == 2:
                self.requests.append((messages, schema, options))
                return Completion(json.dumps(bad))
            return await super().complete(messages, schema, options=options)

    provider = RepairProvider(failed_trait=None)
    result, service, _, _ = await grade(provider)
    assert result is not None and not service.failures
    repairs = [
        m[-1]["content"]
        for m, s, _ in provider.requests
        if "score" in s["properties"] and len(m) == 3
    ]
    assert len(repairs) == 4
    assert all("Return ONLY one field: score" in m for m in repairs)
    assert not any("bounded Vietnamese feedback" in m for m in repairs)


@pytest.mark.parametrize(
    "failure",
    [
        ProviderFailure("AI_PROVIDER_AUTH_FAILED"),
        ProviderFailure("AI_PROVIDER_UNREACHABLE"),
        ProviderFailure("AI_PROVIDER_TIMEOUT"),
        RuntimeError("corrupt state"),
        ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="PROVIDER_FINISH_ABORT"),
    ],
)
async def test_hard_feedback_failures_are_not_treated_as_valid_completion(failure):
    result, service, _, _ = await grade(Provider(feedback=failure))
    assert result is None and set(service.failures) == {"ta"}
    assert not any(d.reason == "FEEDBACK_FALLBACK_USED" for d in service.diagnostics)


async def test_feedback_cancellation_and_explicit_stop_propagate():
    with pytest.raises(asyncio.CancelledError):
        await grade(Provider(feedback=asyncio.CancelledError()))

    async def stop(event, payload):
        if event == "criterion.retrying":
            raise TraceFailure

    with pytest.raises(TraceFailure):
        await grade(Provider(), trace=stop)


async def test_unrelated_band_one_still_skips_all_ta_calls():
    provider = Provider(relevance=True)
    result, service, _, _ = await grade(provider)
    assert result.criteria.ta.score == 1 and result.relevance.short_circuit_applied
    assert not service.failures
    for messages, schema, _ in provider.requests:
        if {"evidence", "score", "feedback"} & schema["properties"].keys():
            assert "Criterion: Task Response." not in messages[0]["content"]
    assert all(getattr(result.criteria, t).score == 7 for t in ("cc", "lr", "gra"))


async def test_versions_invalidate_old_cache_and_prompt_content_is_stable():
    assert effective_prompt_version("mts-task2-v8") == "mts-task2-v9"
    assert effective_prompt_version("custom") == "mts-task2-v9:custom"
    assert TASK1_PROMPT_VERSION == "mts-task1-visual-v9"
    assert TASK1_SCORING_PROMPT_VERSION == "mts-task1-scoring-v9"
    assert TASK1_VISUAL_CONTRACT_VERSION == "mts-task1-visual-v3"
    providers = [Provider(failed_trait=None), Provider(failed_trait=None)]
    runs = [await grade(p) for p in providers]
    for task, version, old in [
        (2, effective_prompt_version("mts-task2-v8"), "mts-task2-v8"),
        (1, TASK1_PROMPT_VERSION, "mts-task1-visual-v8"),
    ]:
        request = task1_request() if task == 1 else runs[0][3]
        assert input_fingerprint(request, version, "vllm", "model") != input_fingerprint(
            request, old, "vllm", "model"
        )
    assert providers[0].requests == providers[1].requests
