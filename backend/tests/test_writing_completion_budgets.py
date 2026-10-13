"""Stage-specific Writing completions and bounded repairs; no live inference."""

import json
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from test_task1_visual import Task1FakeProvider
from test_task1_visual import request as task1_request

from app.core.config import Settings
from app.domains.scoring.writing import WritingScoringRequest
from app.evaluation.task1.runner import CountedProvider
from app.providers.writing_llm import base, create_provider
from app.providers.writing_llm.base import Completion, ProviderFailure
from app.services.mts_writing import FEEDBACK_FALLBACK, MTSWritingScoringService
from app.services.task1_writing import Task1WritingScoringService

SCORE = {"score": 6.5}
FEEDBACK = {
    "feedback": "Bài viết rõ ý nhưng các ví dụ cần phát triển thêm.",
    "strengths": ["Lập trường rõ ràng."],
    "improvements": ["Phát triển ví dụ cụ thể."],
}
TASK2_FEEDBACK = {
    "observations": [
        {
            "source_id": "P1S1",
            "kind": "STRENGTH",
            "observation": "Câu này trình bày rõ lợi ích của công viên đối với đời sống đô thị.",
            "original_span": None,
            "suggested_revision": None,
            "confidence": "HIGH",
        }
    ]
}
EVIDENCE = {"evidence": [{"source_id": "P1S1", "assessment": "Dẫn chứng liên quan."}]}
RELEVANCE = {
    "verdict": "ON_TOPIC",
    "confidence": "HIGH",
    "source_ids": [],
    "reason": "Có liên hệ với đề bài.",
}
ESSAY = "Fictional parks improve city life. They support communities."
STAGE_BUDGETS = {"evidence": 1800, "score": 128, "feedback": 1200}
REPAIR_BUDGETS = {"evidence": 2056, "score": 256, "feedback": 1400}
STAGE_OUTPUTS = {"evidence": EVIDENCE, "score": SCORE, "feedback": TASK2_FEEDBACK}


def completion_stage(schema):
    properties = schema["properties"]
    return (
        "evidence" if "evidence" in properties else "score" if "score" in properties else "feedback"
    )


class BudgetProvider:
    def __init__(self, score=(), evidence=(), feedback=()):
        self.outputs = {
            "score": iter(score),
            "evidence": iter(evidence),
            "feedback": iter(feedback),
        }
        self.calls = []

    async def complete(self, messages, schema, *, options=None):
        if "verdict" in schema["properties"]:
            return Completion(json.dumps(RELEVANCE))
        self.calls.append((messages, schema, options))
        stage = completion_stage(schema)
        value = next(self.outputs[stage], None)
        if isinstance(value, ProviderFailure):
            raise value
        if isinstance(value, Completion):
            return value
        return Completion(json.dumps(STAGE_OUTPUTS[stage] if value is None else value))


async def assess(provider, service_type=MTSWritingScoringService, request=None):
    events = []

    async def trace(event, payload):
        events.append((event, payload))

    service = service_type(provider)
    result = await service.assess(
        request
        or WritingScoringRequest(
            attempt_id=uuid4(),
            writing_task_id=uuid4(),
            prompt="Discuss fictional parks.",
            response=ESSAY,
        ),
        trace,
    )
    return result, service, events


def budget(call):
    assert call[2] is not None, "Writing must pass a typed, stage-specific completion budget"
    return call[2].max_tokens


def stage_calls(provider, stage):
    return [call for call in provider.calls if completion_stage(call[1]) == stage]


def public_retry_stages(events):
    return [payload.stage for event, payload in events if event == "criterion.retrying"]


async def test_task2_success_runs_score_evidence_then_feedback_once_per_criterion():
    provider = BudgetProvider()
    result, service, events = await assess(provider)
    assert result.overall_band == Decimal("6.5") and result.raw_mean == Decimal("6.5")
    assert result.criteria.ta.evidence[0].quote == "Fictional parks improve city life."
    assert len(provider.calls) == 12
    assert [budget(call) for call in provider.calls] == [128, 1800, 1200] * 4
    assert all(len(stage_calls(provider, stage)) == 4 for stage in STAGE_BUDGETS)
    assert not service.diagnostics and not service.failures and not public_retry_stages(events)
    assert "reasoning" not in result.model_dump_json()
    scoring_events = [
        payload for event, payload in events if event.startswith("criterion.scoring.")
    ]
    assert len(scoring_events) == 8 and all(
        payload.stage == "scoring" for payload in scoring_events
    )


async def test_score_and_feedback_have_separate_schema_and_authoritative_prompt_context():
    provider = BudgetProvider()
    await assess(provider)
    for stage, expected in (("score", {"score"}), ("feedback", {"observations"})):
        for messages, schema, _options in stage_calls(provider, stage):
            assert set(schema["properties"]) == set(schema["required"]) == expected
            assert schema["additionalProperties"] is False
            prompt_schema = json.loads(messages[0]["content"].split("JSON schema: ", 1)[1])
            assert set(prompt_schema["properties"]) == expected
            payload = json.loads(messages[1]["content"])
            if stage == "feedback":
                assert payload["fixed_score"] == 6.5
                item_schema = schema["properties"]["observations"]["items"]
                assert set(item_schema["properties"]) == {
                    "source_id",
                    "kind",
                    "observation",
                    "original_span",
                    "suggested_revision",
                    "confidence",
                }
                assert item_schema["additionalProperties"] is False
            else:
                assert "evidence" not in payload and "fixed_score" not in payload
                assert (
                    payload["segmented_essay"]
                    == "[P1S1] Fictional parks improve city life.\n[P1S2] They support communities."
                )


def wire_schema(body, provider):
    if provider == "vllm":
        return body["response_format"]["json_schema"]["schema"]
    assert body["response_format"] == {"type": "json_object"}
    return json.loads(body["messages"][0]["content"].split("JSON schema: ", 1)[1])


def install_adapter(monkeypatch, handler, provider):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    return create_provider(
        Settings(
            _env_file=None,
            ai_writing_enabled=True,
            ai_writing_provider=provider,
            ai_writing_vllm_base_url="https://provider.example/v1",
            ai_writing_openai_base_url="https://provider.example/v1",
            ai_writing_openai_api_key="fictional-test-key",
        )
    )


@pytest.mark.parametrize(
    "provider,parameter", [("vllm", "max_tokens"), ("openai", "max_completion_tokens")]
)
async def test_truncated_completion_retains_safe_token_usage_and_stage_diagnostics(
    monkeypatch, caplog, provider, parameter
):
    truncated = False

    def handler(request):
        nonlocal truncated
        body = json.loads(request.content)
        stage = (
            "relevance" if body[parameter] == 768 else completion_stage(wire_schema(body, provider))
        )
        finish = "stop"
        if stage == "score" and not truncated:
            truncated = True
            finish = "length"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": finish,
                        "message": {
                            "content": json.dumps(
                                RELEVANCE if stage == "relevance" else STAGE_OUTPUTS[stage]
                            )
                        },
                    }
                ],
                "usage": {
                    "completion_tokens": 128 if finish == "length" else 10,
                    "private": "private usage",
                    "total_tokens": -1,
                },
            },
        )

    result, service, _ = await assess(install_adapter(monkeypatch, handler, provider))
    assert result is not None
    assert {"completion_tokens": 128} in service.usage
    attempt = service.latency.summary()["stages"]["ta.score"]["attempts"][0]
    assert attempt["finish_reason"] == "length" and attempt["completion_tokens"] == 128
    assert "private usage" not in str(service.usage) + str(service.diagnostics) + caplog.text


@pytest.mark.parametrize(
    "provider,parameter", [("vllm", "max_tokens"), ("openai", "max_completion_tokens")]
)
@pytest.mark.parametrize("finish", ["abort", "error"])
async def test_provider_failure_finish_wins_over_malformed_usage(
    monkeypatch, provider, parameter, finish
):
    def handler(request):
        body = json.loads(request.content)
        stage = (
            "relevance" if body[parameter] == 768 else completion_stage(wire_schema(body, provider))
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": finish if stage == "feedback" else "stop",
                        "message": {
                            "content": json.dumps(
                                RELEVANCE if stage == "relevance" else STAGE_OUTPUTS[stage]
                            )
                        },
                    }
                ],
                "usage": "malformed" if stage == "feedback" else {},
            },
        )

    result, service, _ = await assess(install_adapter(monkeypatch, handler, provider))
    assert result is None and set(service.failures) == {"ta", "cc", "lr", "gra"}
    assert all(d.reason == f"PROVIDER_FINISH_{finish.upper()}" for d in service.diagnostics)


@pytest.mark.parametrize(
    "provider,parameter", [("vllm", "max_tokens"), ("openai", "max_completion_tokens")]
)
async def test_production_wire_contract_has_tiny_score_and_separate_feedback(
    monkeypatch, provider, parameter
):
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if body[parameter] == 768:
            output = RELEVANCE
        else:
            schema = wire_schema(body, provider)
            stage = completion_stage(schema)
            output = STAGE_OUTPUTS[stage]
            expected = {stage} if stage in {"evidence", "score"} else {"observations"}
            assert set(schema["properties"]) == set(schema["required"]) == expected
            assert schema["additionalProperties"] is False
            assert body[parameter] == STAGE_BUDGETS[stage]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(output),
                            "reasoning_content": "private ignored reasoning",
                        },
                    }
                ]
            },
        )

    result, service, _events = await assess(install_adapter(monkeypatch, handler, provider))
    assert result.overall_band == Decimal("6.5") and not service.diagnostics
    assert [body[parameter] for body in bodies] == [768] + [128, 1800, 1200] * 4
    assert "private ignored reasoning" not in result.model_dump_json()
    other = "max_completion_tokens" if parameter == "max_tokens" else "max_tokens"
    assert all(
        other not in body
        and not ({"reasoning", "reasoning_effort", "reasoning_content"} & body.keys())
        for body in bodies
    )


@pytest.mark.parametrize("stage", ["evidence", "score", "feedback"])
@pytest.mark.parametrize("adapter_raises", [False, True])
async def test_length_repair_uses_only_its_stage_headroom_and_correction(stage, adapter_raises):
    rejected = {"score": 9} if stage == "score" else STAGE_OUTPUTS[stage]
    first = (
        ProviderFailure(
            "AI_PROVIDER_BAD_RESPONSE", reason="PROVIDER_FINISH_LENGTH", finish_reason="length"
        )
        if adapter_raises
        else Completion(json.dumps(rejected), finish_reason="length")
    )
    provider = BudgetProvider(**{stage: [first]})
    result, service, events = await assess(provider)
    assert result.criteria.ta.score == Decimal("6.5")
    calls = stage_calls(provider, stage)
    assert len(provider.calls) == 13 and len(calls) == 5
    assert [budget(call) for call in calls] == [
        STAGE_BUDGETS[stage],
        REPAIR_BUDGETS[stage],
        *([STAGE_BUDGETS[stage]] * 3),
    ]
    assert "Correction (PROVIDER_FINISH_LENGTH)" in calls[1][0][-1]["content"]
    assert calls[1][0][:-1] == calls[0][0]
    assert (service.diagnostics[0].stage, service.diagnostics[0].reason) == (
        stage,
        "PROVIDER_FINISH_LENGTH",
    )
    assert public_retry_stages(events) == ["scoring" if stage == "score" else stage]
    for other in STAGE_BUDGETS.keys() - {stage}:
        assert [budget(call) for call in stage_calls(provider, other)] == [STAGE_BUDGETS[other]] * 4


@pytest.mark.parametrize(
    "provider,parameter", [("vllm", "max_tokens"), ("openai", "max_completion_tokens")]
)
@pytest.mark.parametrize("stage", ["evidence", "score", "feedback"])
async def test_adapters_send_stage_specific_length_repair_budget(
    monkeypatch, provider, parameter, stage
):
    bodies, stage_bodies = [], []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if body[parameter] == 768:
            output, finish = RELEVANCE, "stop"
        else:
            schema = wire_schema(body, provider)
            actual_stage = completion_stage(schema)
            output = STAGE_OUTPUTS[actual_stage]
            if actual_stage == stage:
                stage_bodies.append(body)
            finish = "length" if actual_stage == stage and len(stage_bodies) == 1 else "stop"
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": finish, "message": {"content": json.dumps(output)}}]
            },
        )

    result, service, events = await assess(install_adapter(monkeypatch, handler, provider))
    assert result is not None and result.criteria.ta.score == Decimal("6.5")
    assert len(bodies) == 14 and len(stage_bodies) == 5
    assert [body[parameter] for body in stage_bodies] == [
        STAGE_BUDGETS[stage],
        REPAIR_BUDGETS[stage],
        *([STAGE_BUDGETS[stage]] * 3),
    ]
    assert service.diagnostics[0].stage == stage and len(public_retry_stages(events)) == 1


@pytest.mark.parametrize(
    "output,reason",
    [
        ({"score": 6.3}, "INVALID_HALF_BAND"),
        ({**SCORE, "feedback": "Must not be part of score."}, "SCORE_SCHEMA_INVALID"),
    ],
)
async def test_non_length_score_repair_keeps_tiny_budget(output, reason):
    provider = BudgetProvider(score=[output])
    result, service, events = await assess(provider)
    assert result.criteria.ta.score == Decimal("6.5")
    calls = stage_calls(provider, "score")
    assert [budget(call) for call in calls] == [128] * 5
    assert len(provider.calls) == 13 and reason in calls[1][0][-1]["content"]
    assert (service.diagnostics[0].stage, service.diagnostics[0].reason) == ("score", reason)
    assert public_retry_stages(events) == ["scoring"]


async def test_unknown_auxiliary_source_is_dropped_without_evidence_repair():
    provider = BudgetProvider(
        evidence=[{"evidence": [{"source_id": "P99S1", "assessment": "Dẫn chứng."}]}]
    )
    result, service, _events = await assess(provider)
    assert result.criteria.ta.score == Decimal("6.5")
    assert [budget(call) for call in provider.calls[:3]] == [128, 1800, 1200]
    assert len(provider.calls) == 12 and service.diagnostics[0].reason == "EVIDENCE_ITEM_DROPPED"


@pytest.mark.parametrize(
    "invalid,reason",
    [
        (Completion('{"score":9}', finish_reason="length"), "PROVIDER_FINISH_LENGTH"),
        ({"score": 6.3}, "INVALID_HALF_BAND"),
    ],
)
async def test_second_score_failure_stops_after_two_inferences_and_continues_other_traits(
    invalid, reason
):
    provider = BudgetProvider(score=[invalid] * 2)
    result, service, events = await assess(provider)
    assert result is None and set(service.failures) == {"ta"}
    assert service.failures["ta"].stage == "scoring"
    assert len(provider.calls) == 11 and len(stage_calls(provider, "feedback")) == 3
    assert len(stage_calls(provider, "evidence")) == 3
    assert [budget(call) for call in stage_calls(provider, "score")] == [
        128,
        256 if reason == "PROVIDER_FINISH_LENGTH" else 128,
        128,
        128,
        128,
    ]
    assert [(d.stage, d.reason, d.attempt) for d in service.diagnostics] == [
        ("score", reason, 1),
        ("score", reason, 2),
    ]
    assert public_retry_stages(events) == ["scoring"]
    assert [payload.criterion for event, payload in events if event == "criterion.completed"] == [
        "cc",
        "lr",
        "gra",
    ]


@pytest.mark.parametrize(
    "invalid,reason",
    [
        (Completion(json.dumps(TASK2_FEEDBACK), finish_reason="length"), "PROVIDER_FINISH_LENGTH"),
        ({**FEEDBACK, "score": 9}, "FEEDBACK_SCHEMA_INVALID"),
        ({**FEEDBACK, "feedback": "Bài viết phù hợp Band 9."}, "FEEDBACK_SCHEMA_INVALID"),
    ],
)
async def test_second_recoverable_feedback_failure_keeps_score_with_visible_fallback(
    invalid, reason
):
    provider = BudgetProvider(feedback=[invalid] * 2)
    result, service, events = await assess(provider)
    assert result is not None and not service.failures
    assert result.criteria.ta.score == Decimal("6.5") and result.overall_band == Decimal("6.5")
    assert result.criteria.ta.feedback == FEEDBACK_FALLBACK
    assert result.criteria.ta.strengths == result.criteria.ta.improvements == []
    assert len(provider.calls) == 13 and len(stage_calls(provider, "score")) == 4
    assert [budget(call) for call in stage_calls(provider, "feedback")] == [
        1200,
        1400 if reason == "PROVIDER_FINISH_LENGTH" else 1200,
        1200,
        1200,
        1200,
    ]
    assert [(d.stage, d.reason, d.attempt) for d in service.diagnostics] == [
        ("feedback", reason, 1),
        ("feedback", reason, 2),
        ("feedback", "FEEDBACK_FALLBACK_USED", 2),
    ]
    assert public_retry_stages(events) == ["feedback"]
    assert {payload.criterion for event, payload in events if event == "criterion.completed"} == {
        "ta",
        "cc",
        "lr",
        "gra",
    }


async def test_feedback_transport_failure_remains_failure_without_fallback_or_repair():
    provider = BudgetProvider(feedback=[ProviderFailure("AI_PROVIDER_TIMEOUT")])
    result, service, events = await assess(provider)
    assert result is None and set(service.failures) == {"ta"}
    assert service.failures["ta"].stage == "feedback"
    assert service.failures["ta"].error_code == "AI_PROVIDER_TIMEOUT"
    assert len(provider.calls) == 12 and not service.diagnostics and not public_retry_stages(events)


class Task1BudgetProvider(Task1FakeProvider):
    def __init__(self, ta_length_failures=1):
        super().__init__()
        self.budget_calls = []
        self.ta_calls = 0
        self.ta_length_failures = ta_length_failures

    async def complete(self, messages, schema, *, options=None):
        self.budget_calls.append((messages, schema, options))
        completion = await super().complete(messages, schema, options=options)
        if (
            "score" in schema["properties"]
            and "Criterion: Task Achievement." in messages[0]["content"]
        ):
            self.ta_calls += 1
            if self.ta_calls <= self.ta_length_failures:
                return Completion(json.dumps({"score": 9}), finish_reason="length")
        return completion


@pytest.mark.parametrize("contract", ["v3", "v5", "v8"])
async def test_frozen_benchmark_evidence_length_repair_keeps_historical_budget(contract):
    from app.evaluation.task1.baseline_v5_prompts import BaselineV5Task1WritingScoringService
    from app.evaluation.task1.legacy_prompts import LegacyTask1WritingScoringService
    from app.evaluation.task1.pre_score_first import PreScoreFirstTask1WritingScoringService

    service_type = {
        "v3": LegacyTask1WritingScoringService,
        "v5": BaselineV5Task1WritingScoringService,
        "v8": PreScoreFirstTask1WritingScoringService,
    }[contract]

    class Provider(Task1BudgetProvider):
        async def complete(self, messages, schema, *, options=None):
            completion = await super().complete(messages, schema, options=options)
            if "evidence" in schema["properties"] and len(task1_stage_calls(self, "evidence")) == 1:
                return Completion(completion.text, finish_reason="length")
            return completion

    provider = Provider(ta_length_failures=0)
    result, service, _ = await assess(provider, service_type, task1_request())
    assert result is not None and not service.failures
    assert [budget(call) for call in task1_stage_calls(provider, "evidence")] == [
        1800,
        2824,
        1800,
        1800,
        1800,
    ]
    assert all("score" in call[1]["properties"] for call in task1_stage_calls(provider, "feedback"))


def task1_stage_calls(provider, stage):
    return [
        call
        for call in provider.budget_calls
        if stage in call[1]["properties"]
        or (stage == "feedback" and "observations" in call[1]["properties"])
    ]


async def test_task1_all_traits_use_same_tiny_score_cap_and_separate_feedback():
    provider = Task1BudgetProvider(ta_length_failures=0)
    result, service, events = await assess(provider, Task1WritingScoringService, task1_request())
    assert result is not None and provider.ta_calls == 1
    assert len(provider.budget_calls) == 15
    for stage in STAGE_BUDGETS:
        calls = task1_stage_calls(provider, stage)
        assert len(calls) == 4 and all(budget(call) == STAGE_BUDGETS[stage] for call in calls)
        if stage in {"score", "feedback"}:
            expected = {"score"} if stage == "score" else {"observations"}
            assert all(set(call[1]["properties"]) == expected for call in calls)
    criterion_stages = {}
    for messages, schema, _options in provider.budget_calls:
        if {"evidence", "score", "feedback", "observations"} & schema["properties"].keys():
            name = messages[0]["content"].split("Criterion: ", 1)[1].split(".", 1)[0]
            criterion_stages.setdefault(name, []).append(completion_stage(schema))
    assert len(criterion_stages) == 4
    assert all(stages == ["evidence", "score", "feedback"] for stages in criterion_stages.values())
    assert not service.diagnostics and not public_retry_stages(events)


async def test_task1_counted_provider_forwards_split_budgets_and_keeps_perception():
    provider = Task1BudgetProvider()
    counted = CountedProvider(provider)
    result, service, events = await assess(counted, Task1WritingScoringService, task1_request())
    assert result is not None and result.criteria.ta.score == Decimal(7)
    assert result.task1_analysis.claims[0].verdict == "SUPPORTED"
    assert provider.ta_calls == 2 and counted.calls == 16
    assert counted.usage["total_tokens"] == 150
    assert all(
        options is None
        for _messages, schema, options in provider.budget_calls
        if {"reference", "claims", "items"} & schema["properties"].keys()
    )
    scores = task1_stage_calls(provider, "score")
    ta_scores = [call for call in scores if "Criterion: Task Achievement." in call[0][0]["content"]]
    assert [budget(call) for call in ta_scores] == [128, 256]
    assert all(budget(call) == 128 for call in scores if call not in ta_scores)
    assert all(budget(call) == 1200 for call in task1_stage_calls(provider, "feedback"))
    assert (service.diagnostics[0].stage, service.diagnostics[0].reason) == (
        "score",
        "PROVIDER_FINISH_LENGTH",
    )
    assert public_retry_stages(events) == ["scoring"]


async def test_task1_second_ta_score_length_failure_has_no_third_inference_or_feedback():
    provider = Task1BudgetProvider(ta_length_failures=2)
    result, service, events = await assess(provider, Task1WritingScoringService, task1_request())
    assert result is None and set(service.failures) == {"ta"}
    assert service.failures["ta"].stage == "scoring"
    assert provider.ta_calls == 2 and len(provider.budget_calls) == 15
    ta_scores = [
        call
        for call in task1_stage_calls(provider, "score")
        if "Criterion: Task Achievement." in call[0][0]["content"]
    ]
    assert [budget(call) for call in ta_scores] == [128, 256]
    assert "Correction (PROVIDER_FINISH_LENGTH)" in ta_scores[1][0][-1]["content"]
    assert len(task1_stage_calls(provider, "feedback")) == 3
    assert [(d.stage, d.reason, d.attempt, d.finish_reason) for d in service.diagnostics] == [
        ("score", "PROVIDER_FINISH_LENGTH", 1, "length"),
        ("score", "PROVIDER_FINISH_LENGTH", 2, "length"),
    ]
    assert public_retry_stages(events) == ["scoring"]
    assert {payload.criterion for event, payload in events if event == "criterion.completed"} == {
        "cc",
        "lr",
        "gra",
    }


@pytest.mark.parametrize(
    "provider,parameter,default",
    [("vllm", "max_tokens", 1800), ("openai", "max_completion_tokens", 4096)],
)
@pytest.mark.parametrize("requested", [None, 128, 256, 1200, 1400, 1800, 2056])
async def test_provider_adapters_map_typed_stage_budgets_and_preserve_defaults(
    monkeypatch, provider, parameter, default, requested
):
    assert hasattr(base, "CompletionOptions")
    options = base.CompletionOptions(max_tokens=requested)
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        )

    adapter = install_adapter(monkeypatch, handler, provider)
    await adapter.complete([], {}, options=options)
    await adapter.complete([], {})
    assert bodies[0][parameter] == (default if requested is None else requested)
    assert bodies[1][parameter] == default
    other = "max_completion_tokens" if parameter == "max_tokens" else "max_tokens"
    assert all(other not in body and "reasoning" not in json.dumps(body) for body in bodies)
