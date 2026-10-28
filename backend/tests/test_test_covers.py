import base64
import hashlib
import io
import json
import zipfile
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import select
from starlette.datastructures import Headers

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models import Test as DomainTest
from app.models import TestCover as CoverRecord
from app.models import TestVersion as VersionRecord
from app.models import User
from app.models.enums import TestOrigin as Origin
from app.models.enums import UserRole, VersionStatus
from app.services.test_covers import TestCoverService as CoverService
from app.services.transfer import TransferService

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg=="
)


JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQgJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAACAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q=="
)
WEBP = base64.b64decode("UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoCAAIAAUAmJaQAA3AA/vz0AAA=")


def upload(data=PNG, name="cover.png", mime="image/png"):
    return UploadFile(file=io.BytesIO(data), filename=name, headers=Headers({"content-type": mime}))


async def create_test(session, *, owner=None, origin=Origin.ADMIN, status=VersionStatus.DRAFT):
    from datetime import UTC, datetime

    async with session.begin():
        test = DomainTest(
            title=f"Fictional cover {uuid4()}",
            owner_user_id=owner,
            origin=origin,
            cover_image=None,
            versions=[
                VersionRecord(
                    version_number=1,
                    status=status,
                    published_at=datetime.now(UTC) if status == VersionStatus.PUBLISHED else None,
                )
            ],
        )
        session.add(test)
        await session.flush()
        return test.id


async def create_user(session, role):
    async with session.begin():
        user = User(
            email=f"{uuid4()}@example.com",
            display_name="Fictional",
            role=role,
            is_active=True,
            email_verified=True,
        )
        session.add(user)
        await session.flush()
        return User(id=user.id, role=user.role, is_active=True)


async def test_upload_replace_remove_and_version_unchanged(db_session, tmp_path):
    actor = db_session.info["current_user_identity"]
    settings = Settings(storage_root=tmp_path / "store")
    test_id = await create_test(db_session, owner=actor.id)
    service = CoverService(db_session, actor, settings)
    first = await service.upload(test_id, upload())
    row = await db_session.scalar(select(CoverRecord).where(CoverRecord.id == first.id))
    path = settings.resolved_storage_root / row.relative_path
    assert path.read_bytes() == PNG
    await db_session.rollback()
    second = await service.upload(test_id, upload(name="other.png"))
    assert second.id != first.id
    row = await db_session.scalar(select(CoverRecord).where(CoverRecord.id == second.id))
    new_path = settings.resolved_storage_root / row.relative_path
    assert new_path.read_bytes() == PNG
    await db_session.rollback()
    assert not path.exists()
    await service.remove(test_id)
    assert not new_path.exists()
    versions = list(
        await db_session.scalars(select(VersionRecord).where(VersionRecord.test_id == test_id))
    )
    assert len(versions) == 1 and versions[0].status == VersionStatus.DRAFT
    await db_session.rollback()
    await service.remove(test_id)


async def test_upload_rejects_invalid_and_oversized_content_preserving_cover(db_session, tmp_path):
    actor = db_session.info["current_user_identity"]
    settings = Settings(storage_root=tmp_path / "store", max_image_upload_mb=1)
    test_id = await create_test(db_session, owner=actor.id)
    service = CoverService(db_session, actor, settings)
    cover = await service.upload(test_id, upload())
    for bad in (
        upload(b"not png"),
        upload(PNG, "cover.svg", "image/svg+xml"),
        upload(PNG + b"x" * 1048576),
    ):
        with pytest.raises(AppError):
            await service.upload(test_id, bad)
    rows = list(await db_session.scalars(select(CoverRecord).where(CoverRecord.test_id == test_id)))
    assert len(rows) == 1 and rows[0].id == cover.id
    assert len(list((settings.resolved_storage_root / "images").iterdir())) == 1


async def test_teacher_ownership_student_and_private_cover_access(db_session, tmp_path):
    teacher = await create_user(db_session, UserRole.TEACHER)
    other = await create_user(db_session, UserRole.TEACHER)
    student = await create_user(db_session, UserRole.USER)
    test_id = await create_test(db_session, owner=teacher.id, origin=Origin.TEACHER)
    settings = Settings(storage_root=tmp_path / "store")
    cover = await CoverService(db_session, teacher, settings).upload(test_id, upload())
    for actor in (other, student):
        with pytest.raises(AppError) as error:
            await CoverService(db_session, actor, settings).upload(test_id, upload())
        assert error.value.status_code == 403
        with pytest.raises(AppError) as error:
            await CoverService(db_session, actor, settings).read(test_id, cover.id)
        assert error.value.status_code == 404
        await db_session.rollback()
    assert (
        await CoverService(db_session, teacher, settings).read(test_id, cover.id)
    ).id == cover.id


async def test_cover_v2_round_trip_remaps_and_restores_to_another_root(db_session, tmp_path):
    actor = db_session.info["current_user_identity"]
    source = Settings(storage_root=tmp_path / "source")
    destination = Settings(storage_root=tmp_path / "destination")
    test_id = await create_test(db_session, owner=actor.id)
    cover = await CoverService(db_session, actor, source).upload(test_id, upload())
    archive = tmp_path / "export.zip"
    service = TransferService(db_session, source, actor)
    await service.export([test_id], archive)
    await db_session.rollback()
    with zipfile.ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["schema_version"] == 2
        entry = manifest["covers"][0]
        assert entry["source_test_id"] == str(test_id)
        assert entry["sha256"] == hashlib.sha256(PNG).hexdigest()
        assert bundle.read(entry["path"]) == PNG
    staging = tmp_path / "staging"
    staging.mkdir()
    importer = TransferService(db_session, destination, actor)
    package = importer.validate_archive(archive, staging)
    result = await importer.import_package(package)
    imported_id = result.imported_tests[0].test_id
    stored = await db_session.scalar(select(CoverRecord).where(CoverRecord.test_id == imported_id))
    assert stored.id != cover.id and imported_id != test_id
    assert (destination.resolved_storage_root / stored.relative_path).read_bytes() == PNG
    assert result.asset_count == 1


def test_v2_manifest_rejects_corrupted_missing_and_unreferenced_covers(tmp_path):
    from datetime import UTC, datetime

    from app.schemas.transfer import ManifestCover, ManifestTest, PortableTest, TransferManifest

    test_id, cover_id = uuid4(), uuid4()
    test = PortableTest(id=test_id, title="Fictional", versions=[], cover_id=cover_id)
    cover = ManifestCover(
        source_id=cover_id,
        source_test_id=test_id,
        path="assets/cover.png",
        mime_type="image/png",
        original_filename="cover.png",
        size=len(PNG),
        sha256=hashlib.sha256(PNG).hexdigest(),
    )
    manifest = TransferManifest(
        schema_version=2,
        exported_at=datetime.now(UTC),
        tests=[ManifestTest(source_id=test_id, path="tests/test.json", title=test.title)],
        covers=[cover],
    )
    settings = Settings(storage_root=tmp_path / "storage")
    service = TransferService.__new__(TransferService)
    service.settings = settings
    for mode in ("checksum", "missing", "unreferenced"):
        path = tmp_path / f"{mode}.zip"
        payload = test.model_copy(update={"cover_id": None}) if mode == "unreferenced" else test
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("manifest.json", manifest.model_dump_json())
            bundle.writestr("tests/test.json", payload.model_dump_json())
            if mode != "missing":
                bundle.writestr("assets/cover.png", b"invalid" if mode == "checksum" else PNG)
        staging = tmp_path / mode
        staging.mkdir()
        with pytest.raises(AppError):
            service.validate_archive(path, staging)


async def test_public_cover_access_tracks_approval_revocation_and_archive(db_session, tmp_path):
    from datetime import UTC, datetime

    from app.models import TestVersionModeration
    from app.models.enums import ModerationScope, ModerationStatus
    from app.services.tests import TestService

    admin = db_session.info["current_user_identity"]
    teacher = await create_user(db_session, UserRole.TEACHER)
    student = await create_user(db_session, UserRole.USER)
    test_id = await create_test(db_session, owner=teacher.id, origin=Origin.TEACHER)
    settings = Settings(storage_root=tmp_path / "store")
    cover = await CoverService(db_session, teacher, settings).upload(test_id, upload())
    async with db_session.begin():
        version = await db_session.scalar(
            select(VersionRecord).where(VersionRecord.test_id == test_id)
        )
        version.status = VersionStatus.PUBLISHED
        version.published_at = datetime.now(UTC)
        version_id = version.id
    with pytest.raises(AppError) as error:
        await CoverService(db_session, student, settings).read(test_id, cover.id)
    assert error.value.status_code == 404
    await db_session.rollback()
    async with db_session.begin():
        approval = TestVersionModeration(
            test_version_id=version_id,
            scope=ModerationScope.PUBLIC,
            status=ModerationStatus.APPROVED,
            submitted_by_user_id=teacher.id,
        )
        db_session.add(approval)
        await db_session.flush()
        approval_id = approval.id
    assert (
        await CoverService(db_session, student, settings).read(test_id, cover.id)
    ).id == cover.id
    await db_session.rollback()
    public = await TestService(db_session, student).list_summaries(public_only=True)
    matching = next(item for item in public if item.id == test_id)
    assert matching.cover_image.id == cover.id
    assert "relative_path" not in matching.model_dump_json()
    await db_session.rollback()
    async with db_session.begin():
        record = await db_session.get(DomainTest, test_id)
        record.archived_at = datetime.now(UTC)
    with pytest.raises(AppError):
        await CoverService(db_session, student, settings).read(test_id, cover.id)
    await db_session.rollback()
    async with db_session.begin():
        record = await db_session.get(DomainTest, test_id)
        record.archived_at = None
    async with db_session.begin():
        approval = await db_session.get(TestVersionModeration, approval_id)
        approval.status = ModerationStatus.REVOKED
    with pytest.raises(AppError):
        await CoverService(db_session, student, settings).read(test_id, cover.id)
    await db_session.rollback()
    assert (await CoverService(db_session, admin, settings).read(test_id, cover.id)).id == cover.id


async def test_failed_replacement_retains_existing_cover(db_session, tmp_path, monkeypatch):
    actor = db_session.info["current_user_identity"]
    settings = Settings(storage_root=tmp_path / "store")
    test_id = await create_test(db_session, owner=actor.id)
    service = CoverService(db_session, actor, settings)
    old = await service.upload(test_id, upload())
    original_flush = db_session.flush

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(db_session, "flush", fail_flush)
    with pytest.raises(RuntimeError):
        await service.upload(test_id, upload())
    monkeypatch.setattr(db_session, "flush", original_flush)
    stored = await db_session.scalar(select(CoverRecord).where(CoverRecord.test_id == test_id))
    assert stored.id == old.id
    assert (settings.resolved_storage_root / stored.relative_path).read_bytes() == PNG
    assert len(list((settings.resolved_storage_root / "images").iterdir())) == 1


def test_cover_validation_bounds_decoded_dimensions():
    from app.services.cover_validation import validate_cover_image

    validate_cover_image("image/png", PNG)
    import zlib

    huge = PNG[:16] + (16000).to_bytes(4, "big") + (16000).to_bytes(4, "big") + PNG[24:]
    huge = huge[:29] + zlib.crc32(huge[12:29]).to_bytes(4, "big") + huge[33:]
    with pytest.raises(ValueError, match="dimensions"):
        validate_cover_image("image/png", huge)
    with pytest.raises(ValueError):
        validate_cover_image("image/png", PNG[:12])


@pytest.mark.parametrize(
    "data,name,mime",
    [
        (PNG, "cover.png", "image/png"),
        (JPEG, "cover.jpg", "image/jpeg"),
        (WEBP, "cover.webp", "image/webp"),
    ],
)
async def test_supported_cover_formats(db_session, tmp_path, data, name, mime):
    actor = db_session.info["current_user_identity"]
    settings = Settings(storage_root=tmp_path / "store")
    test_id = await create_test(db_session, owner=actor.id)
    cover = await CoverService(db_session, actor, settings).upload(
        test_id, upload(data, name, mime)
    )
    row = await db_session.scalar(select(CoverRecord).where(CoverRecord.id == cover.id))
    assert cover.mime_type == mime
    assert (settings.resolved_storage_root / row.relative_path).read_bytes() == data


async def test_clone_archive_restore_and_test_deletion_preserve_or_clean_cover(
    db_session, tmp_path, monkeypatch
):
    from app.schemas.tests import VersionCreate
    from app.services.tests import TestService

    actor = db_session.info["current_user_identity"]
    settings = Settings(storage_root=tmp_path / "store")
    monkeypatch.setattr("app.services.tests.get_settings", lambda: settings)
    test_id = await create_test(db_session, owner=actor.id, status=VersionStatus.PUBLISHED)
    service = CoverService(db_session, actor, settings)
    cover = await service.upload(test_id, upload())
    row = await db_session.scalar(select(CoverRecord).where(CoverRecord.id == cover.id))
    path = settings.resolved_storage_root / row.relative_path
    source = await db_session.scalar(select(VersionRecord).where(VersionRecord.test_id == test_id))
    source_id = source.id
    await db_session.rollback()
    lifecycle = TestService(db_session, actor)
    draft = await lifecycle.create_version(test_id, VersionCreate(source_version_id=source_id))
    draft_id = draft.id
    await db_session.rollback()
    await lifecycle.delete_draft(test_id, draft_id)
    assert path.exists()
    outcome = await lifecycle.delete_test(test_id)
    assert outcome.action == "ARCHIVED" and path.exists()
    await lifecycle.restore_test(test_id)
    assert path.exists()
    await lifecycle.delete_test(test_id)
    await lifecycle.permanently_delete_test(test_id)
    assert not path.exists()


async def test_cover_http_endpoints_return_safe_metadata_and_content(
    db_session, tmp_path, monkeypatch
):
    import httpx

    from app.api.dependencies import get_current_user
    from app.core.database import get_session
    from app.main import app

    actor = db_session.info["current_user_identity"]
    settings = Settings(storage_root=tmp_path / "store")
    monkeypatch.setattr("app.api.v1.tests.get_settings", lambda: settings)
    test_id = await create_test(db_session, owner=actor.id)
    previous_auth = app.dependency_overrides.get(get_current_user)
    previous_session = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/v1/tests/{test_id}/cover", files={"file": ("cover.png", PNG, "image/png")}
            )
            assert response.status_code == 200
            cover = response.json()
            assert set(cover) == {"id", "mime_type", "content_url"}
            assert "path" not in response.text
            response = await client.get(f"/api/v1/tests/{test_id}")
            assert response.status_code == 200 and response.json()["cover_image"] == cover
            await db_session.rollback()
            response = await client.get(f"/api/v1{cover['content_url']}")
            assert response.status_code == 200 and response.content == PNG
            assert response.headers["content-type"].startswith("image/png")
            assert response.headers["x-content-type-options"] == "nosniff"
            await db_session.rollback()
            response = await client.delete(f"/api/v1/tests/{test_id}/cover")
            assert response.status_code == 204
    finally:
        if previous_auth is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_auth
        if previous_session is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous_session


async def test_pending_teacher_review_blocks_cover_changes(db_session, tmp_path):
    from app.models import TestVersionModeration
    from app.models.enums import ModerationScope, ModerationStatus

    teacher = await create_user(db_session, UserRole.TEACHER)
    test_id = await create_test(db_session, owner=teacher.id, origin=Origin.TEACHER)
    settings = Settings(storage_root=tmp_path / "store")
    service = CoverService(db_session, teacher, settings)
    cover = await service.upload(test_id, upload())
    async with db_session.begin():
        version_id = await db_session.scalar(
            select(VersionRecord.id).where(VersionRecord.test_id == test_id)
        )
        db_session.add(
            TestVersionModeration(
                test_version_id=version_id,
                scope=ModerationScope.PUBLIC,
                status=ModerationStatus.PENDING,
                submitted_by_user_id=teacher.id,
            )
        )
    with pytest.raises(AppError) as error:
        await service.upload(test_id, upload())
    assert error.value.code == "VERSION_MODERATION_PENDING"
    row = await db_session.scalar(select(CoverRecord).where(CoverRecord.test_id == test_id))
    assert row.id == cover.id


async def test_import_failure_compensates_cover_file(db_session, tmp_path, monkeypatch):
    actor = db_session.info["current_user_identity"]
    source = Settings(storage_root=tmp_path / "source")
    target = Settings(storage_root=tmp_path / "target")
    test_id = await create_test(db_session, owner=actor.id)
    await CoverService(db_session, actor, source).upload(test_id, upload())
    archive = tmp_path / "export.zip"
    await TransferService(db_session, source, actor).export([test_id], archive)
    await db_session.rollback()
    stage = tmp_path / "stage"
    stage.mkdir()
    importer = TransferService(db_session, target, actor)
    package = importer.validate_archive(archive, stage)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(db_session, "flush", fail_flush)
    with pytest.raises(RuntimeError):
        await importer.import_package(package)
    assert not list(target.resolved_storage_root.rglob("*.png"))


async def test_two_covers_round_trip_and_repeat_import_independently(db_session, tmp_path):
    actor = db_session.info["current_user_identity"]
    source = Settings(storage_root=tmp_path / "source")
    target = Settings(storage_root=tmp_path / "target")
    test_ids = [await create_test(db_session, owner=actor.id) for _ in range(2)]
    original_covers = [
        await CoverService(db_session, actor, source).upload(test_id, upload())
        for test_id in test_ids
    ]
    archive = tmp_path / "export.zip"
    await TransferService(db_session, source, actor).export(test_ids, archive)
    await db_session.rollback()
    stage = tmp_path / "stage"
    stage.mkdir()
    importer = TransferService(db_session, target, actor)
    package = importer.validate_archive(archive, stage)
    assert len(package.manifest.covers) == 2
    first = await importer.import_package(package)
    second = await importer.import_package(package)
    ids = [item.test_id for item in first.imported_tests + second.imported_tests]
    rows = list(await db_session.scalars(select(CoverRecord).where(CoverRecord.test_id.in_(ids))))
    assert len(rows) == 4
    assert len({row.id for row in rows}) == 4
    assert not {row.id for row in rows}.intersection(cover.id for cover in original_covers)
    assert all(
        (target.resolved_storage_root / row.relative_path).read_bytes() == PNG for row in rows
    )


async def test_lost_cover_commit_acknowledgement_keeps_new_and_cleans_old(
    db_session, tmp_path, monkeypatch
):
    actor = db_session.info["current_user_identity"]
    settings = Settings(storage_root=tmp_path / "store")
    test_id = await create_test(db_session, owner=actor.id)
    service = CoverService(db_session, actor, settings)
    old = await service.upload(test_id, upload())
    original_begin = db_session.begin
    calls = 0

    class LostAcknowledgement:
        async def __aenter__(self):
            self.tx = original_begin()
            return await self.tx.__aenter__()

        async def __aexit__(self, *args):
            nonlocal calls
            await self.tx.__aexit__(*args)
            calls += 1
            if calls == 2:
                raise RuntimeError("injected lost commit acknowledgement")

    monkeypatch.setattr(db_session, "begin", LostAcknowledgement)
    with pytest.raises(RuntimeError):
        await service.upload(test_id, upload())
    row = await db_session.scalar(select(CoverRecord).where(CoverRecord.test_id == test_id))
    assert row.id != old.id
    assert (settings.resolved_storage_root / row.relative_path).read_bytes() == PNG
    assert len(list((settings.resolved_storage_root / "images").iterdir())) == 1


async def test_cancellation_during_cover_validation_cleans_staged_file(
    db_session, tmp_path, monkeypatch
):
    import asyncio
    import threading

    from app.services.cover_validation import validate_cover_image

    actor = db_session.info["current_user_identity"]
    settings = Settings(storage_root=tmp_path / "store")
    test_id = await create_test(db_session, owner=actor.id)
    service = CoverService(db_session, actor, settings)
    entered, release = threading.Event(), threading.Event()

    def slow_validation(mime, data):
        entered.set()
        release.wait(5)
        validate_cover_image(mime, data)

    monkeypatch.setattr("app.services.test_covers.validate_cover_image", slow_validation)
    task = asyncio.create_task(service.upload(test_id, upload()))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not list(settings.resolved_storage_root.rglob("*.png"))
    assert (
        await db_session.scalar(select(CoverRecord.id).where(CoverRecord.test_id == test_id))
        is None
    )
