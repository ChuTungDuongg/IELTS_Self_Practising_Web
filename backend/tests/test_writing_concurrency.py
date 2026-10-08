"""Dependency barriers and cancellation checks; no live model or timing thresholds."""

import asyncio
import json
from collections import Counter

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.evaluation.writing_latency import (
    FakeLatencyProvider,
    FakeLatencySpecialist,
    call_identity,
    fake_comparison,
    load_fixture,
    synthetic_request,
)
from app.providers.writing_llm.base import Completion
from app.schemas.writing_ai import TRAITS
from app.services.mts_writing import MTSWritingScoringService
from app.services.task1_writing import Task1WritingScoringService
from app.services.writing_execution import (
    BoundedWritingProvider,
    TraceFailure,
    WritingLatencyMetrics,
    durable_checkpoint,
)


async def noop(event, payload):
    pass


async def wait(event):
    # Timeout is a deadlock guard, never a speed assertion.
    await asyncio.wait_for(event.wait(), 5)


async def test_task2_all_evidence_overlaps_and_each_score_waits_for_own_evidence():
    evidence_started, release_evidence, release_cc = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    three_completed = asyncio.Event()
    events, started = [], set()

    class Provider(FakeLatencyProvider):
        async def complete(self, messages, schema, *, options=None):
            stage, trait = call_identity(messages, schema)
            if stage == "evidence":
                started.add(trait)
                if len(started) == 4:
                    evidence_started.set()
                await release_evidence.wait()
            if (stage, trait) == ("scoring", "cc"):
                await release_cc.wait()
            return await super().complete(messages, schema, options=options)

    async def trace(event, payload):
        events.append((event, payload.criterion))
        if sum(event == "criterion.completed" for event, _ in events) == 3:
            three_completed.set()

    provider = Provider(load_fixture(), 0)
    service = MTSWritingScoringService(provider, max_concurrent_requests=4)
    job = asyncio.create_task(service.assess(synthetic_request(2, load_fixture()), trace))
    try:
        await wait(evidence_started)
        assert not provider.calls
        release_evidence.set()
        await wait(three_completed)
        assert service.states["cc"].result is None
        release_cc.set()
        result = await job
    finally:
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)
    assert list(result.criteria.model_dump()) == list(TRAITS)
    assert [trait for event, trait in events if event == "criterion.completed"][-1] == "cc"
    for trait in TRAITS:
        assert events.index(("criterion.evidence.completed", trait)) < events.index(
            ("criterion.scoring.started", trait)
        )
        for _, call_trait, messages, _, options in provider.calls:
            if call_trait == trait:
                other_scores = {
                    other: float(service.states[other].result.score)
                    for other in TRAITS
                    if other != trait
                }
                assert all(
                    other not in json.loads(messages[1]["content"]) for other in other_scores
                )
                assert options.max_tokens in {1800, 3072}


@pytest.mark.parametrize("enabled", [False, True])
async def test_task1_text_claims_and_visuals_overlap_ta_waits_for_all_dependencies(enabled):
    fixture = load_fixture()
    starts = {
        stage: asyncio.Event()
        for stage in ("visual_grounding", "claim_extraction", "chart_specialist")
    }
    releases = {stage: asyncio.Event() for stage in starts}
    languages_done = asyncio.Event()
    events = []

    class Provider(FakeLatencyProvider):
        async def complete(self, messages, schema, *, options=None):
            stage, _ = call_identity(messages, schema)
            if stage in starts:
                starts[stage].set()
                await releases[stage].wait()
            return await super().complete(messages, schema, options=options)

    class Specialist(FakeLatencySpecialist):
        async def extract(self, image):
            starts["chart_specialist"].set()
            await releases["chart_specialist"].wait()
            return await super().extract(image)

    async def trace(event, payload):
        events.append((event, payload.criterion))
        if sum(event == "criterion.completed" and trait != "ta" for event, trait in events) == 3:
            languages_done.set()

    service = Task1WritingScoringService(
        Provider(fixture, 0), Specialist(fixture, 0), max_concurrent_requests=4
    )
    job = asyncio.create_task(service.assess(synthetic_request(1, fixture, enabled), trace))
    try:
        await wait(starts["visual_grounding"])
        await wait(starts["claim_extraction"])
        if enabled:
            await wait(starts["chart_specialist"])
        else:
            assert not starts["chart_specialist"].is_set()
        await wait(languages_done)
        assert not any(
            event == "claim_verification.started"
            or (event == "criterion.started" and trait == "ta")
            for event, trait in events
        )
        releases["visual_grounding"].set()
        releases["chart_specialist"].set()
        # Facts may be ready while the independently extracted claims are pending.
        await asyncio.sleep(0)
        assert ("claim_verification.started", "ta") not in events
        releases["claim_extraction"].set()
        result = await job
    finally:
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)
    assert result.task1_analysis.claims[0].verdict == "SUPPORTED"
    names = [event for event, _ in events]
    assert names.index("derived_facts.completed") < names.index("claim_verification.started")
    assert names.index("claim_extraction.completed") < names.index("claim_verification.started")
    assert names.index("claim_verification.completed") < events.index(("criterion.started", "ta"))
    if enabled:
        assert names.index("chart_reconciliation.completed") < names.index(
            "derived_facts.completed"
        )
    for _stage, trait, messages, _, _ in service.provider.provider.calls:
        if trait != "ta":
            assert all(isinstance(message["content"], str) for message in messages)
            assert "visual_reference" not in messages[1]["content"]


@pytest.mark.parametrize("limit", [1, 2, 4])
async def test_limit_is_per_run_not_global_and_cancellation_drains_waiters(limit):
    release = asyncio.Event()
    ready = asyncio.Event()
    active = 0

    class Provider:
        async def complete(self, *args, **kwargs):
            nonlocal active
            active += 1
            if active == limit * 2:
                ready.set()
            try:
                await release.wait()
                return Completion("{}")
            finally:
                active -= 1

    providers = [BoundedWritingProvider(Provider(), limit) for _ in range(2)]
    jobs = [
        asyncio.create_task(provider.complete([], {})) for provider in providers for _ in range(8)
    ]
    try:
        await wait(ready)
        assert [provider.active for provider in providers] == [limit, limit]
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        assert active == 0 and all(provider.active == 0 for provider in providers)
        assert [provider.peak_active for provider in providers] == [limit, limit]
    finally:
        release.set()
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)


@pytest.mark.parametrize("stage", ["evidence", "scoring"])
async def test_unexpected_python_error_is_local_and_diagnostics_belong_to_trait(stage, caplog):
    class Provider(FakeLatencyProvider):
        async def complete(self, messages, schema, *, options=None):
            identity = call_identity(messages, schema)
            if identity == (stage, "lr"):
                raise RuntimeError("PRIVATE prompt secret")
            return await super().complete(messages, schema, options=options)

    service = MTSWritingScoringService(Provider(load_fixture(), 0), max_concurrent_requests=2)
    result = await service.assess(synthetic_request(2, load_fixture()), noop)
    assert result is None and list(service.failures) == ["lr"]
    assert service.failures["lr"].stage == stage
    assert all(service.states[trait].result for trait in ("ta", "cc", "gra"))
    assert "PRIVATE" not in caplog.text + json.dumps(service.latency_summary())


@pytest.mark.parametrize("task_number", [1, 2])
async def test_run_cancellation_or_stopped_trace_cancels_inflight_children(task_number):
    class Provider(FakeLatencyProvider):
        def __init__(self):
            super().__init__(load_fixture(), 0)
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def complete(self, *args, **kwargs):
            self.started.set()
            await self.release.wait()
            return await super().complete(*args, **kwargs)

    for stopped in (False, True):
        provider = Provider()
        service = (Task1WritingScoringService if task_number == 1 else MTSWritingScoringService)(
            provider
        )
        stop = asyncio.Event()

        async def trace(event, payload, stopped=stopped, provider=provider, stop=stop):
            if stopped and event == "criterion.started" and payload.criterion == "gra":
                await wait(provider.started)
                stop.set()
                raise TraceFailure

        job = asyncio.create_task(
            service.assess(synthetic_request(task_number, load_fixture()), trace)
        )
        await wait(provider.started)
        if stopped:
            await wait(stop)
        else:
            job.cancel()
        with pytest.raises(TraceFailure if stopped else asyncio.CancelledError):
            await asyncio.wait_for(job, 5)
        assert service.provider.active == 0
        provider.release.set()
        assert provider.calls == []


def test_config_bounds_and_content_free_bounded_metrics():
    for value in (0, 5, -1):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, ai_writing_max_concurrent_llm_requests=value)
    metrics = WritingLatencyMetrics()
    for attempt in range(1, 9):
        with metrics.attempt("evidence", "lr", attempt) as record:
            metrics.completion(
                record,
                "secret finish",
                {"prompt_tokens": 4, "completion_tokens": "secret", "essay": "PRIVATE"},
            )
    metrics.completed_criterion()
    metrics.finish()
    result = metrics.summary()
    assert len(result["stages"]["lr.evidence"]["attempts"]) == 2
    assert result["time_to_first_criterion_ms"] <= result["run_total_ms"]
    assert "secret" not in json.dumps(result) and "PRIVATE" not in json.dumps(result)
    assert result["stages"]["lr.evidence"]["attempts"][0]["finish_reason"] == "other"
    snapshot = metrics.summary()
    result["stages"]["lr.evidence"]["attempts"][0]["attempt"] = 999
    assert metrics.summary() == snapshot


async def test_fake_comparison_preserves_outputs_prompts_schemas_budgets_and_counts():
    report = await fake_comparison(repeats=1, delay_ms=0)
    assert report["mode"] == "synthetic-fake" and not report["network_calls"]
    groups = Counter()
    for row in report["rows"]:
        assert row["equivalent_outputs_and_requests"]
        assert row["llm_calls"] == (8 if row["task_number"] == 2 else 11)
        assert row["total_tokens"] == row["llm_calls"] * 150
        assert row["specialist_calls"] == int(row["specialist_enabled"])
        assert row["peak_active_llm_requests"] <= row["limit"]
        groups[row["task_number"], row["specialist_enabled"]] += 1
    assert sorted(groups.values()) == [4, 4, 4]


async def test_concurrent_repairs_retain_criterion_identity_and_length_headroom():
    attempts = Counter()

    class Provider(FakeLatencyProvider):
        async def complete(self, messages, schema, *, options=None):
            stage, trait = call_identity(messages, schema)
            attempts[stage, trait] += 1
            if attempts[stage, trait] == 1 and (stage, trait) in {
                ("evidence", "lr"),
                ("scoring", "cc"),
            }:
                await asyncio.sleep(0)
                return Completion("{}", finish_reason="length" if trait == "cc" else "stop")
            if (stage, trait) == ("scoring", "cc"):
                assert options.max_tokens == 4096
            return await super().complete(messages, schema, options=options)

    service = MTSWritingScoringService(Provider(load_fixture(), 0), max_concurrent_requests=2)
    result = await service.assess(synthetic_request(2, load_fixture()), noop)
    assert result is not None
    assert {(item.criterion, item.stage, item.reason) for item in service.diagnostics} == {
        ("lr", "evidence", "EVIDENCE_SCHEMA_INVALID"),
        ("cc", "scoring", "PROVIDER_FINISH_LENGTH"),
    }
    assert service.provider.peak_active <= 2
    assert (
        service.latency.summary()["stages"]["cc.scoring"]["attempts"][0]["finish_reason"]
        == "length"
    )
    assert all(item.criterion == "lr" for item in service.states["lr"].diagnostics)


async def test_cancelled_checkpoint_is_drained_before_caller_returns():
    started, release, committed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def transaction():
        started.set()
        await release.wait()
        committed.set()

    job = asyncio.create_task(durable_checkpoint(transaction()))
    await wait(started)
    job.cancel()
    await asyncio.sleep(0)
    assert not job.done() and not committed.is_set()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await job
    assert committed.is_set()


@pytest.mark.parametrize("stage", ["evidence", "scoring"])
async def test_prompt_builder_errors_are_isolated_and_attributed(monkeypatch, stage):
    from app.services import mts_writing

    function = "evidence_messages" if stage == "evidence" else "scoring_messages"
    original = getattr(mts_writing, function)

    def broken(prompt, response, trait, *args):
        if trait == "lr":
            raise RuntimeError("PRIVATE builder bug")
        return original(prompt, response, trait, *args)

    monkeypatch.setattr(mts_writing, function, broken)
    service = MTSWritingScoringService(FakeLatencyProvider(load_fixture(), 0))
    assert await service.assess(synthetic_request(2, load_fixture()), noop) is None
    assert list(service.failures) == ["lr"] and service.failures["lr"].stage == stage
    assert all(service.states[trait].result for trait in ("ta", "cc", "gra"))
