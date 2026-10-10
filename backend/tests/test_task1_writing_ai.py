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
from test_chart_cross_check import LINE, FakeSpecialist
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
from app.services.writing_ai import input_fingerprint


async def test_failed_early_claim_extraction_keeps_warning_in_partial_analysis(
    db_session, task1, settings
):
    class Provider(Task1FakeProvider):
        async def complete(self, messages, schema, *, options=None):
            if "claims" in schema["properties"]:
                from app.providers.writing_llm.base import ProviderFailure

                raise ProviderFailure("AI_PROVIDER_TIMEOUT")
            return await super().complete(messages, schema, options=options)

    api = service(db_session, settings)
    created = await api.create(task1[0], task1[1], force=False)
    runner = worker(db_session, settings, Provider(fail_trait="Task Achievement"))
    await runner.execute(created.run_id)
    run, events = await api.snapshot(created.run_id, 0)
    assert run.status == WritingAIRunStatus.FAILED and "ta" in run.failures
    assert "CLAIM_EXTRACTION_FAILED" in run.task1_analysis.warnings
    failed = [event for event in events if event.event_type == "claim_extraction.failed"]
    assert (
        len(failed) == 1 and "CLAIM_EXTRACTION_FAILED" in failed[0].payload.task1_analysis.warnings
    )
    assert set(run.progress) == {"cc", "lr", "gra"}


@pytest.mark.parametrize(
    "error", [None, "CHART_SPECIALIST_UNAVAILABLE", "CHART_SPECIALIST_PARSE_FAILED"]
)
async def test_chart_cross_check_restores_diagnostics_sse_and_preserves_human_scores(
    db_session, task1, writing, settings, error
):
    attempt_id, task_id, _, _ = task1
    task2_id = writing[2]
    settings.ai_writing_chart_specialist_enabled = True
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    specialist = FakeSpecialist(LINE, error)
    worker_instance = worker(db_session, settings, Task1FakeProvider())
    worker_instance.chart_derenderer = specialist
    await worker_instance.execute(created.run_id)
    run, events = await api.snapshot(created.run_id, 0)
    assert run.status == "COMPLETED" and run.task1_analysis.cross_check is not None
    assert len(specialist.calls) == 1
    assert run.task1_analysis.cross_check.status == (
        "COMPLETED"
        if error is None
        else "PARSE_FAILED"
        if error.endswith("PARSE_FAILED")
        else "UNAVAILABLE"
    )
    types = [event.event_type for event in events]
    assert "chart_specialist.started" in types
    assert (
        "chart_reconciliation.completed" if error is None else "chart_specialist.failed"
    ) in types
    assert (await api.create(attempt_id, task_id, force=False)).cache_hit
    # Enabling the specialist creates a distinct chart cache, with old runs readable.
    settings.ai_writing_chart_specialist_enabled = False
    assert not (await api.create(attempt_id, task_id, force=False)).cache_hit
    async with db_session.begin():
        human1 = await db_session.scalar(
            select(AttemptWritingScore).where(
                AttemptWritingScore.attempt_id == attempt_id,
                AttemptWritingScore.writing_task_id == task_id,
            )
        )
        human2 = await db_session.scalar(
            select(AttemptWritingScore).where(
                AttemptWritingScore.attempt_id == attempt_id,
                AttemptWritingScore.writing_task_id == task2_id,
            )
        )
        attempt = await db_session.get(Attempt, attempt_id)
    assert human1.ta == 6 and human2.ta == 7 and attempt.band_score == 7


async def test_task2_ignores_enabled_specialist(db_session, writing, settings):
    from test_writing_ai import FakeProvider

    attempt_id, _, task2_id = writing
    settings.ai_writing_chart_specialist_enabled = True
    specialist = FakeSpecialist()
    api = service(db_session, settings)
    created = await api.create(attempt_id, task2_id, force=False)
    instance = worker(db_session, settings, FakeProvider())
    instance.chart_derenderer = specialist
    await instance.execute(created.run_id)
    run, events = await api.snapshot(created.run_id, 0)
    assert run.status == "COMPLETED" and len(run.progress) == 4
    assert not specialist.calls and not any(
        event.event_type.startswith("chart_") for event in events
    )


pytestmark = pytest.mark.integration


async def test_primary_validation_diagnostics_persist_without_leaking_into_api(
    db_session, task1, settings
):
    attempt_id, task_id, _, _ = task1
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    await worker(db_session, settings, Task1FakeProvider(malformed_grounding=2)).execute(
        created.run_id
    )
    run, events = await api.snapshot(created.run_id, 0)
    async with db_session.begin():
        stored = await db_session.get(WritingAIGradingRun, run.id)
        diagnostics = stored.usage_json["diagnostics"]
    assert diagnostics == [
        {
            "stage": "visual_grounding",
            "criterion": "ta",
            "reason": "SCHEMA_VALIDATION",
            "attempt": attempt,
            "finish_reason": "stop",
            "validation_issues": [{"field": "reference", "validation_type": "missing"}],
        }
        for attempt in (1, 2)
    ]
    assert run.task1_analysis.confidence == "UNUSABLE" and set(run.progress) == {"cc", "lr", "gra"}
    public = run.model_dump_json() + "".join(event.model_dump_json() for event in events)
    assert "validation_issues" not in public and "diagnostics" not in public


@pytest.mark.parametrize("stage", ["reconciliation", "derived_facts"])
async def test_unexpected_optional_failure_persists_safe_analysis_and_completed_ta(
    db_session, task1, settings, monkeypatch, stage
):
    def fail(*_):
        raise RuntimeError("PRIVATE RAW DATA")

    settings.ai_writing_chart_specialist_enabled = stage == "reconciliation"
    monkeypatch.setattr(
        "app.services.task1_chart_cross_check.reconcile_chart"
        if stage == "reconciliation"
        else "app.services.task1_writing.derive_facts",
        fail,
    )
    attempt_id, task_id, _, _ = task1
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    instance = worker(db_session, settings, Task1FakeProvider())
    instance.chart_derenderer = FakeSpecialist()
    await instance.execute(created.run_id)
    run, events = await api.snapshot(created.run_id, 0)
    assert run.status == "COMPLETED" and set(run.progress) == {"ta", "cc", "lr", "gra"}
    assert run.task1_analysis.confidence == "HIGH" and run.task1_analysis.reference is not None
    if stage == "reconciliation":
        assert run.task1_analysis.cross_check.status == "RECONCILIATION_FAILED"
        assert run.task1_analysis.derived_facts
    else:
        assert "DERIVED_FACTS_FAILED" in run.task1_analysis.warnings
        fallback = next(event for event in events if event.event_type == "derived_facts.failed")
        assert fallback.payload.stage == "derived_facts"
    assert not any(event.event_type == "visual_grounding.failed" for event in events)
    assert (await api.get(run.id)).task1_analysis == run.task1_analysis
    assert (await api.create(attempt_id, task_id, force=False)).cache_hit
    assert "PRIVATE RAW DATA" not in run.model_dump_json() + str(events)


@pytest.mark.parametrize(
    "old_version",
    [
        "mts-task1-visual-v1",
        "mts-task1-visual-v2",
        "mts-task1-visual-v3",
        "mts-task1-visual-v4",
        "mts-task1-visual-v5",
    ],
)
async def test_old_task1_prompt_cache_remains_readable_but_is_not_reused(
    db_session, task1, settings, old_version
):
    attempt_id, task_id, _, _ = task1
    api = service(db_session, settings)
    created = await api.create(attempt_id, task_id, force=False)
    await worker(db_session, settings, Task1FakeProvider()).execute(created.run_id)
    old_result = (await api.get(created.run_id)).result
    async with db_session.begin():
        request = await api.input(attempt_id, task_id)
        row = await db_session.get(WritingAIGradingRun, created.run_id)
        row.prompt_version = old_version
        row.input_fingerprint = input_fingerprint(
            request, row.prompt_version, row.provider, row.model
        )
    upgraded = await api.create(attempt_id, task_id, force=False)
    assert not upgraded.cache_hit and upgraded.run_id != created.run_id
    assert (await api.get(upgraded.run_id)).prompt_version == "mts-task1-visual-v6"
    assert (await api.get(created.run_id)).result == old_result


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
    assert restored == run and all(event.sequence > cursor for event in replay)
    assert any(
        event.event_type == "criterion.started" and event.payload.criterion == "ta"
        for event in replay
    )
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
