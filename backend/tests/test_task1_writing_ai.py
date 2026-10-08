"""Task 1 lifecycle through the existing PostgreSQL run/event infrastructure."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from test_task1_visual import ESSAY, PNG, Task1FakeProvider
from test_writing_ai import service, worker
from test_writing_ai import settings as settings
from test_writing_ai import writing as writing

from app.api.v1.writing_ai import event_stream
from app.core.exceptions import AppError
from app.domains.writing.task_types import WritingTaskType
from app.models import (
    Asset,
    Attempt,
    AttemptWritingResponse,
    AttemptWritingScore,
    WritingAIGradingRun,
    WritingTask,
)
from app.models import TestSession as DomainSession
from app.models.enums import AssetType, AttemptStatus, ModuleType, WritingAIRunStatus
from app.models.enums import TestSessionStatus as SessionStatus
from app.services.task1_input import TASK1_PROMPT_VERSION

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def task1(db_session, writing, settings, tmp_path):
    attempt_id, task_id, _ = writing
    settings.storage_root = tmp_path
    image = tmp_path / "frozen.png"
    image.write_bytes(PNG)
    async with db_session.begin():
        attempt = await db_session.get(Attempt, attempt_id)
        asset = Asset(
            test_version_id=attempt.test_version_id,
            asset_type=AssetType.WRITING_TASK_IMAGE,
            relative_path="frozen.png",
            original_name="Synthetic chart.png",
            mime_type="image/png",
            file_size=len(PNG),
        )
        db_session.add(asset)
        await db_session.flush()
        task = await db_session.get(WritingTask, task_id)
        task.task_type, task.image_asset_id = WritingTaskType.LINE_GRAPH.value, asset.id
        db_session.add_all(
            [
                AttemptWritingResponse(
                    attempt_id=attempt_id, writing_task_id=task_id, content=ESSAY, word_count=12
                ),
                AttemptWritingScore(
                    attempt_id=attempt_id,
                    writing_task_id=task_id,
                    ta=6,
                    cc=6,
                    lr=6,
                    gra=6,
                    ta_feedback="Human Task 1 feedback.",
                ),
            ]
        )
    return attempt_id, task_id, asset.id, image


async def test_task1_persists_replays_caches_and_never_changes_official_scores(
    db_session, task1, settings
):
    attempt_id, task_id, _, _ = task1
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    active = await api.create(attempt_id, task_id, force=False)
    assert active.run_id == created.run_id and active.existing_active
    provider = Task1FakeProvider()
    runner = worker(db_session, settings, provider)
    await runner.execute(created.run_id)
    run, events = await api.snapshot(created.run_id, 0)
    assert run.status == WritingAIRunStatus.COMPLETED and run.task_number == 1
    assert run.prompt_version == TASK1_PROMPT_VERSION and run.result.overall_band == Decimal(7)
    assert run.result.task_number == 1 and run.task1_analysis == run.result.task1_analysis
    assert run.task1_analysis.derived_facts and run.task1_analysis.claims[0].verdict == "SUPPORTED"
    assert run.task1_analysis.claims[0].quote == "A increased from 20 to 50."
    types = [event.event_type for event in events]
    for event in [
        "visual_grounding.started",
        "visual_grounding.completed",
        "derived_facts.completed",
        "claim_extraction.completed",
        "claim_verification.completed",
        "criterion.started",
        "criterion.completed",
        "run.completed",
    ]:
        assert event in types
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    cursor = next(
        event.sequence for event in events if event.event_type == "claim_verification.completed"
    )
    restored, replay = await api.snapshot(run.id, cursor)
    assert restored == run and replay[0].event_type == "criterion.started"
    chunks = [
        chunk
        async for chunk in event_stream(
            SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
            run.id,
            db_session.info["current_user_id"],
            cursor,
            runner,
        )
    ]
    assert chunks[-1].startswith(f"id: {events[-1].sequence}\nevent: run.completed\n")
    assert all(json.loads(chunk.split("data: ")[1])["sequence"] > cursor for chunk in chunks)
    await runner.execute(run.id)
    assert len(provider.calls) == 10
    cached = await api.create(attempt_id, task_id, force=False)
    assert cached.run_id == run.id and cached.cache_hit
    forced = await api.create(attempt_id, task_id, force=True)
    assert forced.run_id != run.id and not forced.cache_hit
    assert len((await api.list(attempt_id, task_id)).items) == 2
    public = run.model_dump_json() + str(events)
    assert "base64" not in public and "iVBOR" not in public and "system" not in public
    async with db_session.begin():
        db_session.expire_all()
        attempt = await db_session.get(Attempt, attempt_id)
        human = await db_session.scalar(
            select(AttemptWritingScore).where(
                AttemptWritingScore.attempt_id == attempt_id,
                AttemptWritingScore.writing_task_id == task_id,
            )
        )
        assert attempt.band_score == Decimal(7)
        assert (human.ta, human.cc, human.lr, human.gra, human.ta_feedback) == (
            6,
            6,
            6,
            6,
            "Human Task 1 feedback.",
        )
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(AttemptWritingScore)
                .where(AttemptWritingScore.attempt_id == attempt_id)
            )
            == 2
        )


@pytest.mark.parametrize("failure", ["grounding", "ta", "lr"])
async def test_task1_failure_persists_partial_results_and_replays_later_criteria(
    db_session, task1, settings, failure
):
    attempt_id, task_id, _, _ = task1
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    provider = Task1FakeProvider(
        malformed_grounding=2 if failure == "grounding" else 0,
        fail_trait={"ta": "Task Achievement", "lr": "Lexical Resource"}.get(failure),
    )
    await worker(db_session, settings, provider).execute(created.run_id)
    run, events = await api.snapshot(created.run_id, 0)
    failed_trait = "lr" if failure == "lr" else "ta"
    assert run.status == WritingAIRunStatus.FAILED and run.result is None
    assert set(run.progress) == {"ta", "cc", "lr", "gra"} - {failed_trait}
    assert set(run.failures) == {failed_trait} and run.task1_analysis is not None
    assert events[-1].event_type == "run.failed"
    assert (
        next(event for event in events if event.event_type == "criterion.failed").payload.criterion
        == failed_trait
    )
    assert any(
        event.event_type == "criterion.completed" and event.payload.criterion == "gra"
        for event in events
    )
    if failure == "grounding":
        assert any(event.event_type == "visual_grounding.failed" for event in events)
    async with db_session.begin():
        stored = await db_session.get(WritingAIGradingRun, run.id)
        assert stored.raw_mean is None and stored.overall_band is None
    retry = await api.create(attempt_id, task_id, force=False)
    assert retry.run_id != run.id


@pytest.mark.parametrize(
    "violation,code",
    [
        ("owner", "ATTEMPT_NOT_FOUND"),
        ("active", "ATTEMPT_NOT_FINALIZED"),
        ("unfinished", "ATTEMPT_NOT_FINALIZED"),
        ("reading", "WRITING_ATTEMPT_REQUIRED"),
        ("foreign_task", "INVALID_WRITING_TASK"),
        ("empty", "AI_EMPTY_ESSAY"),
        ("missing_image", "AI_TASK1_IMAGE_MISSING"),
        ("foreign_asset", "AI_TASK1_IMAGE_INVALID"),
        ("wrong_kind", "AI_TASK1_IMAGE_INVALID"),
        ("mime", "AI_TASK1_IMAGE_INVALID"),
        ("bytes", "AI_TASK1_IMAGE_INVALID"),
        ("size", "AI_TASK1_IMAGE_INVALID"),
        ("missing_bytes", "AI_TASK1_IMAGE_INVALID"),
        ("path", "AI_TASK1_IMAGE_INVALID"),
        ("task_type", "AI_INVALID_TASK_TYPE"),
        ("disabled", "AI_NOT_CONFIGURED"),
        ("full_mock", "FULL_MOCK_REVIEW_LOCKED"),
    ],
)
async def test_task1_eligibility_trusted_asset_and_ownership(
    db_session, task1, settings, violation, code
):
    attempt_id, task_id, asset_id, image = task1
    async with db_session.begin():
        attempt = await db_session.get(Attempt, attempt_id)
        task = await db_session.get(WritingTask, task_id)
        asset = await db_session.get(Asset, asset_id)
        if violation == "active":
            attempt.status = AttemptStatus.IN_PROGRESS
        elif violation == "unfinished":
            attempt.finished_at = None
        elif violation == "reading":
            attempt.module_type = ModuleType.READING
        elif violation == "empty":
            response = await db_session.scalar(
                select(AttemptWritingResponse).where(
                    AttemptWritingResponse.attempt_id == attempt_id,
                    AttemptWritingResponse.writing_task_id == task_id,
                )
            )
            response.content = " "
        elif violation == "missing_image":
            task.image_asset_id = None
        elif violation == "foreign_asset":
            # A different existing frozen version, never an arbitrary URL.
            from app.models import TestVersion

            version = await db_session.get(TestVersion, attempt.test_version_id)
            other = TestVersion(test_id=version.test_id, version_number=2)
            db_session.add(other)
            await db_session.flush()
            asset.test_version_id = other.id
        elif violation == "wrong_kind":
            asset.asset_type = AssetType.LISTENING_AUDIO
        elif violation == "mime":
            asset.mime_type = "image/svg+xml"
        elif violation == "bytes":
            image.write_bytes(b"x" * len(PNG))
        elif violation == "size":
            asset.file_size = 20 * 1024 * 1024
        elif violation == "missing_bytes":
            asset.relative_path = "does-not-exist.png"
        elif violation == "path":
            asset.relative_path = "../outside.png"
        elif violation == "task_type":
            task.task_type = "OPINION"
        elif violation == "disabled":
            settings.ai_writing_enabled = False
        elif violation == "full_mock":
            mock = DomainSession(
                test_version_id=attempt.test_version_id,
                status=SessionStatus.IN_PROGRESS,
                started_at=datetime.now(UTC),
            )
            db_session.add(mock)
            await db_session.flush()
            attempt.test_session_id = mock.id
    with pytest.raises(AppError) as error:
        await service(db_session, settings, uuid4() if violation == "owner" else None).create(
            attempt_id, uuid4() if violation == "foreign_task" else task_id, force=False
        )
    assert error.value.code == code


async def test_changed_image_bytes_separate_cache_and_worker_rejects_stale_input(
    db_session, task1, settings
):
    attempt_id, task_id, asset_id, image = task1
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    await worker(db_session, settings, Task1FakeProvider()).execute(created.run_id)
    image.write_bytes(PNG + b"synthetic-change")
    async with db_session.begin():
        (await db_session.get(Asset, asset_id)).file_size = image.stat().st_size
    changed = await api.create(attempt_id, task_id, force=False)
    assert changed.run_id != created.run_id and not changed.cache_hit
    image.write_bytes(PNG)
    async with db_session.begin():
        (await db_session.get(Asset, asset_id)).file_size = len(PNG)
    provider = Task1FakeProvider()
    await worker(db_session, settings, provider).execute(changed.run_id)
    assert (await api.get(changed.run_id)).error_code == "AI_CONFIGURATION_CHANGED"
    assert not provider.calls


async def test_task1_history_remains_readable_without_image_and_new_runs_require_it(
    db_session, task1, settings
):
    attempt_id, task_id, _, image = task1
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    await worker(db_session, settings, Task1FakeProvider()).execute(created.run_id)
    image.unlink()
    assert (await api.list(attempt_id, task_id)).items[0].result.task_number == 1
    with pytest.raises(AppError, match="AI_TASK1_IMAGE_INVALID"):
        await api.create(attempt_id, task_id, force=True)
