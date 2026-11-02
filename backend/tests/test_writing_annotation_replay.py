"""Durable semantic feedback checkpoints and replay, without a DB or provider."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_writing_ai_observer_lifecycle as lifecycle_tests
from test_writing_ai import FakeProvider

from app.api.v1.writing_ai import event_stream, replay_cursor
from app.models import WritingAIGradingRun
from app.models.enums import WritingAIRunStatus
from app.schemas.writing_ai import AIWritingResult, CriterionResult, EventPayload
from app.services.mts_writing import MTSWritingScoringService
from app.services.writing_ai import persist_activity

lifecycle = lifecycle_tests.lifecycle


async def claim_lifecycle(lifecycle):
    async with lifecycle.sessions() as session, session.begin():
        row = await lifecycle_tests.MemoryRepository(session).claim(
            run_id=lifecycle.store.row.id, lease_seconds=60, max_running=4
        )
        return row.lease_token


@pytest.mark.parametrize(
    ("event_type", "expected_phase"),
    [
        ("criterion.feedback.started", "generating_feedback"),
        ("criterion.feedback.completed", "feedback_completed"),
    ],
)
def test_feedback_activity_snapshots_describe_generation_after_scoring(event_type, expected_phase):
    now = datetime.now(UTC)
    row = WritingAIGradingRun(id=uuid4(), updated_at=now)
    # Existing DTOs can already represent feedback completion diagnostics, but
    # the new public activity stage must survive checkpoint/snapshot validation.
    payload = EventPayload.model_validate({"criterion": "gra", "stage": "feedback"})
    persist_activity(row, event_type, payload)
    assert row.usage_json["activity"] == {
        "phase": expected_phase,
        "criterion": "gra",
        "stage": "feedback",
        "started_at": now.isoformat().replace("+00:00", "Z"),
    }


async def test_feedback_checkpoints_replay_and_final_snapshot_keep_the_same_annotation(lifecycle):
    row = lifecycle.store.row
    token = await claim_lifecycle(lifecycle)
    row.started_at = datetime.now(UTC)
    annotation = {
        "id": "stable-grammar-id",
        "criterion": "gra",
        "kind": "ERROR",
        "source_id": "P1S1",
        "start_offset": 0,
        "end_offset": 12,
        "original_span": "people tends",
        "suggested_revision": "people tend",
        "message": "Chủ ngữ số nhiều cần động từ dạng nguyên mẫu.",
        "confidence": "HIGH",
        "category": "grammar",
    }
    accepted_band = CriterionResult(
        score=6.5,
        feedback="Đang chờ nhận xét.",
        strengths=[],
        improvements=[],
        evidence=[],
        feedback_status="PENDING",
    )
    final_criterion = CriterionResult.model_validate(
        {
            **accepted_band.model_dump(),
            "feedback": annotation["message"],
            "annotations": [annotation],
            "feedback_status": "COMPLETED",
        }
    )
    await lifecycle.runner._checkpoint(
        row.id,
        "criterion.feedback.started",
        EventPayload(criterion="gra", stage="feedback", result=accepted_band),
        token=token,
    )
    active, _ = await lifecycle.api.snapshot(row.id, 0)
    assert active.activity.phase == "generating_feedback"
    assert active.progress["gra"].score == 6.5
    assert active.progress["gra"].annotations == []
    assert active.progress["gra"].feedback_status == "PENDING"
    await lifecycle.runner._checkpoint(
        row.id,
        "criterion.feedback.annotation",
        EventPayload.model_validate(
            {"criterion": "gra", "stage": "feedback", "annotation": annotation}
        ),
        token=token,
    )
    for event_type in ("criterion.feedback.completed", "criterion.completed"):
        await lifecycle.runner._checkpoint(
            row.id,
            event_type,
            EventPayload(criterion="gra", stage="feedback", result=final_criterion),
            token=token,
        )
    final_result = AIWritingResult(
        criteria={
            trait: final_criterion
            if trait == "gra"
            else accepted_band.model_copy(update={"feedback_status": "COMPLETED"})
            for trait in ("ta", "cc", "lr", "gra")
        },
        raw_mean=6.5,
        overall_band=6.5,
    )
    await lifecycle.runner._complete(
        row.id,
        final_result,
        SimpleNamespace(usage=[], diagnostics=[], latency_summary=lambda: {}),
        token,
    )
    saved, events = await lifecycle.api.snapshot(row.id, 0)
    assert saved.result.criteria.gra.annotations[0].id == "stable-grammar-id"
    assert saved.result.criteria.gra.feedback_status == "COMPLETED"
    assert saved.progress["gra"] == saved.result.criteria.gra
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5]
    assert [event.event_type for event in events] == [
        "criterion.feedback.started",
        "criterion.feedback.annotation",
        "criterion.feedback.completed",
        "criterion.completed",
        "run.completed",
    ]
    assert events[1].payload.annotation == final_criterion.annotations[0]
    restored, later = await lifecycle.api.snapshot(row.id, replay_cursor(0, "2"))
    assert restored == saved
    assert [event.sequence for event in later] == [3, 4, 5]
    assert all(event.event_type != "criterion.feedback.annotation" for event in later)

    # Exercise production SSE framing against those persisted semantic events.
    async def connected():
        return False

    stream = event_stream(
        SimpleNamespace(is_disconnected=connected), row.id, lifecycle.owner, 1, lifecycle.runner
    )
    frames = [frame async for frame in stream]
    assert len(frames) == 4
    assert frames[0].startswith("id: 2\nevent: criterion.feedback.annotation\ndata: ")
    assert '"id":"stable-grammar-id"' in frames[0]
    assert '"sequence":1,' not in "".join(frames)
    assert "prompt" not in "".join(frames) and "diagnostics" not in "".join(frames)


async def test_unavailable_feedback_checkpoint_keeps_accepted_score_when_run_later_fails(lifecycle):
    row = lifecycle.store.row
    token = await claim_lifecycle(lifecycle)
    unavailable = CriterionResult(
        score=6.5,
        feedback="Nhận xét chi tiết tạm thời chưa khả dụng.",
        strengths=[],
        improvements=[],
        evidence=[],
        feedback_status="UNAVAILABLE",
    )
    await lifecycle.runner._checkpoint(
        row.id,
        "criterion.feedback.completed",
        EventPayload(criterion="gra", stage="feedback", result=unavailable),
        token=token,
    )
    await lifecycle.runner._fail(
        row.id, "AI_PROVIDER_TIMEOUT", "Chấm AI bị gián đoạn.", None, token
    )
    saved, events = await lifecycle.api.snapshot(row.id, 0)
    assert saved.status == WritingAIRunStatus.FAILED and saved.result is None
    assert saved.progress["gra"].score == 6.5
    assert saved.progress["gra"].feedback_status == "UNAVAILABLE"
    assert saved.progress["gra"].annotations == []
    assert not any(event.event_type == "criterion.feedback.annotation" for event in events)
    assert events[-1].event_type == "run.failed"


async def test_snapshot_retains_both_pending_feedback_states_when_activity_moves(lifecycle):
    row = lifecycle.store.row
    token = await claim_lifecycle(lifecycle)
    accepted = CriterionResult(
        score=7,
        feedback="Đang chờ nhận xét.",
        strengths=[],
        improvements=[],
        evidence=[],
        feedback_status="PENDING",
    )
    for trait in ("gra", "lr"):
        await lifecycle.runner._checkpoint(
            row.id,
            "criterion.feedback.started",
            EventPayload(criterion=trait, stage="feedback", result=accepted),
            token=token,
        )
    snapshot, _ = await lifecycle.api.snapshot(row.id, 0)
    assert snapshot.activity.criterion == "lr"
    assert snapshot.progress["lr"].feedback_status == "PENDING"
    assert snapshot.progress["gra"].feedback_status == "PENDING"
    assert snapshot.result is None


@pytest.mark.parametrize("interruption", ["worker_shutdown", "stale_recovery"])
async def test_interrupted_pending_feedback_persists_each_failure_without_losing_bands(
    lifecycle, interruption
):
    row = lifecycle.store.row
    token = await claim_lifecycle(lifecycle)
    complete = CriterionResult(
        score=7, feedback="Nhận xét đã sẵn sàng.", strengths=[], improvements=[], evidence=[]
    )
    for trait in ("ta", "cc", "gra", "lr"):
        result = complete.model_copy(
            update={"feedback_status": "PENDING" if trait in {"gra", "lr"} else "COMPLETED"}
        )
        await lifecycle.runner._checkpoint(
            row.id,
            "criterion.feedback.started" if trait in {"gra", "lr"} else "criterion.completed",
            EventPayload(criterion=trait, stage="feedback", result=result),
            token=token,
        )
    before = await lifecycle.api.get(row.id)
    if interruption == "worker_shutdown":
        scoring = MTSWritingScoringService(FakeProvider())
        for trait in ("gra", "lr"):
            scoring.states[trait].stage = "feedback"
        await lifecycle.runner._fail(
            row.id, "RUN_INTERRUPTED", "Chấm AI bị gián đoạn.", scoring, token
        )
    else:
        row.lease_expires_at = datetime.now(UTC) - timedelta(minutes=10)
        await lifecycle.runner.recover()
    restored, events = await lifecycle.api.snapshot(row.id, 0)
    assert restored.status == WritingAIRunStatus.FAILED
    assert restored.progress == before.progress
    assert set(restored.failures) == {"gra", "lr"}
    assert all(failure.stage == "feedback" for failure in restored.failures.values())
    assert {
        event.payload.criterion for event in events if event.event_type == "criterion.failed"
    } == {"gra", "lr"}
    assert events[-1].event_type == "run.failed"
