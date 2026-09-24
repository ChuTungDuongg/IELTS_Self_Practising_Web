from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import AppError
from app.main import app
from app.models import Asset, AttemptEvent, WritingTask
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AssetType, EventType, ModuleType, TimerMode, VersionStatus
from app.schemas.attempts import AttemptCreate, TimerRequest, WritingTaskScoreUpdate
from app.services.attempts import AttemptService


async def _persist_writing_test(
    session: AsyncSession, *, title: str = "Fictional Writing attempt"
) -> tuple[UUID, UUID, UUID, UUID]:
    test = DomainTest(title=title)
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
    image = Asset(
        id=uuid4(),
        asset_type=AssetType.WRITING_TASK_IMAGE,
        relative_path=f"images/{uuid4()}.png",
        mime_type="image/png",
        original_name="fictional.png",
        file_size=10,
    )
    task_one = WritingTask(
        task_number=1,
        prompt="Describe the fictional chart.",
        image_asset=image,
        minimum_recommended_words=150,
        recommended_duration_seconds=1200,
        order_index=0,
    )
    task_two = WritingTask(
        task_number=2,
        prompt="Discuss the fictional proposition.",
        minimum_recommended_words=250,
        recommended_duration_seconds=2400,
        order_index=1,
    )
    test.versions.append(version)
    version.assets.append(image)
    version.modules.append(module)
    module.writing_tasks.extend([task_one, task_two])
    async with session.begin():
        session.add(test)
        await session.flush()
        result = (version.id, task_one.id, task_two.id, image.id)
    return result


async def _persist_objective_test(session: AsyncSession) -> UUID:
    test = DomainTest(title="Fictional objective attempt")
    version = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    version.modules.append(DomainModule(module_type=ModuleType.READING, order_index=0))
    test.versions.append(version)
    async with session.begin():
        session.add(test)
        await session.flush()
        version_id = version.id
    return version_id


async def _start(session: AsyncSession, version_id: UUID, module: ModuleType) -> UUID:
    response = await AttemptService(session).start(
        AttemptCreate(
            test_version_id=version_id,
            module=module,
            timer=TimerRequest(mode=TimerMode.COUNT_UP),
        )
    )
    return response.attempt_id


@pytest.mark.integration
async def test_writing_response_upsert_resume_submit_and_review(
    db_session: AsyncSession,
) -> None:
    version_id, task_one_id, task_two_id, image_id = await _persist_writing_test(db_session)
    attempt_id = await _start(db_session, version_id, ModuleType.WRITING)
    service = AttemptService(db_session)

    initial_exam = await service.exam(attempt_id)
    assert [task.content for task in initial_exam.writing_tasks] == ["", ""]
    assert [task.word_count for task in initial_exam.writing_tasks] == [0, 0]
    assert initial_exam.writing_tasks[0].image_asset is not None
    assert initial_exam.writing_tasks[0].image_asset.id == image_id
    await db_session.rollback()

    first = await service.save_writing_response(
        attempt_id,
        task_one_id,
        "It’s a city's plan for Đà Nẵng.",
        0,
    )
    second = await service.save_writing_response(
        attempt_id,
        task_two_id,
        "A fictional second response.",
        0,
    )
    updated = await service.save_writing_response(
        attempt_id,
        task_one_id,
        "Updated response with four words.",
        1,
    )

    assert first.word_count == 7
    assert second.word_count == 4
    assert updated.word_count == 5

    resumed = await service.exam(attempt_id)
    assert [task.content for task in resumed.writing_tasks] == [
        "Updated response with four words.",
        "A fictional second response.",
    ]
    assert [task.word_count for task in resumed.writing_tasks] == [5, 4]
    await db_session.rollback()

    submitted = await service.submit(attempt_id)
    assert submitted.raw_score is None
    assert submitted.max_score is None
    assert submitted.band_score is None

    review = await service.writing_review(attempt_id)
    assert [task.writing_task_id for task in review.tasks] == [task_one_id, task_two_id]
    assert [task.content for task in review.tasks] == [
        "Updated response with four words.",
        "A fictional second response.",
    ]
    assert review.tasks[0].image_asset is not None
    assert review.tasks[0].image_asset.id == image_id
    events = list(
        await db_session.scalars(
            select(AttemptEvent)
            .where(
                AttemptEvent.attempt_id == attempt_id,
                AttemptEvent.event_type == EventType.WRITING_UPDATED,
            )
            .order_by(AttemptEvent.created_at)
        )
    )
    assert len(events) == 3
    assert events[-1].event_metadata == {"writing_task_id": str(task_one_id)}


@pytest.mark.integration
async def test_writing_response_rejects_wrong_attempt_task_and_finalized_state(
    db_session: AsyncSession,
) -> None:
    version_id, task_id, _, _ = await _persist_writing_test(db_session)
    other_version_id, other_task_id, _, _ = await _persist_writing_test(
        db_session, title="Other fictional Writing attempt"
    )
    objective_version_id = await _persist_objective_test(db_session)
    writing_attempt_id = await _start(db_session, version_id, ModuleType.WRITING)
    objective_attempt_id = await _start(db_session, objective_version_id, ModuleType.READING)
    service = AttemptService(db_session)

    with pytest.raises(AppError) as objective_error:
        await service.save_writing_response(objective_attempt_id, task_id, "No", 0)
    assert objective_error.value.code == "WRITING_ATTEMPT_REQUIRED"

    with pytest.raises(AppError) as task_error:
        await service.save_writing_response(writing_attempt_id, other_task_id, "No", 0)
    assert task_error.value.code == "INVALID_WRITING_TASK"

    await service.submit(writing_attempt_id)
    with pytest.raises(AppError) as finalized_error:
        await service.save_writing_response(writing_attempt_id, task_id, "Too late", 0)
    assert finalized_error.value.code == "ATTEMPT_FINALIZED"
    assert other_version_id != version_id


@pytest.mark.integration
async def test_writing_criterion_grading_recomputes_band_and_history(
    db_session: AsyncSession,
) -> None:
    version_id, task_one_id, task_two_id, _ = await _persist_writing_test(db_session)
    other_version_id, other_task_id, _, _ = await _persist_writing_test(
        db_session, title="Other Writing grading"
    )
    objective_version_id = await _persist_objective_test(db_session)
    writing_attempt_id = await _start(db_session, version_id, ModuleType.WRITING)
    objective_attempt_id = await _start(db_session, objective_version_id, ModuleType.READING)
    service = AttemptService(db_session)
    task_one_scores = WritingTaskScoreUpdate(
        ta=Decimal("7.0"),
        cc=Decimal("6.5"),
        lr=Decimal("7.0"),
        gra=Decimal("6.5"),
        ta_feedback="  Strong task coverage.  ",
        cc_feedback="Clear progression.",
    )
    task_two_scores = WritingTaskScoreUpdate(
        ta=Decimal("7.0"),
        cc=Decimal("7.0"),
        lr=Decimal("7.0"),
        gra=Decimal("7.0"),
    )

    with pytest.raises(AppError) as active_error:
        await service.grade_writing_task(writing_attempt_id, task_one_id, task_one_scores)
    assert active_error.value.code == "ATTEMPT_NOT_FINALIZED"

    await service.pause(writing_attempt_id)
    with pytest.raises(AppError) as paused_error:
        await service.grade_writing_task(writing_attempt_id, task_one_id, task_one_scores)
    assert paused_error.value.code == "ATTEMPT_NOT_FINALIZED"
    await service.resume(writing_attempt_id)
    await service.submit(writing_attempt_id)
    await service.submit(objective_attempt_id)

    with pytest.raises(AppError) as objective_error:
        await service.grade_writing_task(objective_attempt_id, task_one_id, task_one_scores)
    assert objective_error.value.code == "WRITING_ATTEMPT_REQUIRED"

    with pytest.raises(AppError) as ownership_error:
        await service.grade_writing_task(writing_attempt_id, other_task_id, task_one_scores)
    assert ownership_error.value.code == "INVALID_WRITING_TASK"
    assert other_version_id != version_id

    first = await service.grade_writing_task(writing_attempt_id, task_one_id, task_one_scores)
    assert first.task1_overall == 6.75
    assert first.task2_overall is None
    assert first.weighted_overall is None
    assert first.band_score is None
    assert first.review.attempt.band_score is None

    completed = await service.grade_writing_task(writing_attempt_id, task_two_id, task_two_scores)
    assert completed.task1_overall == 6.75
    assert completed.task2_overall == 7.0
    assert completed.weighted_overall == pytest.approx(6.9166666667)
    assert completed.band_score == 7.0
    assert completed.review.attempt.raw_score is None
    assert completed.review.attempt.max_score is None
    assert completed.tasks[0].score is not None
    assert completed.tasks[0].score.ta == 7.0
    assert completed.tasks[0].score.ta_feedback == "Strong task coverage."
    assert completed.tasks[0].score.cc_feedback == "Clear progression."

    cleared = await service.grade_writing_task(
        writing_attempt_id,
        task_one_id,
        WritingTaskScoreUpdate(
            ta=Decimal("7.0"),
            cc=Decimal("6.5"),
            lr=Decimal("7.0"),
            gra=Decimal("6.5"),
            ta_feedback="   ",
        ),
    )
    assert cleared.tasks[0].score is not None
    assert cleared.tasks[0].score.ta_feedback is None
    assert cleared.tasks[0].score.cc_feedback == "Clear progression."

    updated = await service.grade_writing_task(
        writing_attempt_id,
        task_two_id,
        WritingTaskScoreUpdate(
            ta=Decimal("7.5"),
            cc=Decimal("7.5"),
            lr=Decimal("7.5"),
            gra=Decimal("7.5"),
            ta_feedback="   ",
        ),
    )
    assert updated.task2_overall == 7.5
    assert updated.weighted_overall == 7.25
    assert updated.band_score == 7.5
    assert updated.tasks[1].score is not None
    assert updated.tasks[1].score.ta_feedback is None

    history = await service.history()
    item = next(row for row in history.items if row.attempt_id == writing_attempt_id)
    assert item.band_score == 7.5


@pytest.mark.integration
async def test_writing_task_score_endpoint_returns_authoritative_summary(
    db_session: AsyncSession,
    authenticated_admin,
) -> None:
    version_id, task_one_id, _, _ = await _persist_writing_test(db_session)
    attempt_id = await _start(db_session, version_id, ModuleType.WRITING)
    await AttemptService(db_session).submit(attempt_id)

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                f"/api/v1/attempts/{attempt_id}/writing-scores/{task_one_id}",
                json={
                    "ta": 7.0,
                    "cc": 6.5,
                    "lr": 7.0,
                    "gra": 6.5,
                    "gra_feedback": "Accurate range.",
                },
            )
            invalid = await client.put(
                f"/api/v1/attempts/{attempt_id}/writing-scores/{task_one_id}",
                json={"ta": 7.25, "cc": 6.5, "lr": 7.0, "gra": 6.5},
            )
            oversized = await client.put(
                f"/api/v1/attempts/{attempt_id}/writing-scores/{task_one_id}",
                json={"ta": 7.0, "cc": 6.5, "lr": 7.0, "gra": 6.5, "ta_feedback": "x" * 4001},
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["task1_overall"] == 6.75
    assert payload["task2_overall"] is None
    assert payload["weighted_overall"] is None
    assert payload["band_score"] is None
    assert payload["tasks"][0]["score"] == {
        "ta": 7.0,
        "cc": 6.5,
        "lr": 7.0,
        "gra": 6.5,
        "overall": 6.75,
        "ta_feedback": None,
        "cc_feedback": None,
        "lr_feedback": None,
        "gra_feedback": "Accurate range.",
    }
    assert invalid.status_code == 422
    assert oversized.status_code == 422
