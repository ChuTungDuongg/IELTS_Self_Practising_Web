"""Speaking call accounting uses fake providers and an in-memory database boundary."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_speaking_ai import FEEDBACK, FakeProvider, checkpoint, evidence, feature_bundle

from app.providers.speaking_llm.base import Completion
from app.providers.writing_llm.base import ProviderFailure
from app.services.speaking_ai_worker import GradingStopped, SpeakingAIWorker
from app.services.speaking_scorer import SpeakingScorer


async def test_usage_observes_score_repair_and_feedback_before_score_checkpoint():
    records = []
    provider = FakeProvider(
        Completion(
            '{"score": 6.3}', {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
        ),
        Completion(
            '{"score": 6.5}', {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}
        ),
        Completion(
            json.dumps(FEEDBACK),
            {"prompt_tokens": 20, "completion_tokens": 4, "total_tokens": 24, "secret": "PRIVATE"},
        ),
    )

    async def observe(record):
        records.append(record)

    async def persist(result):
        assert result.score == 6.5
        assert [record["stage"] for record in records] == ["score", "score_repair"]

    result = await SpeakingScorer(provider, on_provider_call=observe).score_criterion(
        "fc", evidence(), persist
    )
    assert result.status == "COMPLETED" and result.score == 6.5
    assert records == [
        {
            "criterion": "fc",
            "stage": "score",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        },
        {
            "criterion": "fc",
            "stage": "score_repair",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
        },
        {
            "criterion": "fc",
            "stage": "feedback",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 20, "completion_tokens": 4, "total_tokens": 24},
        },
    ]


async def test_provider_failure_usage_and_cause_are_safe_without_retry_or_score():
    records = []

    async def observe(record):
        records.append(record)

    failure = ProviderFailure(
        "AI_PROVIDER_BAD_RESPONSE",
        reason="PROVIDER_FINISH_LENGTH",
        finish_reason="length",
        usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    )
    # Revalidate diagnostics at the observer boundary, even for a mutated adapter exception.
    failure.usage.update({"private": "PRIVATE_BODY", "bad": True})
    provider = FakeProvider(failure)
    result = await SpeakingScorer(provider, on_provider_call=observe).score_criterion(
        "lr", evidence(), checkpoint
    )
    assert result.score is None and result.error_code == "SPEAKING_AI_PROVIDER_FAILED"
    assert len(provider.calls) == 1
    assert records == [
        {
            "criterion": "lr",
            "stage": "score",
            "finish_reason": "length",
            "provider_error_code": "AI_PROVIDER_BAD_RESPONSE",
            "reason": "PROVIDER_FINISH_LENGTH",
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }
    ]
    assert "PRIVATE" not in json.dumps(records)


async def test_feedback_failure_accounts_usage_and_keeps_band_without_arbitrary_exception_code():
    records = []

    async def observe(record):
        records.append(record)

    failure = ProviderFailure("AI_PROVIDER_RATE_LIMITED", usage={"total_tokens": 8})
    failure.code = "PRIVATE_EXCEPTION_CODE"
    failure.reason = "PRIVATE_REASON"
    failure.finish_reason = "PRIVATE_FINISH"
    provider = FakeProvider(Completion('{"score": 6.5}', {"total_tokens": 5}), failure)
    result = await SpeakingScorer(provider, on_provider_call=observe).score_criterion(
        "gra", evidence(), checkpoint
    )
    assert result.score == 6.5 and result.status == "FEEDBACK_FAILED"
    assert records[-1] == {
        "criterion": "gra",
        "stage": "feedback",
        "usage": {"total_tokens": 8},
        "provider_error_code": "SPEAKING_AI_PROVIDER_FAILED",
        "finish_reason": "other",
    }
    assert "PRIVATE" not in json.dumps(records) + result.model_dump_json()


async def test_usage_checkpoint_failure_propagates_before_band_or_feedback():
    provider = FakeProvider({"score": 6.5}, FEEDBACK)
    checkpoints = []

    async def observe(_record):
        raise RuntimeError("accounting checkpoint unavailable")

    async def persist(result):
        checkpoints.append(result)

    with pytest.raises(RuntimeError, match="accounting checkpoint unavailable"):
        await SpeakingScorer(provider, on_provider_call=observe).score_criterion(
            "fc", evidence(), persist
        )
    assert len(provider.calls) == 1 and not checkpoints


async def test_feedback_validation_exception_preserves_checkpointed_band_and_usage():
    records = []

    async def observe(record):
        records.append(record)

    provider = FakeProvider({"score": 6.5}, Completion("\ud800", {"completion_tokens": 1}))
    result = await SpeakingScorer(provider, on_provider_call=observe).score_criterion(
        "fc", evidence(), checkpoint
    )
    assert result.status == "FEEDBACK_FAILED" and result.score == 6.5
    assert records[-1]["usage"] == {"completion_tokens": 1}


async def test_feedback_accounting_failure_propagates_with_score_checkpoint_intact():
    checkpoints = []

    async def observe(record):
        if record["stage"] == "feedback":
            raise RuntimeError("feedback accounting unavailable")

    async def persist(result):
        checkpoints.append(result)

    with pytest.raises(RuntimeError, match="feedback accounting unavailable"):
        await SpeakingScorer(
            FakeProvider({"score": 6.5}, FEEDBACK), on_provider_call=observe
        ).score_criterion("fc", evidence(), persist)
    assert len(checkpoints) == 1 and checkpoints[0].score == 6.5


class MemorySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def begin(self):
        return self

    async def get(self, *_args):
        return SimpleNamespace(id=uuid4())


def memory_worker(monkeypatch, provider):
    run = SimpleNamespace(
        id=uuid4(),
        attempt_id=uuid4(),
        requested_by_user_id=uuid4(),
        status="PENDING",
        stage="PENDING",
        lease_token=None,
        criteria_json={},
        usage_json={},
        identity_json={"provider": "fake"},
        started_at=None,
        heartbeat_at=None,
        raw_mean=None,
        overall_band=None,
    )
    worker = SpeakingAIWorker(
        MemorySession,
        SimpleNamespace(),
        scorer=SpeakingScorer(provider),
    )

    async def locked(_session, run_id, token):
        if run_id != run.id or token != run.lease_token or run.status != "RUNNING":
            raise GradingStopped()
        return run

    async def get_run(_repository, run_id, **_options):
        assert run_id == run.id
        return run

    async def append(_repository, *_args, **_options):
        return None

    async def transcript(*_args):
        return None

    attempt_evidence = evidence(features=feature_bundle())

    async def input_evidence(*_args):
        return attempt_evidence

    monkeypatch.setattr(worker, "_locked", locked)
    monkeypatch.setattr(
        worker, "service", lambda *_args: SimpleNamespace(identity=run.identity_json)
    )
    monkeypatch.setattr(worker, "_ensure_transcript", transcript)
    monkeypatch.setattr(worker, "_input", input_evidence)
    monkeypatch.setattr("app.repositories.speaking_ai.SpeakingAIRepository.run", get_run)
    monkeypatch.setattr("app.repositories.speaking_ai.SpeakingAIRepository.append", append)
    return worker, run


async def test_worker_persists_all_observed_calls_and_totals_with_feedback_failure(monkeypatch):
    class Provider(FakeProvider):
        async def ensure_ready(self):
            return None

    outputs = []
    for _trait in range(4):
        outputs.extend(
            [
                Completion(
                    '{"score": 6.5}',
                    {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                ),
                ProviderFailure(
                    "AI_PROVIDER_RATE_LIMITED", usage={"prompt_tokens": 7, "total_tokens": 7}
                ),
            ]
        )
    worker, run = memory_worker(monkeypatch, Provider(*outputs))
    await worker.execute(run.id)
    assert run.status == "COMPLETED" and run.overall_band == 6.5
    assert all(row["score"] == 6.5 for row in run.criteria_json.values())
    assert run.usage_json["accounting"] == "observed_partial"
    assert run.usage_json["observed_call_count"] == 8
    assert run.usage_json["totals"] == {
        "prompt_tokens": 48,
        "completion_tokens": 4,
        "total_tokens": 52,
    }
    assert len(run.usage_json["calls"]) == 8
    assert all(
        record["provider_error_code"] == "AI_PROVIDER_RATE_LIMITED"
        for record in run.usage_json["calls"][1::2]
    )


async def test_worker_usage_history_is_bounded_totals_survive_resume_and_stale_lease_cannot_write(
    monkeypatch,
):
    worker, run = memory_worker(monkeypatch, FakeProvider())
    run.status, run.lease_token = "RUNNING", "current"
    run.usage_json = {
        "retained": "metadata",
        "totals": {"total_tokens": 9},
        "observed_call_count": 1,
    }
    for _call in range(35):
        await worker._record_provider_call(
            run.id,
            "current",
            {
                "criterion": "fc",
                "stage": "feedback",
                "finish_reason": "stop",
                "usage": {"total_tokens": 2},
            },
        )
    assert len(run.usage_json["calls"]) == 32
    assert run.usage_json["totals"] == {"total_tokens": 79}
    assert run.usage_json["observed_call_count"] == 36
    assert run.usage_json["retained"] == "metadata"
    snapshot = json.dumps(run.usage_json, sort_keys=True)
    with pytest.raises(GradingStopped):
        await worker._record_provider_call(run.id, "expired", {"usage": {"total_tokens": 100}})
    assert json.dumps(run.usage_json, sort_keys=True) == snapshot


async def test_shutdown_resume_accumulates_usage_without_repeating_checkpointed_score(monkeypatch):
    class InterruptedProvider(FakeProvider):
        async def ensure_ready(self):
            return None

        async def complete(self, messages, schema, *, options=None):
            if "score" not in schema["properties"]:
                raise asyncio.CancelledError()
            return await super().complete(messages, schema, options=options)

    worker, run = memory_worker(
        monkeypatch, InterruptedProvider(Completion('{"score": 6.5}', {"total_tokens": 2}))
    )
    with pytest.raises(asyncio.CancelledError):
        await worker.execute(run.id)
    assert run.status == "PENDING" and run.criteria_json["fc"]["score"] == 6.5
    assert run.usage_json["totals"] == {"total_tokens": 2}
    assert run.usage_json["observed_call_count"] == 1

    class ResumedProvider(FakeProvider):
        async def ensure_ready(self):
            return None

    provider = ResumedProvider(
        Completion(json.dumps(FEEDBACK), {"total_tokens": 2}),
        *[
            completion
            for _criterion in range(3)
            for completion in (
                Completion('{"score": 6.5}', {"total_tokens": 2}),
                Completion(json.dumps(FEEDBACK), {"total_tokens": 2}),
            )
        ],
    )
    worker.scorer = SpeakingScorer(provider)
    await worker.execute(run.id)
    assert run.status == "COMPLETED" and run.overall_band == 6.5
    assert sum("score" in schema["properties"] for _, schema, _ in provider.calls) == 3
    assert run.usage_json["totals"] == {"total_tokens": 16}
    assert run.usage_json["observed_call_count"] == 8


async def test_accounting_rejects_nonfinite_boolean_negative_and_unbounded_tokens(monkeypatch):
    worker, run = memory_worker(monkeypatch, FakeProvider())
    run.status, run.lease_token = "RUNNING", "current"
    run.usage_json = {
        "totals": {"total_tokens": 9_007_199_254_740_990},
        "observed_call_count": 9_007_199_254_740_991,
    }
    await worker._record_provider_call(
        run.id,
        "current",
        {
            "criterion": "fc",
            "stage": "score",
            "finish_reason": "PRIVATE_FINISH",
            "usage": {"prompt_tokens": True, "completion_tokens": float("inf"), "total_tokens": 5},
            "private_body": "PRIVATE_TRANSCRIPT",
        },
    )
    await worker._record_provider_call(
        run.id,
        "current",
        {
            "criterion": "fc",
            "stage": "score_repair",
            "usage": {"prompt_tokens": -1, "completion_tokens": 10_000_001},
        },
    )
    assert run.usage_json["totals"] == {"total_tokens": 9_007_199_254_740_991}
    assert run.usage_json["observed_call_count"] == 9_007_199_254_740_991
    assert run.usage_json["calls"][0]["usage"] == {"total_tokens": 5}
    assert run.usage_json["calls"][1]["usage"] == {}
    assert "PRIVATE" not in json.dumps(run.usage_json)
