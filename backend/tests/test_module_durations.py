from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Test as DomainTest
from app.models import TestVersion as DomainVersion
from app.models.enums import ModuleType, VersionStatus
from app.schemas.content import ModuleCreate, ModuleUpdate
from app.schemas.draft_import import DraftImportManifest
from app.services.draft_import import DraftImportService
from app.services.reading import ReadingService
from app.services.tests import TestService as LifecycleService


@pytest.mark.integration
async def test_module_creation_defaults_and_edit_preserve_seconds(db_session: AsyncSession) -> None:
    test = DomainTest(title="Fictional module duration test")
    version = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(version)
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
    version_id = version.id
    service = ReadingService(db_session)
    modules = []
    for kind, expected in (
        (ModuleType.READING, 3600),
        (ModuleType.LISTENING, 1800),
        (ModuleType.WRITING, 3600),
    ):
        created = await service.create_module(version_id, ModuleCreate(module_type=kind))
        assert created.recommended_duration_seconds == expected
        modules.append(created)
        await db_session.rollback()

    reading = modules[0]
    saved = await service.update_module(
        reading.id,
        ModuleUpdate(expected_revision=reading.revision, recommended_duration_seconds=3300),
    )
    assert saved.recommended_duration_seconds == 3300
    assert saved.revision == reading.revision + 1
    assert [item.revision for item in saved.passages] == []
    await db_session.rollback()
    with pytest.raises(AppError) as caught:
        await service.update_module(
            reading.id,
            ModuleUpdate(expected_revision=reading.revision, recommended_duration_seconds=3600),
        )
    assert caught.value.code == "DRAFT_REVISION_CONFLICT"
    await db_session.rollback()

    version_detail = await LifecycleService(db_session).get_version(version_id)
    assert [item.recommended_duration_seconds for item in version_detail.modules] == [
        3300,
        1800,
        3600,
    ]


@pytest.mark.integration
async def test_draft_import_defaults_missing_duration_and_preserves_explicit_value(
    db_session: AsyncSession,
) -> None:
    manifest = DraftImportManifest.model_validate(
        {
            "format": "ielts-draft-import-v1",
            "title": "Fictional imported durations",
            "modules": [
                {"type": "READING", "passages": []},
                {"type": "LISTENING", "sections": [], "recommended_duration_seconds": 2100},
                {"type": "WRITING", "tasks": []},
            ],
        }
    )
    imported = await DraftImportService(db_session).import_manifest(manifest, Path.cwd())
    builder = await ReadingService(db_session).builder_version(imported.version_id)
    assert [item.recommended_duration_seconds for item in builder.modules] == [
        3600,
        2100,
        3600,
    ]


@pytest.mark.integration
async def test_missing_duration_is_validation_warning_not_publish_error(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Fictional legacy module")
    version = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(version)
    from app.models import TestModule as DomainModule

    version.modules.append(DomainModule(module_type=ModuleType.READING, order_index=0))
    async with db_session.begin():
        db_session.add(test)
    validation = await LifecycleService(db_session).validate(version.id)
    assert any(
        issue.message == "Reading recommended duration is missing." for issue in validation.warnings
    )
    assert not any("recommended duration" in issue.message for issue in validation.errors)
