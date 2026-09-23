from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Asset, ListeningPart, Question, QuestionGroup, WritingTask
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AssetType, ModuleType, VersionStatus
from app.schemas.content import QuestionGroupWrite
from app.schemas.tests import VersionCreate
from app.services.listening import ListeningService
from app.services.tests import TestService as VersionService
from app.storage import LocalAssetStorage


def _settings(storage_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        resolved_storage_root=storage_root,
        max_image_upload_mb=10,
        max_audio_upload_mb=100,
    )


def _stored_paths(storage_root: Path) -> set[str]:
    return {
        path.relative_to(storage_root).as_posix()
        for path in storage_root.rglob("*")
        if path.is_file()
    }


def _asset(
    version: DomainVersion,
    storage_root: Path,
    asset_type: AssetType,
    relative_path: str,
    content: bytes,
) -> Asset:
    path = storage_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    mime_type = "audio/mpeg" if asset_type == AssetType.LISTENING_AUDIO else "image/png"
    asset = Asset(
        id=uuid4(),
        asset_type=asset_type,
        relative_path=relative_path,
        mime_type=mime_type,
        original_name=path.name,
        file_size=len(content),
    )
    version.assets.append(asset)
    return asset


def _source_with_all_asset_references(
    storage_root: Path,
) -> tuple[DomainTest, DomainVersion, dict[str, Asset]]:
    test = DomainTest(title="Asset clone invariant")
    source = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    test.versions.append(source)
    assets = {
        "audio": _asset(
            source,
            storage_root,
            AssetType.LISTENING_AUDIO,
            f"audio/{uuid4()}.mp3",
            b"fictional audio",
        ),
        "question_image": _asset(
            source,
            storage_root,
            AssetType.QUESTION_IMAGE,
            f"images/{uuid4()}.png",
            b"fictional map",
        ),
        "writing_image": _asset(
            source,
            storage_root,
            AssetType.WRITING_TASK_IMAGE,
            f"images/{uuid4()}.png",
            b"fictional chart",
        ),
    }

    listening = DomainModule(
        module_type=ModuleType.LISTENING,
        order_index=0,
        audio_asset=assets["audio"],
    )
    part = ListeningPart(title="Section 1", order_index=0)
    option_ids = [str(uuid4()), str(uuid4())]
    group = QuestionGroup(
        question_type="map_labelling",
        instruction="Choose a letter.",
        config={
            "options": [
                {"id": option_ids[0], "label": "A", "text": "Entrance"},
                {"id": option_ids[1], "label": "B", "text": "Exit"},
            ]
        },
        order_index=0,
        image_asset=assets["question_image"],
    )
    group.questions.append(
        Question(
            number=1,
            prompt="Scarecrow",
            config={},
            answer_key={"kind": "SINGLE_OPTION", "value": option_ids[0]},
            order_index=0,
        )
    )
    part.question_groups.append(group)
    listening.listening_parts.append(part)
    listening.question_groups.append(group)

    writing = DomainModule(module_type=ModuleType.WRITING, order_index=1)
    writing.writing_tasks.append(
        WritingTask(
            task_number=1,
            prompt="Describe the fictional chart.",
            image_asset=assets["writing_image"],
            minimum_recommended_words=150,
            recommended_duration_seconds=1200,
            order_index=0,
        )
    )
    source.modules.extend([listening, writing])
    return test, source, assets


@pytest.mark.integration
async def test_version_clone_owns_independent_copies_of_every_referenced_asset(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.tests.get_settings", lambda: _settings(tmp_path))
    test, source, source_assets = _source_with_all_asset_references(tmp_path)
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
    source_id = source.id
    source_paths = {name: asset.relative_path for name, asset in source_assets.items()}

    clone = await VersionService(db_session).create_version(
        test.id, VersionCreate(source_version_id=source_id)
    )
    listening = next(
        module for module in clone.modules if module.module_type == ModuleType.LISTENING
    )
    writing = next(module for module in clone.modules if module.module_type == ModuleType.WRITING)
    cloned_group = listening.question_groups[0]
    cloned_task = writing.writing_tasks[0]
    referenced = [listening.audio_asset, cloned_group.image_asset, cloned_task.image_asset]

    assert all(asset is not None for asset in referenced)
    assert all(asset.test_version_id == clone.id for asset in referenced if asset is not None)
    assert {asset.id for asset in referenced if asset is not None}.isdisjoint(
        {asset.id for asset in source_assets.values()}
    )
    assert {asset.relative_path for asset in referenced if asset is not None}.isdisjoint(
        set(source_paths.values())
    )
    for asset in referenced:
        assert asset is not None
        source_asset = source_assets[
            "audio"
            if asset.asset_type == AssetType.LISTENING_AUDIO
            else "question_image"
            if asset.asset_type == AssetType.QUESTION_IMAGE
            else "writing_image"
        ]
        assert (tmp_path / asset.relative_path).read_bytes() == (
            tmp_path / source_asset.relative_path
        ).read_bytes()

    cloned_paths = [asset.relative_path for asset in referenced if asset is not None]
    test_id = test.id
    clone_id = clone.id
    await db_session.rollback()
    await VersionService(db_session).delete_draft(test_id, clone_id)

    assert all((tmp_path / path).is_file() for path in source_paths.values())
    assert all(not (tmp_path / path).exists() for path in cloned_paths)


@pytest.mark.integration
async def test_source_asset_cleanup_does_not_remove_cloned_files(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.tests.get_settings", lambda: _settings(tmp_path))
    test, source, source_assets = _source_with_all_asset_references(tmp_path)
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
    source_id = source.id
    source_module_ids = [module.id for module in source.modules]
    source_group_id = source.modules[0].question_groups[0].id
    source_task_id = source.modules[1].writing_tasks[0].id
    source_asset_ids = [asset.id for asset in source_assets.values()]
    source_paths = [asset.relative_path for asset in source_assets.values()]

    clone = await VersionService(db_session).create_version(
        test.id, VersionCreate(source_version_id=source_id)
    )
    listening = next(
        module for module in clone.modules if module.module_type == ModuleType.LISTENING
    )
    writing = next(module for module in clone.modules if module.module_type == ModuleType.WRITING)
    cloned_assets = [
        listening.audio_asset,
        listening.question_groups[0].image_asset,
        writing.writing_tasks[0].image_asset,
    ]
    assert all(asset is not None for asset in cloned_assets)
    cloned_asset_ids = [asset.id for asset in cloned_assets if asset is not None]
    cloned_paths = [asset.relative_path for asset in cloned_assets if asset is not None]
    clone_id = clone.id
    await db_session.rollback()

    deleted_paths: list[str] = []
    async with db_session.begin():
        listening_record = await db_session.get(DomainModule, source_module_ids[0])
        source_group = await db_session.get(QuestionGroup, source_group_id)
        source_task = await db_session.get(WritingTask, source_task_id)
        assert listening_record is not None
        assert source_group is not None
        assert source_task is not None
        listening_record.audio_asset_id = None
        source_group.image_asset_id = None
        source_task.image_asset_id = None
        await db_session.flush()
        service = VersionService(db_session)
        for asset_id in source_asset_ids:
            path = await service.cleanup_asset_if_unreferenced(asset_id)
            if path:
                deleted_paths.append(path)
    VersionService._delete_files(deleted_paths)

    assert set(deleted_paths) == set(source_paths)
    assert all(not (tmp_path / path).exists() for path in source_paths)
    assert all((tmp_path / path).is_file() for path in cloned_paths)
    for asset_id in cloned_asset_ids:
        asset = await db_session.get(Asset, asset_id)
        assert asset is not None
        assert asset.test_version_id == clone_id


@pytest.mark.integration
async def test_version_clone_rolls_back_database_and_files_when_an_asset_copy_fails(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.tests.get_settings", lambda: _settings(tmp_path))
    test, source, _ = _source_with_all_asset_references(tmp_path)
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
    test_id = test.id
    source_id = source.id
    before = _stored_paths(tmp_path)
    original_store_file = LocalAssetStorage.store_file
    calls = 0

    def fail_second_copy(self: LocalAssetStorage, **kwargs: object):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("fictional copy failure")
        return original_store_file(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(LocalAssetStorage, "store_file", fail_second_copy)

    with pytest.raises(OSError, match="fictional copy failure"):
        await VersionService(db_session).create_version(
            test.id, VersionCreate(source_version_id=source_id)
        )

    drafts = list(
        await db_session.scalars(
            select(DomainVersion).where(
                DomainVersion.test_id == test_id,
                DomainVersion.status == VersionStatus.DRAFT,
            )
        )
    )
    after = _stored_paths(tmp_path)
    assert drafts == []
    assert after == before


@pytest.mark.integration
async def test_legacy_cloned_listening_group_repairs_only_its_inherited_image(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.tests.get_settings", lambda: _settings(tmp_path))
    test = DomainTest(title="Legacy inherited map")
    source = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    draft = DomainVersion(version_number=2, status=VersionStatus.DRAFT)
    test.versions.extend([source, draft])
    inherited = _asset(
        source,
        tmp_path,
        AssetType.QUESTION_IMAGE,
        f"images/{uuid4()}.png",
        b"legacy inherited map",
    )
    source_listening = DomainModule(module_type=ModuleType.LISTENING, order_index=0)
    source_part = ListeningPart(title="Section 1", order_index=0)
    source_group = QuestionGroup(
        question_type="map_labelling",
        instruction="Choose a letter.",
        config={"options": []},
        order_index=0,
        image_asset=inherited,
    )
    source_part.question_groups.append(source_group)
    source_listening.listening_parts.append(source_part)
    source_listening.question_groups.append(source_group)
    source.modules.append(source_listening)
    listening = DomainModule(module_type=ModuleType.LISTENING, order_index=0)
    part = ListeningPart(title="Section 1", order_index=0)
    question_id = uuid4()
    option_ids = [str(uuid4()), str(uuid4())]
    group = QuestionGroup(
        question_type="map_labelling",
        instruction="Choose a letter.",
        config={
            "options": [
                {"id": option_ids[0], "label": "A", "text": "Entrance"},
                {"id": option_ids[1], "label": "B", "text": "Exit"},
            ],
            "markers": [
                {
                    "id": str(uuid4()),
                    "question_id": str(question_id),
                    "x": 0.5,
                    "y": 0.5,
                }
            ],
        },
        order_index=0,
        image_asset_id=inherited.id,
    )
    group.questions.append(
        Question(
            id=question_id,
            number=1,
            prompt="Scarecrow",
            config={},
            answer_key={"kind": "SINGLE_OPTION", "value": option_ids[0]},
            order_index=0,
        )
    )
    part.question_groups.append(group)
    listening.listening_parts.append(part)
    listening.question_groups.append(group)
    draft.modules.append(listening)
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()

    service = ListeningService(db_session)
    group_id = group.id
    draft_id = draft.id
    inherited_id = inherited.id
    persisted = await service.get_group(group_id)
    body = QuestionGroupWrite.model_validate(persisted.model_dump(mode="json"))
    await db_session.rollback()
    broken = await VersionService(db_session).get_version(draft_id)
    assert not VersionService.validate_version(broken).valid
    await db_session.rollback()
    updated = await service.update_group(group_id, body)

    assert updated.image_asset_id != inherited_id
    assert updated.config == {"options": persisted.config["options"]}
    assert [question.id for question in updated.questions] == [question_id]
    assert updated.questions[0].answer_key["value"] == option_ids[0]
    repaired = await db_session.get(Asset, updated.image_asset_id)
    assert repaired is not None
    assert repaired.test_version_id == draft_id
    source_asset = await db_session.get(Asset, inherited_id)
    assert source_asset is not None
    assert repaired.relative_path != source_asset.relative_path
    assert (tmp_path / repaired.relative_path).read_bytes() == b"legacy inherited map"
    assert (tmp_path / source_asset.relative_path).read_bytes() == b"legacy inherited map"

    second_body = QuestionGroupWrite.model_validate(updated.model_dump(mode="json"))
    second_body.questions[0].prompt = "Edited scarecrow"
    await db_session.rollback()
    second = await service.update_group(group_id, second_body)
    assert second.image_asset_id == repaired.id
    assert second.questions[0].id == question_id
    assert second.questions[0].prompt == "Edited scarecrow"
    await db_session.rollback()
    repaired_version = await VersionService(db_session).get_version(draft_id)
    assert not any(
        "owned by this test version" in issue.message
        for issue in VersionService.validate_version(repaired_version).errors
    )


@pytest.mark.integration
async def test_legacy_repair_rejects_an_unrelated_cross_version_image(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.tests.get_settings", lambda: _settings(tmp_path))
    test = DomainTest(title="Strict inherited image repair")
    source = DomainVersion(version_number=1, status=VersionStatus.PUBLISHED)
    draft = DomainVersion(version_number=2, status=VersionStatus.DRAFT)
    test.versions.extend([source, draft])
    inherited = _asset(
        source,
        tmp_path,
        AssetType.QUESTION_IMAGE,
        f"images/{uuid4()}.png",
        b"inherited map",
    )
    unrelated = _asset(
        source,
        tmp_path,
        AssetType.QUESTION_IMAGE,
        f"images/{uuid4()}.png",
        b"unrelated image",
    )
    listening = DomainModule(module_type=ModuleType.LISTENING, order_index=0)
    part = ListeningPart(title="Section 1", order_index=0)
    option_ids = [str(uuid4()), str(uuid4())]
    group = QuestionGroup(
        question_type="plan_labelling",
        instruction="Choose a letter.",
        config={
            "options": [
                {"id": option_ids[0], "label": "A", "text": "Entrance"},
                {"id": option_ids[1], "label": "B", "text": "Exit"},
            ]
        },
        order_index=0,
        image_asset_id=inherited.id,
    )
    group.questions.append(
        Question(
            number=1,
            prompt="Gate",
            config={},
            answer_key={"kind": "SINGLE_OPTION", "value": option_ids[0]},
            order_index=0,
        )
    )
    part.question_groups.append(group)
    listening.listening_parts.append(part)
    listening.question_groups.append(group)
    draft.modules.append(listening)
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()

    group_id = group.id
    inherited_id = inherited.id
    unrelated_id = unrelated.id
    persisted = await ListeningService(db_session).get_group(group_id)
    body = QuestionGroupWrite.model_validate(persisted.model_dump(mode="json"))
    body.image_asset_id = unrelated_id
    await db_session.rollback()

    with pytest.raises(AppError) as caught:
        await ListeningService(db_session).update_group(group_id, body)

    assert caught.value.code == "INVALID_IMAGE_ASSET"
    assert body.image_asset_id == unrelated_id
    assert await db_session.get(Asset, inherited_id) is not None
    assert await db_session.get(Asset, unrelated_id) is not None
