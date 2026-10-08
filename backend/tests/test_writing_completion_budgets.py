"""Bounded per-stage completions and one deliberate truncation repair; no inference."""

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
from app.services.mts_writing import MTSWritingScoringService
from app.services.task1_writing import Task1WritingScoringService

CORE = {
    "score": 6.5,
    "feedback": "Bài viết rõ ý nhưng các ví dụ cần phát triển thêm.",
    "strengths": ["Lập trường rõ ràng."],
    "improvements": ["Phát triển ví dụ cụ thể."],
}
EVIDENCE = {"evidence": [{"source_id": "P1S1", "assessment": "Dẫn chứng liên quan."}]}
ESSAY = "Fictional parks improve city life. They support communities."


class BudgetProvider:
    def __init__(self, scoring=(), evidence=()):
        self.scoring, self.evidence = iter(scoring), iter(evidence)
        self.calls = []

    async def complete(self, messages, schema, *, options=None):
        self.calls.append((messages, schema, options))
        is_evidence = "evidence" in schema["properties"]
        value = next(self.evidence if is_evidence else self.scoring, None)
        if isinstance(value, ProviderFailure):
            raise value
        if isinstance(value, Completion):
            return value
        return Completion(json.dumps(value or (EVIDENCE if is_evidence else CORE)))


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
    assert call[2] is not None, "MTS must pass a typed, stage-specific completion budget"
    return call[2].max_tokens


def scoring_calls(provider):
    return [call for call in provider.calls if "score" in call[1]["properties"]]


async def test_task2_success_uses_smaller_evidence_budget_and_one_inference_per_score():
    provider = BudgetProvider()
    result, service, events = await assess(provider)

    assert result.overall_band == Decimal("6.5") and result.raw_mean == Decimal("6.5")
    assert result.criteria.ta.evidence[0].quote == "Fictional parks improve city life."
    assert len(provider.calls) == 8 and len(scoring_calls(provider)) == 4
    assert [budget(call) for call in provider.calls] == [1800, 3072] * 4
    assert not service.diagnostics and not service.failures
    assert not any(event == "criterion.retrying" for event, _ in events)
    assert "reasoning" not in result.model_dump_json()


async def test_actual_scoring_contract_has_four_fields_in_schema_and_prompt():
    provider = BudgetProvider()
    await assess(provider)
    expected = {"score", "feedback", "strengths", "improvements"}
    for messages, schema, _options in scoring_calls(provider):
        assert set(schema["properties"]) == set(schema["required"]) == expected
        assert schema["additionalProperties"] is False
        prompt_schema = json.loads(messages[0]["content"].split("JSON schema: ", 1)[1])
        assert set(prompt_schema["properties"]) == expected


async def test_mts_vllm_wire_schema_has_only_four_fields_and_stage_budgets(monkeypatch):
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        schema = body["response_format"]["json_schema"]["schema"]
        is_evidence = "evidence" in schema["properties"]
        if not is_evidence:
            assert (
                set(schema["properties"])
                == set(schema["required"])
                == {"score", "feedback", "strengths", "improvements"}
            )
            assert schema["additionalProperties"] is False
            assert schema["properties"]["strengths"]["maxItems"] == 3
            assert schema["properties"]["improvements"]["maxItems"] == 3
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(EVIDENCE if is_evidence else CORE),
                            "reasoning_content": "private ignored reasoning",
                        },
                    }
                ],
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_vllm_base_url="https://provider.example/v1",
    )
    result, service, _events = await assess(create_provider(settings))
    assert result.overall_band == Decimal("6.5") and not service.diagnostics
    assert [body["max_tokens"] for body in bodies] == [1800, 3072] * 4
    assert "private ignored reasoning" not in result.model_dump_json()


@pytest.mark.parametrize("adapter_raises", [False, True])
async def test_scoring_length_repair_gets_larger_bounded_budget_and_correction(adapter_raises):
    first = (
        ProviderFailure(
            "AI_PROVIDER_BAD_RESPONSE", reason="PROVIDER_FINISH_LENGTH", finish_reason="length"
        )
        if adapter_raises
        # Complete JSON with length is still rejected, never accepted as score 9.
        else Completion(json.dumps({**CORE, "score": 9}), finish_reason="length")
    )
    provider = BudgetProvider(scoring=[first])
    result, service, events = await assess(provider)

    assert result.criteria.ta.score == Decimal("6.5")
    scores = scoring_calls(provider)
    assert len(provider.calls) == 9 and len(scores) == 5
    assert [budget(call) for call in scores] == [3072, 4096, 3072, 3072, 3072]
    assert "Correction (PROVIDER_FINISH_LENGTH)" in scores[1][0][-1]["content"]
    assert len(scores[1][0]) == len(scores[0][0]) + 1
    assert service.diagnostics[0].reason == "PROVIDER_FINISH_LENGTH"
    assert sum(event == "criterion.retrying" for event, _ in events) == 1


@pytest.mark.parametrize(
    "output,reason",
    [
        ({**CORE, "score": 6.3}, "INVALID_HALF_BAND"),
        ({**CORE, "feedback": 42}, "SCORE_SCHEMA_INVALID"),
    ],
)
async def test_non_length_scoring_repair_keeps_normal_budget(output, reason):
    provider = BudgetProvider(scoring=[output])
    result, service, events = await assess(provider)

    assert result.criteria.ta.score == Decimal("6.5")
    scores = scoring_calls(provider)
    assert [budget(call) for call in scores] == [3072] * 5
    assert len(provider.calls) == 9
    assert reason in scores[1][0][-1]["content"]
    assert service.diagnostics[0].reason == reason
    assert sum(event == "criterion.retrying" for event, _ in events) == 1


async def test_unknown_evidence_source_repair_keeps_evidence_budget():
    provider = BudgetProvider(
        evidence=[{"evidence": [{"source_id": "P99S1", "assessment": "Dẫn chứng."}]}]
    )
    result, service, _events = await assess(provider)

    assert result.criteria.ta.score == Decimal("6.5")
    assert [budget(call) for call in provider.calls[:3]] == [1800, 1800, 3072]
    assert service.diagnostics[0].reason == "EVIDENCE_UNKNOWN_SOURCE_ID"


async def test_second_length_failure_stops_after_two_scoring_calls_and_continues_other_traits():
    provider = BudgetProvider(scoring=[Completion('{"score":', finish_reason="length")] * 2)
    result, service, events = await assess(provider)

    assert result is None and set(service.failures) == {"ta"}
    assert service.failures["ta"].stage == "scoring"
    assert len(provider.calls) == 9
    assert [budget(call) for call in scoring_calls(provider)] == [3072, 4096, 3072, 3072, 3072]
    assert [(d.reason, d.attempt) for d in service.diagnostics] == [
        ("PROVIDER_FINISH_LENGTH", 1),
        ("PROVIDER_FINISH_LENGTH", 2),
    ]
    assert sum(event == "criterion.retrying" for event, _ in events) == 1
    assert [payload.criterion for event, payload in events if event == "criterion.completed"] == [
        "cc",
        "lr",
        "gra",
    ]


class Task1BudgetProvider(Task1FakeProvider):
    def __init__(self):
        super().__init__()
        self.budget_calls = []
        self.ta_calls = 0

    async def complete(self, messages, schema, *, options=None):
        self.budget_calls.append((messages, schema, options))
        completion = await super().complete(messages, schema, options=options)
        if (
            "score" in schema["properties"]
            and "Criterion: Task Achievement." in messages[0]["content"]
        ):
            self.ta_calls += 1
            if self.ta_calls == 1:
                return Completion('{"score":', finish_reason="length")
        return completion


async def test_task1_ta_and_counted_provider_forward_budget_without_changing_perception():
    provider = Task1BudgetProvider()
    counted = CountedProvider(provider)
    result, service, events = await assess(counted, Task1WritingScoringService, task1_request())

    assert result is not None and result.criteria.ta.score == Decimal(7)
    assert result.task1_analysis.claims[0].verdict == "SUPPORTED"
    assert provider.ta_calls == 2 and counted.calls == 11
    assert counted.usage["total_tokens"] == 100
    assert all(
        options is None
        for _messages, schema, options in provider.budget_calls
        if {"reference", "claims", "items"} & schema["properties"].keys()
    )
    scores = [call for call in provider.budget_calls if "score" in call[1]["properties"]]
    assert [budget(call) for call in scores] == [3072, 4096, 3072, 3072, 3072]
    assert service.diagnostics[0].reason == "PROVIDER_FINISH_LENGTH"
    assert sum(event == "criterion.retrying" for event, _ in events) == 1


@pytest.mark.parametrize(
    "provider,parameter,default",
    [("vllm", "max_tokens", 1800), ("openai", "max_completion_tokens", 4096)],
)
@pytest.mark.parametrize("requested", [None, 3072])
async def test_provider_adapters_map_typed_budget_and_preserve_defaults(
    monkeypatch, provider, parameter, default, requested
):
    assert hasattr(base, "CompletionOptions")
    options = base.CompletionOptions(max_tokens=requested)
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_provider=provider,
        ai_writing_vllm_base_url="https://provider.example/v1",
        ai_writing_openai_api_key="fictional-test-key",
    )
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]},
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    adapter = create_provider(settings)
    await adapter.complete([], {}, options=options)
    await adapter.complete([], {})
    assert bodies[0][parameter] == (default if requested is None else requested)
    assert bodies[1][parameter] == default
    other = "max_completion_tokens" if parameter == "max_tokens" else "max_tokens"
    assert all(other not in body and "reasoning" not in json.dumps(body) for body in bodies)
