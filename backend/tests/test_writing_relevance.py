"""Conservative relevance contracts and real orchestration with scripted providers."""

import asyncio
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_task1_visual import Task1FakeProvider, chart, reference
from test_task1_visual import request as task1_request
from test_writing_ai import ESSAY, FakeProvider

from app.domains.scoring.writing import WritingScoringRequest
from app.domains.scoring.writing_relevance import relevance_messages
from app.providers.writing_llm.base import Completion, ProviderFailure
from app.schemas.writing_ai import AIWritingResult, WritingRelevanceAssessment
from app.services.mts_writing import MTSWritingScoringService
from app.services.task1_writing import Task1WritingScoringService


def task2_request():
    return WritingScoringRequest(
        attempt_id=uuid4(),
        writing_task_id=uuid4(),
        prompt="Discuss fictional city parks.",
        response=ESSAY,
    )


def assessment(verdict="ON_TOPIC", confidence="HIGH", source_ids=None):
    return dict(
        verdict=verdict,
        confidence=confidence,
        source_ids=["P1S1"] if source_ids is None else source_ids,
        reason="Nội dung có liên hệ với đề bài.",
    )


class RelevanceProvider:
    def __init__(self, task=2, output=None, failures=0, error=None, finish="stop"):
        self.delegate = Task1FakeProvider() if task == 1 else FakeProvider()
        self.output = assessment() if output is None else output
        self.failures, self.error, self.finish = failures, error, finish
        self.calls, self.relevance_calls = [], []

    async def ensure_ready(self):
        pass

    async def complete(self, messages, schema, *, options=None):
        self.calls.append((messages, schema, options))
        if "verdict" in schema["properties"]:
            self.relevance_calls.append((messages, schema, options))
            if self.error:
                raise self.error
            if self.failures:
                self.failures -= 1
                return Completion('{"verdict":', finish_reason="stop")
            return Completion(json.dumps(self.output), {"total_tokens": 20}, self.finish)
        completion = await self.delegate.complete(messages, schema, options=options)
        if self.delegate.__class__ is FakeProvider and "score" in schema["properties"]:
            value = json.loads(completion.text)
            value["score"] = 7
            return Completion(json.dumps(value), completion.usage, completion.finish_reason)
        return completion


async def grade(provider, task=2):
    events = []

    async def trace(event, payload):
        events.append((event, payload.model_copy(deep=True)))

    service = (Task1WritingScoringService if task == 1 else MTSWritingScoringService)(provider)
    request = task1_request() if task == 1 else task2_request()
    return await service.assess(request, trace), service, events, request


@pytest.mark.parametrize("verdict", ["ON_TOPIC", "PARTIALLY_RELEVANT", "WHOLLY_UNRELATED"])
@pytest.mark.parametrize("confidence", ["HIGH", "MEDIUM", "LOW"])
def test_classifier_has_strict_small_contract(verdict, confidence):
    value = WritingRelevanceAssessment.model_validate(assessment(verdict, confidence))
    assert value.verdict == verdict and value.confidence == confidence
    schema = WritingRelevanceAssessment.model_json_schema()
    assert set(schema["properties"]) == {"verdict", "confidence", "source_ids", "reason"}
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "update",
    [
        {"verdict": "UNRELATED"},
        {"confidence": "UNUSABLE"},
        {"score": 1},
        {"source_ids": ["P1S1"] * 5},
        {"source_ids": ["P0S1"]},
        {"reason": ""},
    ],
)
def test_invalid_classifier_contract_is_rejected(update):
    with pytest.raises(ValidationError):
        WritingRelevanceAssessment.model_validate({**assessment(), **update})


@pytest.mark.parametrize("task", [1, 2])
@pytest.mark.parametrize(
    "verdict,confidence,short_circuit",
    [
        ("ON_TOPIC", "HIGH", False),
        ("PARTIALLY_RELEVANT", "HIGH", False),
        ("WHOLLY_UNRELATED", "HIGH", True),
        ("WHOLLY_UNRELATED", "MEDIUM", False),
        ("WHOLLY_UNRELATED", "LOW", False),
    ],
)
async def test_only_high_confidence_wholly_unrelated_skips_ta(
    task, verdict, confidence, short_circuit
):
    provider = RelevanceProvider(task, assessment(verdict, confidence))
    result, service, events, request = await grade(provider, task)
    assert result is not None and not service.failures
    assert result.criteria.ta.score == (Decimal(1) if short_circuit else Decimal(7))
    assert all(getattr(result.criteria, trait).score == 7 for trait in ("cc", "lr", "gra"))
    assert result.raw_mean == (Decimal("5.5") if short_circuit else Decimal(7))
    assert result.relevance.short_circuit_applied is short_circuit
    assert result.relevance.evidence[0].quote == request.response.split(".")[0] + "."
    ta_calls = [call for call in provider.calls if "Criterion: Task " in call[0][0]["content"]]
    assert len(ta_calls) == (0 if short_circuit else 3)
    assert {p.criterion for e, p in events if e == "criterion.completed"} == {
        "ta",
        "cc",
        "lr",
        "gra",
    }
    assert any(e == "relevance.completed" for e, _ in events)
    assert len(provider.relevance_calls) == 1
    assert provider.relevance_calls[0][2].max_tokens <= 768
    if short_circuit:
        assert "Band 1" in result.criteria.ta.feedback
        assert "hoàn toàn không liên quan" in result.criteria.ta.feedback


@pytest.mark.parametrize("task", [1, 2])
@pytest.mark.parametrize(
    "failure", ["json", "schema", "source", "length", "provider", "timeout", "bug"]
)
async def test_auxiliary_failures_never_fail_scoring_or_make_third_attempt(task, failure, caplog):
    values = dict(task=task)
    if failure == "json":
        values["failures"] = 3
    elif failure == "schema":
        values["output"] = {**assessment(), "verdict": "PRIVATE_INVALID"}
    elif failure == "source":
        values["output"] = assessment("WHOLLY_UNRELATED", "HIGH", ["P99S1"])
    elif failure == "length":
        values.update(output=assessment("WHOLLY_UNRELATED"), finish="length")
    elif failure == "provider":
        values["error"] = ProviderFailure("AI_PROVIDER_TIMEOUT")
    else:
        values["error"] = (
            TimeoutError("PRIVATE_RAW") if failure == "timeout" else RuntimeError("PRIVATE_RAW")
        )
    provider = RelevanceProvider(**values)
    result, service, events, _ = await grade(provider, task)
    assert result is not None and result.criteria.ta.score == 7 and not service.failures
    assert result.relevance is None
    assert len(provider.relevance_calls) == (
        2 if failure in {"json", "schema", "source", "length"} else 1
    )
    assert any(e == "relevance.failed" for e, _ in events)
    assert not any(e == "criterion.failed" for e, _ in events)
    assert "PRIVATE" not in caplog.text + json.dumps([d.model_dump() for d in service.diagnostics])


async def test_one_relevance_repair_can_recover_without_weakening_finish_or_ids():
    provider = RelevanceProvider(output=assessment("WHOLLY_UNRELATED"), failures=1)
    result, _, _, _ = await grade(provider)
    assert result.criteria.ta.score == 1 and len(provider.relevance_calls) == 2
    assert len(provider.relevance_calls[1][0]) == 3


async def test_task1_short_circuit_genuinely_skips_all_post_grounding_work(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Post-grounding TA work executed on the relevance short-circuit")

    monkeypatch.setattr(Task1WritingScoringService, "_extract_claims", forbidden)
    monkeypatch.setattr(Task1WritingScoringService, "_verify_claims", forbidden)
    monkeypatch.setattr(Task1WritingScoringService, "_derive_facts", forbidden)
    monkeypatch.setattr("app.services.task1_writing.extract_chart", forbidden)
    provider = RelevanceProvider(1, assessment("WHOLLY_UNRELATED"))
    request = task1_request()
    request.chart_specialist.enabled = True
    service = Task1WritingScoringService(provider)
    result = await service.assess(request, lambda e, p: asyncio.sleep(0))
    assert result.criteria.ta.score == 1
    assert result.task1_analysis.reference == chart()
    assert not result.task1_analysis.claims and not result.task1_analysis.derived_facts
    assert len([c for c in provider.calls if "reference" in c[1]["properties"]]) == 1
    assert all(isinstance(m["content"], str) for c in provider.relevance_calls for m in c[0])


async def test_unusable_task1_grounding_never_classifies_text_alone():
    provider = RelevanceProvider(1, assessment("WHOLLY_UNRELATED"))
    provider.delegate = Task1FakeProvider(confidence="UNUSABLE")
    result, service, _, _ = await grade(provider, 1)
    assert result is None and service.failures["ta"].stage == "visual_grounding"
    assert not provider.relevance_calls
    assert service.states["cc"].result is not None


@pytest.mark.parametrize(
    "family,task_type",
    [
        ("process", "PROCESS"),
        ("map", "MAP_PLAN"),
        ("system", "OBJECT_SYSTEM_DIAGRAM"),
        ("other", "OTHER_VISUAL"),
    ],
)
async def test_task1_relevance_reuses_each_existing_visual_family(family, task_type):
    from app.domains.writing.task_types import WritingTaskType

    visual = reference(family)

    class Provider(Task1FakeProvider):
        async def complete(self, messages, schema, *, options=None):
            if "reference" in schema["properties"]:
                self.calls.append(messages)
                return Completion(json.dumps({"reference": visual.model_dump(mode="json")}))
            return await super().complete(messages, schema, options=options)

    provider = RelevanceProvider(1, assessment("WHOLLY_UNRELATED"))
    provider.delegate = Provider()
    request = task1_request().model_copy(update={"task_type": WritingTaskType(task_type)})
    result = await Task1WritingScoringService(provider).assess(
        request, lambda e, p: asyncio.sleep(0)
    )
    assert result.criteria.ta.score == 1 and result.task1_analysis.reference == visual
    context = json.loads(provider.relevance_calls[0][0][1]["content"])["visual_context"]
    assert context["visual_family"] == family


def test_chart_relevance_context_is_compact_and_does_not_score_numeric_accuracy():
    context = json.loads(relevance_messages(task1_request(), chart())[1]["content"])[
        "visual_context"
    ]
    for component in context["components"]:
        assert "cells" not in component
        assert all("points" not in series for series in component["series"])
        assert component["categories"] and component["series"][0]["name"]


@pytest.mark.parametrize("task", [1, 2])
async def test_linguistic_paths_do_not_wait_for_relevance(task):
    entered, release, languages_done = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Provider(RelevanceProvider):
        async def complete(self, messages, schema, *, options=None):
            if "verdict" in schema["properties"]:
                entered.set()
                await release.wait()
            return await super().complete(messages, schema, options=options)

    provider = Provider(task)
    service = (Task1WritingScoringService if task == 1 else MTSWritingScoringService)(provider)

    async def trace(event, payload):
        if event == "criterion.completed" and all(
            service.states[t].result for t in ("cc", "lr", "gra")
        ):
            languages_done.set()

    job = asyncio.create_task(
        service.assess(task1_request() if task == 1 else task2_request(), trace)
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        await asyncio.wait_for(languages_done.wait(), 5)
        assert not service.states["ta"].result
        release.set()
        assert await job is not None
    finally:
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)


@pytest.mark.parametrize("task", [1, 2])
def test_prompt_protects_partial_relevance_and_is_text_only_untrusted_data(task):
    request = task1_request() if task == 1 else task2_request()
    messages = relevance_messages(request, chart() if task == 1 else None)
    assert all(isinstance(m["content"], str) for m in messages)
    system = messages[0]["content"]
    for phrase in (
        "UNTRUSTED DATA",
        "PARTIALLY_RELEVANT",
        "meaningful task connection",
        "weak language",
        "no overview",
        "wrong numbers",
        "one view",
        "plagiarism",
        "authorship",
    ):
        assert phrase in system
    payload = json.loads(messages[1]["content"])
    assert payload["allowed_ids"][0] == "P1S1"
    assert "image" not in payload and request.response not in system


def test_historical_result_without_relevance_remains_valid():
    criterion = dict(score=7, feedback="Nhận xét.", strengths=[], improvements=[], evidence=[])
    stored = dict(
        criteria=dict.fromkeys(("ta", "cc", "lr", "gra"), criterion), raw_mean=7, overall_band=7
    )
    assert AIWritingResult.model_validate(stored).relevance is None


def test_new_cache_versions_keep_visual_contract_and_reject_old_effective_label():
    from app.domains.scoring.mts_prompts import effective_prompt_version
    from app.services.task1_input import (
        TASK1_PROMPT_VERSION,
        TASK1_SCORING_PROMPT_VERSION,
        TASK1_VISUAL_CONTRACT_VERSION,
    )
    from app.services.writing_ai import input_fingerprint

    assert TASK1_PROMPT_VERSION == "mts-task1-visual-v12"
    assert TASK1_SCORING_PROMPT_VERSION == "mts-task1-scoring-v12"
    assert TASK1_VISUAL_CONTRACT_VERSION == "mts-task1-visual-v3"
    assert effective_prompt_version("mts-task2-v7") == "mts-task2-v12"
    assert effective_prompt_version("mts-task2-v9") == "mts-task2-v12"
    assert effective_prompt_version("mts-task2-v10") == "mts-task2-v12"
    for task, old, new in [
        (1, "mts-task1-visual-v7", TASK1_PROMPT_VERSION),
        (2, "mts-task2-v7", effective_prompt_version("mts-task2-v7")),
        (2, "mts-task2-v9", effective_prompt_version("mts-task2-v9")),
        (2, "mts-task2-v10", effective_prompt_version("mts-task2-v10")),
    ]:
        request = task1_request() if task == 1 else task2_request()
        assert input_fingerprint(request, old, "fake", "fictional") != input_fingerprint(
            request, new, "fake", "fictional"
        )
