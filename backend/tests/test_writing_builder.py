from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Asset, WritingTask
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AssetType, ModuleType, VersionStatus
from app.schemas.content import ModuleCreate, WritingTaskWrite
from app.schemas.tests import VersionCreate
from app.services.reading import ReadingService
from app.services.tests import TestService as ContentTestService
from app.services.writing import WritingService


async def _persist_version(
    session: AsyncSession, *, status: VersionStatus = VersionStatus.DRAFT
) -> tuple[DomainTest, DomainVersion]:
    test = DomainTest(title="Fictional Writing builder")
    version = DomainVersion(version_number=1, status=status)
    test.versions.append(version)
    async with session.begin():
        session.add(test)
        await session.flush()
    return test, version


async def _initialize_writing(session: AsyncSession, version_id):
    module = await ReadingService(session).create_module(
        version_id,
        ModuleCreate(
            module_type=ModuleType.WRITING,
            title="Writing",
            recommended_duration_seconds=3600,
        ),
    )
    await session.rollback()
    return module


def _asset(
    version_id,
    *,
    asset_type: AssetType = AssetType.WRITING_TASK_IMAGE,
    mime_type: str = "image/png",
) -> Asset:
    identifier = uuid4()
    return Asset(
        id=identifier,
        test_version_id=version_id,
        asset_type=asset_type,
        relative_path=f"images/{identifier}.png",
        mime_type=mime_type,
        original_name="fictional.png",
        file_size=10,
    )


@pytest.mark.integration
async def test_writing_module_initializes_two_fixed_tasks_atomically(
    db_session: AsyncSession,
) -> None:
    _, version = await _persist_version(db_session)

    module = await _initialize_writing(db_session, version.id)

    assert module.module_type == ModuleType.WRITING
    assert [task.task_number for task in module.writing_tasks] == [1, 2]
    assert [task.order_index for task in module.writing_tasks] == [0, 1]
    assert [task.minimum_recommended_words for task in module.writing_tasks] == [150, 250]
    assert [task.recommended_duration_seconds for task in module.writing_tasks] == [1200, 2400]
    assert all(task.image_asset is None for task in module.writing_tasks)


@pytest.mark.integration
async def test_task_one_update_accepts_owned_writing_image_and_removal(
    db_session: AsyncSession,
) -> None:
    _, version = await _persist_version(db_session)
    version_id = version.id
    module = await _initialize_writing(db_session, version_id)
    image = _asset(version_id)
    async with db_session.begin():
        db_session.add(image)
        await db_session.flush()

    updated = await WritingService(db_session).update_task(
        module.writing_tasks[0].id,
        WritingTaskWrite(
            prompt="Describe the fictional chart.",
            image_asset_id=image.id,
            minimum_recommended_words=175,
            recommended_duration_seconds=1500,
        ),
    )

    assert updated.prompt == "Describe the fictional chart."
    assert updated.image_asset is not None
    assert updated.image_asset.id == image.id
    assert updated.minimum_recommended_words == 175
    assert updated.recommended_duration_seconds == 1500
    await db_session.rollback()

    removed = await WritingService(db_session).update_task(
        updated.id,
        WritingTaskWrite(
            prompt=updated.prompt,
            image_asset_id=None,
            minimum_recommended_words=updated.minimum_recommended_words,
            recommended_duration_seconds=updated.recommended_duration_seconds,
        ),
    )
    assert removed.image_asset is None
    assert await db_session.get(Asset, image.id) is None


@pytest.mark.integration
@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("task_two", "WRITING_TASK_IMAGE_NOT_ALLOWED"),
        ("wrong_type", "INVALID_WRITING_TASK_IMAGE"),
        ("wrong_version", "INVALID_WRITING_TASK_IMAGE"),
        ("wrong_mime", "INVALID_WRITING_TASK_IMAGE"),
    ],
)
async def test_writing_task_image_rules_are_enforced_server_side(
    db_session: AsyncSession, case: str, expected_code: str
) -> None:
    _, version = await _persist_version(db_session)
    version_id = version.id
    module = await _initialize_writing(db_session, version_id)
    other_test = DomainTest(title="Other fictional version")
    other_version = DomainVersion(id=uuid4(), version_number=1, status=VersionStatus.DRAFT)
    other_test.versions.append(other_version)
    image = _asset(
        other_version.id if case == "wrong_version" else version_id,
        asset_type=AssetType.QUESTION_IMAGE
        if case == "wrong_type"
        else AssetType.WRITING_TASK_IMAGE,
        mime_type="application/octet-stream" if case == "wrong_mime" else "image/png",
    )
    async with db_session.begin():
        db_session.add_all([other_test, image])
        await db_session.flush()
    task = module.writing_tasks[1] if case == "task_two" else module.writing_tasks[0]

    with pytest.raises(AppError) as caught:
        await WritingService(db_session).update_task(
            task.id,
            WritingTaskWrite(
                prompt="Fictional prompt",
                image_asset_id=image.id,
                minimum_recommended_words=150,
                recommended_duration_seconds=1200,
            ),
        )

    assert caught.value.code == expected_code


@pytest.mark.integration
async def test_published_writing_task_is_immutable(db_session: AsyncSession) -> None:
    _, version = await _persist_version(db_session, status=VersionStatus.PUBLISHED)
    module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
    task = WritingTask(task_number=1, prompt="Frozen", order_index=0)
    async with db_session.begin():
        module.test_version_id = version.id
        module.writing_tasks.append(task)
        db_session.add(module)
        await db_session.flush()

    with pytest.raises(AppError) as caught:
        await WritingService(db_session).update_task(
            task.id,
            WritingTaskWrite(
                prompt="Changed",
                minimum_recommended_words=150,
                recommended_duration_seconds=1200,
            ),
        )

    assert caught.value.code == "TEST_VERSION_IMMUTABLE"


@pytest.mark.integration
async def test_writing_module_delete_removes_tasks(db_session: AsyncSession) -> None:
    _, version = await _persist_version(db_session)
    module = await _initialize_writing(db_session, version.id)
    task_ids = [task.id for task in module.writing_tasks]

    await ContentTestService(db_session).delete_module(module.id)

    for task_id in task_ids:
        assert await db_session.get(WritingTask, task_id) is None


@pytest.mark.integration
async def test_clone_preserves_writing_tasks_and_shared_image_reference(
    db_session: AsyncSession,
) -> None:
    test, source = await _persist_version(db_session, status=VersionStatus.PUBLISHED)
    image = _asset(source.id)
    module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
    task_one = WritingTask(
        task_number=1,
        prompt="Describe fictional data.",
        image_asset_id=image.id,
        minimum_recommended_words=150,
        recommended_duration_seconds=1200,
        order_index=0,
    )
    task_two = WritingTask(
        task_number=2,
        prompt="Discuss a fictional proposition.",
        minimum_recommended_words=250,
        recommended_duration_seconds=2400,
        order_index=1,
    )
    async with db_session.begin():
        db_session.add(image)
        module.test_version_id = source.id
        module.writing_tasks.extend([task_one, task_two])
        db_session.add(module)
        await db_session.flush()

    clone = await ContentTestService(db_session).create_version(
        test.id, VersionCreate(source_version_id=source.id)
    )
    builder = await ReadingService(db_session).builder_version(clone.id)
    writing = next(item for item in builder.modules if item.module_type == ModuleType.WRITING)

    assert [task.prompt for task in writing.writing_tasks] == [
        "Describe fictional data.",
        "Discuss a fictional proposition.",
    ]
    assert writing.writing_tasks[0].image_asset_id == image.id
    assert writing.writing_tasks[0].image_asset is not None
    assert writing.writing_tasks[0].image_asset.id == image.id


def test_partial_writing_module_is_valid_with_readiness_warning() -> None:
    version = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
    module.writing_tasks.append(
        WritingTask(
            task_number=1,
            prompt="Describe fictional data.",
            minimum_recommended_words=150,
            recommended_duration_seconds=1200,
            order_index=0,
        )
    )
    version.modules.append(module)

    result = ContentTestService.validate_version(version)

    assert result.valid
    assert any(issue.path == "writing.tasks" for issue in result.warnings)


def test_structurally_invalid_writing_tasks_block_publish() -> None:
    version = DomainVersion(id=uuid4(), version_number=1, status=VersionStatus.DRAFT)
    module = DomainModule(id=uuid4(), module_type=ModuleType.WRITING, order_index=0)
    image = _asset(version.id)
    invalid_task = WritingTask(
        task_number=2,
        prompt="Invalid image task",
        image_asset=image,
        minimum_recommended_words=250,
        recommended_duration_seconds=2400,
        order_index=0,
    )
    module.writing_tasks.append(invalid_task)
    version.modules.append(module)

    result = ContentTestService.validate_version(version)

    assert not result.valid
    assert any(issue.path.startswith("writing.tasks") for issue in result.errors)
