"""Listening range persistence and eligibility using fictional content and real DDL."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from test_focused_attempts import content, request

from app.core.exceptions import AppError
from app.models import Asset, ListeningPart
from app.models import TestModule as ModuleRecord
from app.models import TestVersion as VersionRecord
from app.models.enums import AssetType, ModuleType, VersionStatus
from app.schemas.content import ListeningModuleAudioWrite, ListeningPartUpdate
from app.schemas.listening import ListeningAudioRange
from app.schemas.transfer import PortableListeningPart
from app.services.attempts import AttemptService
from app.services.listening import ListeningService
from app.services.test_sessions import TestSessionService as SessionService


@pytest.mark.parametrize(
    "start,end", [(None, 60), (0, None), (-1, 10), (20, 20), (30, 20), (1.5, 20)]
)
def test_range_schema_rejects_invalid_pairs(start, end):
    with pytest.raises(ValidationError):
        ListeningAudioRange(audio_start_seconds=start, audio_end_seconds=end)


def test_legacy_portable_part_needs_no_range():
    part = PortableListeningPart(id=uuid4(), title="Fictional section", order_index=0)
    assert part.audio_start_seconds is None and part.audio_end_seconds is None


@pytest.mark.integration
async def test_actual_migration_keeps_legacy_parts_and_checks_both_nulls(db_session):
    _, units = await content(db_session)
    part_id = units[ModuleType.LISTENING][0].id
    path = Path(__file__).parents[1] / "alembic/versions/20261010_0022_listening_audio_ranges.py"
    spec = importlib.util.spec_from_file_location("listening_range_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    assert revision.down_revision == "20261010_0021"

    def migrate(sync_session):
        with Operations.context(MigrationContext.configure(sync_session.connection())):
            revision.downgrade()
            # The old row stays in place as the actual migration adds nullable fields.
            revision.upgrade()

    async with db_session.begin():
        await db_session.run_sync(migrate)
        row = (
            await db_session.execute(
                text(
                    "SELECT audio_start_seconds, audio_end_seconds FROM listening_parts WHERE id=:id"
                ),
                {"id": part_id},
            )
        ).one()
        assert tuple(row) == (None, None)
        for start, end in [(None, 30), (0, None), (-1, 30), (30, 30), (40, 30)]:
            with pytest.raises(IntegrityError):
                async with db_session.begin_nested():
                    await db_session.execute(
                        text(
                            "UPDATE listening_parts SET audio_start_seconds=:start, audio_end_seconds=:end WHERE id=:id"
                        ),
                        {"id": part_id, "start": start, "end": end},
                    )
        await db_session.execute(
            text(
                "UPDATE listening_parts SET audio_start_seconds=0, audio_end_seconds=30 WHERE id=:id"
            ),
            {"id": part_id},
        )


@pytest.mark.integration
async def test_legacy_title_update_preserves_range_and_published_parts_are_immutable(db_session):
    version, units = await content(db_session, status=VersionStatus.DRAFT)
    part_id = units[ModuleType.LISTENING][1].id
    service = ListeningService(db_session)
    saved = await service.update_part(
        part_id,
        ListeningPartUpdate(title="Fictional renamed section", order_index=1, expected_revision=1),
    )
    assert (saved.revision, saved.audio_start_seconds, saved.audio_end_seconds) == (2, 60, 120)
    await db_session.rollback()
    async with db_session.begin():
        await db_session.execute(
            update(VersionRecord)
            .where(VersionRecord.id == version.id)
            .values(status=VersionStatus.PUBLISHED)
        )
    with pytest.raises(AppError) as immutable:
        await service.update_part(
            part_id,
            ListeningPartUpdate(
                title="Forbidden",
                order_index=1,
                expected_revision=2,
                audio_start_seconds=None,
                audio_end_seconds=None,
            ),
        )
    assert immutable.value.code == "TEST_VERSION_IMMUTABLE"


@pytest.mark.integration
async def test_revision_edits_and_audio_reset_are_atomic(db_session):
    version, units = await content(db_session, status=VersionStatus.DRAFT)
    ids = [item.id for item in units[ModuleType.LISTENING]]
    async with db_session.begin():
        module = await db_session.scalar(
            select(ModuleRecord).where(
                ModuleRecord.test_version_id == version.id,
                ModuleRecord.module_type == ModuleType.LISTENING,
            )
        )
        module_id, old_audio = module.id, module.audio_asset_id
        replacement = Asset(
            id=uuid4(),
            test_version_id=version.id,
            asset_type=AssetType.LISTENING_AUDIO,
            relative_path="audio/fictional-replacement.mp3",
            mime_type="audio/mpeg",
            original_name="fictional-replacement.mp3",
            file_size=10,
        )
        db_session.add(replacement)
        replacement_id = replacement.id
    service = ListeningService(db_session)
    edited = await service.update_part(
        ids[0],
        ListeningPartUpdate(
            title="Edited fictional section",
            order_index=0,
            audio_start_seconds=468,
            audio_end_seconds=931,
            expected_revision=1,
        ),
    )
    assert (edited.revision, edited.audio_start_seconds, edited.audio_end_seconds) == (2, 468, 931)
    await db_session.rollback()
    same = await service.attach_audio(
        module_id, ListeningModuleAudioWrite(expected_revision=1, asset_id=old_audio)
    )
    assert [
        (p.revision, p.audio_start_seconds, p.audio_end_seconds) for p in same.listening_parts
    ] == [(2, 468, 931), (1, 60, 120)]
    await db_session.rollback()
    with pytest.raises(AppError) as failure:
        await service.attach_audio(
            module_id, ListeningModuleAudioWrite(expected_revision=2, asset_id=uuid4())
        )
    assert failure.value.code == "INVALID_AUDIO_ASSET"
    replaced = await service.attach_audio(
        module_id, ListeningModuleAudioWrite(expected_revision=2, asset_id=replacement_id)
    )
    assert replaced.revision == 3 and replaced.audio_asset.id == replacement_id
    assert [
        (p.revision, p.audio_start_seconds, p.audio_end_seconds) for p in replaced.listening_parts
    ] == [(3, None, None), (2, None, None)]
    await db_session.rollback()
    with pytest.raises(AppError) as stale:
        await service.update_part(
            ids[0],
            ListeningPartUpdate(
                title="Stale",
                order_index=0,
                audio_start_seconds=468,
                audio_end_seconds=931,
                expected_revision=2,
            ),
        )
    assert stale.value.code == "DRAFT_REVISION_CONFLICT"
    edited = await service.update_part(
        ids[0],
        ListeningPartUpdate(
            title="Edited",
            order_index=0,
            audio_start_seconds=0,
            audio_end_seconds=30,
            expected_revision=3,
        ),
    )
    await db_session.rollback()
    removed = await service.attach_audio(
        module_id, ListeningModuleAudioWrite(expected_revision=3, asset_id=None)
    )
    assert removed.audio_asset is None
    assert [
        (p.revision, p.audio_start_seconds, p.audio_end_seconds) for p in removed.listening_parts
    ] == [(5, None, None), (2, None, None)]


@pytest.mark.integration
@pytest.mark.parametrize("missing", ["none", "range", "audio"])
async def test_focused_optional_audio_preserves_full_listening_and_mock(db_session, missing):
    version, units = await content(db_session)
    target = units[ModuleType.LISTENING][0]
    async with db_session.begin():
        if missing == "range":
            await db_session.execute(
                update(ListeningPart).values(audio_start_seconds=None, audio_end_seconds=None)
            )
        elif missing == "audio":
            await db_session.execute(
                update(ModuleRecord)
                .where(ModuleRecord.test_version_id == version.id)
                .values(audio_asset_id=None)
            )
    # Model a fresh request after direct fixture writes, including the audio relationship.
    db_session.expire_all()
    service = AttemptService(db_session)
    focused = await service.start(request(version, ModuleType.LISTENING, target))
    assert focused.scope == "FOCUSED_UNIT" and focused.focused_unit.id == target.id
    exam = await service.exam(focused.attempt_id)
    assert [part.id for part in exam.listening_parts] == [target.id]
    assert len(exam.listening_parts[0].question_groups[0].questions) == 2
    assert (exam.listening_audio_asset is None) == (missing == "audio")
    expected_range = (None, None) if missing == "range" else (0, 60)
    assert (
        exam.listening_parts[0].audio_start_seconds,
        exam.listening_parts[0].audio_end_seconds,
    ) == expected_range
    await db_session.rollback()
    await service.submit(focused.attempt_id)
    review = await service.listening_review(focused.attempt_id)
    assert [part.id for part in review.parts] == [target.id]
    assert (review.audio_asset is None) == (missing == "audio")
    assert review.review.attempt.raw_score == 0 and review.review.attempt.max_score == 2
    assert review.review.attempt.band_score is None
    await db_session.rollback()
    _, foreign_units = await content(db_session)
    with pytest.raises(AppError) as foreign:
        await service.start(
            request(version, ModuleType.LISTENING, foreign_units[ModuleType.LISTENING][0])
        )
    assert foreign.value.code == "FOCUSED_UNIT_INVALID"
    full = await service.start(request(version, ModuleType.LISTENING))
    exam = await service.exam(full.attempt_id)
    assert len(exam.listening_parts) == 2 and exam.attempt.scope == "FULL_MODULE"
    await db_session.rollback()
    mock = await SessionService(db_session).start(version.id)
    assert mock.current_attempt.module == ModuleType.LISTENING


@pytest.mark.integration
async def test_focused_exam_and_review_preserve_selected_range(db_session):
    version, units = await content(db_session)
    target = units[ModuleType.LISTENING][1]
    service = AttemptService(db_session)
    run = await service.start(request(version, ModuleType.LISTENING, target, duration=600))
    exam = await service.exam(run.attempt_id)
    assert len(exam.listening_parts) == 1 and exam.listening_audio_asset is not None
    assert (
        exam.listening_parts[0].audio_start_seconds,
        exam.listening_parts[0].audio_end_seconds,
    ) == (60, 120)
    await db_session.rollback()
    await service.submit(run.attempt_id)
    review = await service.listening_review(run.attempt_id)
    assert len(review.parts) == 1 and review.parts[0].id == target.id
    assert (review.parts[0].audio_start_seconds, review.parts[0].audio_end_seconds) == (60, 120)
    assert review.review.attempt.band_score is None and review.review.attempt.max_score == 2
