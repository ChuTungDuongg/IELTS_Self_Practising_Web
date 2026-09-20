from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Asset, AttemptEvent, WritingTask
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AssetType, EventType, ModuleType, TimerMode, VersionStatus
from app.schemas.attempts import AttemptCreate, TimerRequest
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
    )
    second = await service.save_writing_response(
        attempt_id,
        task_two_id,
        "A fictional second response.",
    )
    updated = await service.save_writing_response(
        attempt_id,
        task_one_id,
        "Updated response with four words.",
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
        await service.save_writing_response(objective_attempt_id, task_id, "No")
    assert objective_error.value.code == "WRITING_ATTEMPT_REQUIRED"

    with pytest.raises(AppError) as task_error:
        await service.save_writing_response(writing_attempt_id, other_task_id, "No")
    assert task_error.value.code == "INVALID_WRITING_TASK"

    await service.submit(writing_attempt_id)
    with pytest.raises(AppError) as finalized_error:
        await service.save_writing_response(writing_attempt_id, task_id, "Too late")
    assert finalized_error.value.code == "ATTEMPT_FINALIZED"
    assert other_version_id != version_id


@pytest.mark.integration
async def test_manual_writing_band_validation_and_history_visibility(
    db_session: AsyncSession,
) -> None:
    version_id, _, _, _ = await _persist_writing_test(db_session)
    objective_version_id = await _persist_objective_test(db_session)
    writing_attempt_id = await _start(db_session, version_id, ModuleType.WRITING)
    objective_attempt_id = await _start(db_session, objective_version_id, ModuleType.READING)
    service = AttemptService(db_session)

    with pytest.raises(AppError) as active_error:
        await service.grade_writing(writing_attempt_id, Decimal("7.0"))
    assert active_error.value.code == "ATTEMPT_NOT_FINALIZED"

    await service.submit(writing_attempt_id)
    await service.submit(objective_attempt_id)

    for half_step in range(19):
        band = Decimal(half_step) / Decimal(2)
        response = await service.grade_writing(writing_attempt_id, band)
        assert response.band_score == float(band)
        assert response.raw_score is None
        assert response.max_score is None

    for invalid in (Decimal("-0.5"), Decimal("7.25"), Decimal("9.5")):
        with pytest.raises(AppError) as invalid_error:
            await service.grade_writing(writing_attempt_id, invalid)
        assert invalid_error.value.code == "INVALID_WRITING_BAND"

    with pytest.raises(AppError) as objective_error:
        await service.grade_writing(objective_attempt_id, Decimal("7.0"))
    assert objective_error.value.code == "WRITING_ATTEMPT_REQUIRED"

    saved = await service.grade_writing(writing_attempt_id, Decimal("7.5"))
    review = await service.writing_review(writing_attempt_id)
    history = await service.history()
    assert saved.band_score == 7.5
    assert review.review.attempt.band_score == 7.5
    item = next(row for row in history.items if row.attempt_id == writing_attempt_id)
    assert item.band_score == 7.5
