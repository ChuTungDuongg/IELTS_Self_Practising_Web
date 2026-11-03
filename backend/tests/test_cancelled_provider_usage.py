"""Real cancellation/services/workers with memory persistence and no model/DB."""

import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_speaking_ai import FakeProvider as SpeakingProvider
from test_speaking_usage import MemorySession, memory_worker
from test_writing_ai_observer_lifecycle import WaitingTask1Provider
from test_writing_ai_observer_lifecycle import lifecycle as writing_lifecycle

from app.core.config import Settings
from app.models.enums import WritingAIRunStatus
from app.providers.writing_llm.base import Completion
from app.services.speaking_ai import SpeakingAIService
from app.services.speaking_ai_worker import GradingStopped
from app.services.writing_ai import CANCELLATION_CODE

KNOWN_USAGE = {
    "prompt_tokens": 10,
    "completion_tokens": 100,
    "total_tokens": 110,
    "reasoning_tokens": 90,
}


class PaidCancelledWritingProvider(WaitingTask1Provider):
    async def complete(self, messages, schema, *, options=None):
        try:
            return await super().complete(messages, schema, options=options)
        except asyncio.CancelledError as exc:
            exc.usage = {**KNOWN_USAGE, "private": "PRIVATE"}
            raise


async def test_real_writing_stop_preserves_late_known_usage_without_reviving_or_duplicating(
    monkeypatch,
):
    harness = writing_lifecycle.__wrapped__(SimpleNamespace(param=1), monkeypatch)
    harness.provider = PaidCancelledWritingProvider()
    harness.runner.provider = harness.provider
    row = harness.store.row
    job = asyncio.create_task(harness.runner.execute(row.id))
    try:
        await asyncio.wait_for(harness.provider.waiting.wait(), 2)
        await asyncio.wait_for(harness.store.partial_ready.wait(), 2)
        former_lease = row.lease_token
        stopped = await harness.api.cancel(row.id)
        original_calls = deepcopy(row.usage_json["calls"])
        protected = (
            deepcopy(row.result_json),
            row.completed_at,
            row.error_code,
            row.raw_mean,
            row.overall_band,
            len(harness.store.events),
        )
        cancelled_snapshot = deepcopy(row.usage_json)
        fake_mts = SimpleNamespace(
            usage=[{"total_tokens": 999}], latency_summary=lambda: {}, diagnostics=[]
        )
        await harness.runner._fail(row.id, "RUN_INTERRUPTED", "ignored", fake_mts, uuid4())
        assert row.usage_json == cancelled_snapshot
        harness.runner.cancel(row.id)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(job, 2)
        calls = row.usage_json["calls"]
        assert len(calls) == len(original_calls) + 1
        assert KNOWN_USAGE in calls
        assert row.status == WritingAIRunStatus.FAILED and row.error_code == CANCELLATION_CODE
        assert row.lease_token is None
        assert (
            row.result_json,
            row.completed_at,
            row.error_code,
            row.raw_mean,
            row.overall_band,
            len(harness.store.events),
        ) == protected
        assert await harness.api.get(row.id) == stopped
        snapshot = deepcopy(row.usage_json)
        await harness.runner._fail(row.id, "RUN_INTERRUPTED", "ignored", fake_mts, former_lease)
        assert row.usage_json == snapshot
        assert str(former_lease) not in json.dumps(row.usage_json)
        assert "PRIVATE" not in json.dumps(row.usage_json)
    finally:
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


async def test_cross_replica_writing_stop_retains_response_that_arrives_before_heartbeat(
    monkeypatch,
):
    harness = writing_lifecycle.__wrapped__(SimpleNamespace(param=1), monkeypatch)
    row = harness.store.row
    job = asyncio.create_task(harness.runner.execute(row.id))
    try:
        await asyncio.wait_for(harness.provider.waiting.wait(), 2)
        await asyncio.wait_for(harness.store.partial_ready.wait(), 2)
        await harness.api.cancel(row.id)  # Simulate Stop committed by another replica.
        original_calls = deepcopy(row.usage_json["calls"])
        protected = (deepcopy(row.result_json), row.completed_at, len(harness.store.events))
        harness.provider.release.set()  # Provider returns before lease heartbeat notices Stop.
        await asyncio.wait_for(job, 2)
        assert len(row.usage_json["calls"]) == len(original_calls) + 1
        assert row.status == WritingAIRunStatus.FAILED and row.error_code == CANCELLATION_CODE
        assert (row.result_json, row.completed_at, len(harness.store.events)) == protected
    finally:
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


class PaidCancelledSpeakingProvider(SpeakingProvider):
    def __init__(self):
        super().__init__(Completion('{"score":6.5}', {"total_tokens": 5}))
        self.waiting = asyncio.Event()

    async def ensure_ready(self):
        return None

    async def complete(self, messages, schema, *, options=None):
        if "score" in schema["properties"]:
            return await super().complete(messages, schema, options=options)
        self.waiting.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError as exc:
            exc.usage = {**KNOWN_USAGE, "private": "PRIVATE"}
            raise


def speaking_cancel_service(monkeypatch, run):
    api = SpeakingAIService(
        MemorySession(),
        SimpleNamespace(id=run.requested_by_user_id),
        Settings(_env_file=None),
        llm_identity={"provider": "fake"},
        transcript_identity={"provider": "fake"},
    )
    events = []

    async def owned(aid, run_id, *, mutate):
        assert (aid, run_id, mutate) == (run.attempt_id, run.id, True)
        return run

    async def present(aid, run_id):
        assert (aid, run_id) == (run.attempt_id, run.id)
        return SimpleNamespace(status=run.status)

    async def append(_run, event_type, _payload):
        events.append(event_type)

    monkeypatch.setattr(api, "owned_run", owned)
    monkeypatch.setattr(api, "get", present)
    api.repository = SimpleNamespace(append=append)
    return api, events


async def test_real_speaking_stop_keeps_late_usage_and_score_with_consumed_lease_fence(monkeypatch):
    provider = PaidCancelledSpeakingProvider()
    worker, run = memory_worker(monkeypatch, provider)
    api, events = speaking_cancel_service(monkeypatch, run)
    job = asyncio.create_task(worker.execute(run.id))
    try:
        await asyncio.wait_for(provider.waiting.wait(), 2)
        former_lease = run.lease_token
        await api.cancel(run.attempt_id, run.id)
        protected = (
            deepcopy(run.criteria_json),
            run.completed_at,
            run.raw_mean,
            run.overall_band,
            run.stage,
            run.error_code,
            deepcopy(events),
        )
        snapshot = deepcopy(run.usage_json)
        with pytest.raises(GradingStopped):
            await worker._record_provider_call(
                run.id,
                "wrong-lease",
                {
                    "criterion": "fc",
                    "stage": "feedback",
                    "usage": KNOWN_USAGE,
                },
            )
        assert run.usage_json == snapshot
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(job, 2)
        assert run.status == "CANCELLED" and run.lease_token is None
        assert run.criteria_json["fc"]["score"] == 6.5
        assert (
            run.criteria_json,
            run.completed_at,
            run.raw_mean,
            run.overall_band,
            run.stage,
            run.error_code,
            events,
        ) == protected
        assert run.usage_json["observed_call_count"] == 2
        assert run.usage_json["totals"] == {**KNOWN_USAGE, "total_tokens": 115}
        snapshot = deepcopy(run.usage_json)
        with pytest.raises(GradingStopped):
            await worker._record_provider_call(
                run.id,
                former_lease,
                {
                    "criterion": "fc",
                    "stage": "feedback",
                    "usage": KNOWN_USAGE,
                },
            )
        assert run.usage_json == snapshot
        assert str(former_lease) not in json.dumps(run.usage_json)
        assert "PRIVATE" not in json.dumps(run.usage_json)
    finally:
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


async def test_remote_speaking_stop_commits_late_invalid_score_usage_without_schema_repair(
    monkeypatch,
):
    class LateInvalidScoreProvider:
        def __init__(self):
            self.waiting, self.release = asyncio.Event(), asyncio.Event()
            self.call_count = 0

        async def ensure_ready(self):
            return None

        async def complete(self, _messages, _schema, *, options=None):
            self.call_count += 1
            if self.call_count == 1:
                self.waiting.set()
                await self.release.wait()
                return Completion('{"score":6.3}', KNOWN_USAGE)
            return Completion('{"score":6.5}', {"total_tokens": 5})

    provider = LateInvalidScoreProvider()
    worker, run = memory_worker(monkeypatch, provider)
    api, events = speaking_cancel_service(monkeypatch, run)

    class RollbackMemorySession(MemorySession):
        @asynccontextmanager
        async def begin(self):
            previous = deepcopy(run.usage_json)
            try:
                yield
            except BaseException:
                # Match database rollback: raising GradingStopped inside the
                # usage transaction would lose the metadata being preserved.
                run.usage_json = previous
                raise

    worker.sessions = RollbackMemorySession
    job = asyncio.create_task(worker.execute(run.id))
    try:
        await asyncio.wait_for(provider.waiting.wait(), 2)
        await api.cancel(run.attempt_id, run.id)
        protected = (deepcopy(run.criteria_json), run.completed_at, deepcopy(events))
        provider.release.set()
        await asyncio.wait_for(job, 2)
        assert provider.call_count == 1
        assert run.usage_json["totals"] == KNOWN_USAGE
        assert run.usage_json["observed_call_count"] == 1
        assert run.usage_json["cancelled_usage_fence"]["consumed"] is True
        assert run.status == run.stage == "CANCELLED" and run.lease_token is None
        assert (run.criteria_json, run.completed_at, events) == protected
        assert run.raw_mean is None and run.overall_band is None
    finally:
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


@pytest.mark.parametrize("replacement", [None, "replacement-lease"])
async def test_speaking_restarted_then_cancelled_run_rejects_former_worker(
    monkeypatch, replacement
):
    worker, run = memory_worker(monkeypatch, SpeakingProvider())
    api, events = speaking_cancel_service(monkeypatch, run)
    run.status, run.lease_token = "RUNNING", "former-lease"
    await api.cancel(run.attempt_id, run.id)
    run.status, run.stage, run.lease_token = "PENDING", "PENDING", None
    if replacement is not None:
        run.status, run.lease_token = "RUNNING", replacement
    await api.cancel(run.attempt_id, run.id)
    snapshot = deepcopy(run.usage_json)
    with pytest.raises(GradingStopped):
        await worker._record_provider_call(
            run.id,
            "former-lease",
            {
                "criterion": "fc",
                "stage": "feedback",
                "usage": KNOWN_USAGE,
            },
        )
    assert run.usage_json == snapshot
    assert run.status == run.stage == "CANCELLED"
    assert events == ["run.cancelled", "run.cancelled"]


def test_cancelled_usage_authority_is_replaced_cleared_and_consumed_once():
    from app.services.cancelled_usage import arm_cancelled_usage, consume_cancelled_usage

    initial = arm_cancelled_usage({"calls": [{"total_tokens": 3}]}, "old-lease")
    assert consume_cancelled_usage(initial, "wrong") is None
    consumed = consume_cancelled_usage(initial, "old-lease")
    assert consumed is not None and consumed["calls"] == initial["calls"]
    assert consume_cancelled_usage(consumed, "old-lease") is None
    queued_cancelled = arm_cancelled_usage(initial, None)
    assert consume_cancelled_usage(queued_cancelled, "old-lease") is None
    replacement = arm_cancelled_usage(initial, "replacement-lease")
    assert consume_cancelled_usage(replacement, "old-lease") is None
    assert consume_cancelled_usage(replacement, "replacement-lease") is not None
    assert "old-lease" not in json.dumps(initial)
    corrupted = {"cancelled_usage_fence": {"lease_sha256": "ắ" * 64, "consumed": False}}
    assert consume_cancelled_usage(corrupted, "old-lease") is None
