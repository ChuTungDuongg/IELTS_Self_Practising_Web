"""Real PostgreSQL snapshot/dump/recovery on explicitly disposable databases only."""

import asyncio
import os
import re
import subprocess
from io import BytesIO
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from test_speaking_transcript import completed, fake_decode
from test_storage_contract import FakeS3
from test_transfer import _portable_fixture

from app.core.config import Settings, get_settings
from app.models import TestCover as CoverRecord
from app.models import TestVersion as VersionRecord
from app.models import User
from app.models.classroom import Classroom
from app.models.classroom_classwork import ClassroomResource
from app.models.enums import UserRole, VersionStatus
from app.models.speaking import SpeakingMediaCleanup
from app.models.writing_benchmark import WritingBenchmarkSample
from app.services.speaking_audio import normalize_committed_take
from app.storage.migration import copy_keys, inventory_cleanup, inventory_references, reference_map
from app.storage.operations import StorageTarget, check_restore_database, database_id
from app.storage.recovery import (
    create_portable_backup,
    reconcile_restored_database,
    restore_objects,
)
from app.storage.s3 import S3CompatibleStorage
from testsupport.test_database import validate_test_database_url


@pytest_asyncio.fixture
async def recovery_databases():
    base = os.environ.get("P5_TEST_DATABASE_URL")
    container = os.environ.get("P5_TEST_CONTAINER", "")
    if not base or not re.fullmatch(r"bandpilot-p5-offline-test-[a-zA-Z0-9-]+", container):
        pytest.skip(
            "Set P5_TEST_DATABASE_URL and P5_TEST_CONTAINER to a disposable loopback PostgreSQL container"
        )
    parsed = validate_test_database_url(base, get_settings().database_url)
    # No normal development volumes may back this test container.
    checked = await asyncio.to_thread(
        subprocess.run,
        ["docker", "inspect", "--format", "{{json .Mounts}}", container],
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    assert all(mount["Type"] == "tmpfs" for mount in json.loads(checked.stdout))
    connection = await asyncpg.connect(base.replace("postgresql+asyncpg://", "postgresql://", 1))
    names = [f"ielts_p5_source_test_{uuid4().hex[:8]}", f"ielts_p5_restore_test_{uuid4().hex[:8]}"]
    try:
        await connection.execute(f'CREATE DATABASE "{names[0]}" TEMPLATE "{parsed.database}"')
        await connection.execute(f'CREATE DATABASE "{names[1]}"')
        source = str(parsed.set(database=names[0]).render_as_string(hide_password=False))
        destination = str(parsed.set(database=names[1]).render_as_string(hide_password=False))

        def tool(operation, url, path, *, snapshot=None):
            database = unquote(urlsplit(url).path.lstrip("/"))
            assert database in names
            args = [
                "docker",
                "exec",
                "-i",
                container,
                operation,
                "--username=p5tester",
                f"--dbname={database}",
            ]
            if operation == "pg_dump":
                args += ["--format=custom", f"--snapshot={snapshot}"]
                with path.open("wb") as output:
                    result = subprocess.run(
                        args, stdout=output, stderr=subprocess.PIPE, check=False
                    )
            else:
                assert operation == "pg_restore"
                args += ["--no-owner", "--no-acl", "--single-transaction", "--exit-on-error"]
                with path.open("rb") as source_file:
                    result = subprocess.run(
                        args,
                        stdin=source_file,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
            assert result.returncode == 0, f"Offline {operation} failed"

        yield source, destination, tool
    finally:
        # Only UUID-named databases created by this fixture, on the verified test service.
        for name in reversed(names):
            await connection.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await connection.close()


@pytest.mark.parametrize("backend", ["local", "s3"])
async def test_real_snapshot_dump_recovery_all_reference_families(
    recovery_databases, tmp_path, monkeypatch, backend
):
    source_url, target_url, tool = recovery_databases
    source_engine = create_async_engine(source_url)
    settings = Settings(storage_root=tmp_path / "source")
    try:
        async with AsyncSession(source_engine, expire_on_commit=False) as session:
            admin = User(
                email=f"p5-{uuid4()}@example.com",
                display_name="Fictional operator",
                role=UserRole.ADMIN,
                is_active=True,
                email_verified=True,
            )
            async with session.begin():
                session.add(admin)
                await session.flush()
            session.info.update(current_user_id=admin.id, current_user_identity=admin)
            test, version, _ = await _portable_fixture(session, settings.resolved_storage_root)
            published_id = version.id
            _aid, response_id, media = await completed(session, settings.resolved_storage_root)
            await normalize_committed_take(
                session, response_id, settings, storage=media.storage, executor=fake_decode
            )
            await session.rollback()
            extras = {
                "images/p5-cover.png": b"fictional cover",
                "classroom-resources/p5.pdf": b"fictional worksheet",
                "benchmark/writing/task1/p5/chart.png": b"fictional benchmark",
            }
            for key, data in extras.items():
                media.storage.put_stream(
                    key, BytesIO(data), content_type="application/octet-stream", max_bytes=len(data)
                )
            async with session.begin():
                session.add(
                    CoverRecord(
                        test_id=test.id,
                        relative_path="images/p5-cover.png",
                        mime_type="image/png",
                        original_name="cover.png",
                        file_size=len(extras["images/p5-cover.png"]),
                    )
                )
                classroom = Classroom(teacher_id=admin.id, name="Fictional class")
                session.add(classroom)
                await session.flush()
                session.add(
                    ClassroomResource(
                        classroom_id=classroom.id,
                        title="Fictional resource",
                        kind="FILE",
                        storage_key="classroom-resources/p5.pdf",
                        original_filename="lesson.pdf",
                        media_type="application/pdf",
                        size_bytes=len(extras["classroom-resources/p5.pdf"]),
                    )
                )
                session.add(
                    WritingBenchmarkSample(
                        task_number=1,
                        sequence_number=1,
                        task1_image_key="benchmark/writing/task1/p5/chart.png",
                    )
                )
                session.add(
                    SpeakingMediaCleanup(storage_key="speaking-private/previous-orphan.webm")
                )
            references = await inventory_references(session)
            cleanup = await inventory_cleanup(session)
            assert {ref.category for ref in references} == {
                "test_asset",
                "test_cover",
                "classroom",
                "speaking_chunk",
                "speaking_normalized",
                "writing_benchmark",
            }
            assert cleanup == ["speaking-private/previous-orphan.webm"]
            assert all(key not in reference_map(references) for key in cleanup)
        source = media.storage
        if backend == "s3":
            remote = S3CompatibleStorage(client=FakeS3(), bucket="snapshot-source")
            rows = copy_keys(source, remote, reference_map(references), dry_run=False)
            assert all(row.status == "copied" for row in rows)
            source = remote
        path = await create_portable_backup(
            source_url,
            StorageTarget(source, backend, "development", "source-fixture"),
            tmp_path / "backups",
            maintenance=True,
            tool=tool,
        )
        destination = S3CompatibleStorage(client=FakeS3(), bucket="recovery-destination")
        manifest, rows = restore_objects(path, destination, execute=True)
        assert all(row["status"] == "copied" for row in rows)
        monkeypatch.setenv("RESTORE_ENVIRONMENT", "recovery")
        target_id = await check_restore_database(target_url, source_id=database_id(source_url))
        await check_restore_database(
            target_url, source_id=database_id(source_url), confirmation=target_id
        )
        from app.backup_restore import sha256_file
        from app.storage import recovery_cli

        monkeypatch.setenv("RESTORE_DATABASE_URL", target_url)
        monkeypatch.setattr(
            recovery_cli,
            "storage_target",
            lambda *args: StorageTarget(destination, "s3", "recovery", "recovery-fixture"),
        )
        monkeypatch.setattr(recovery_cli, "probe_target", lambda *args: None)
        monkeypatch.setattr(recovery_cli, "postgres_tool", tool)
        report_path = tmp_path / "restore-report.json"
        status = await asyncio.to_thread(
            recovery_cli.restore_main,
            [
                str(path),
                "--destination",
                "s3",
                "--report",
                str(report_path),
                "--restore-database",
                "--confirm-target",
                "recovery-fixture",
                "--confirm-database",
                target_id,
                "--confirm-backup",
                sha256_file(path / "manifest.json"),
                "--maintenance-window",
                "--allow-cross-environment",
            ],
        )
        assert status == 0
        import json

        assert json.loads(report_path.read_text())["complete"] is True
        verified = await reconcile_restored_database(target_url, destination, manifest)
        assert verified["verified"] and len(verified["results"]) == len(reference_map(references))
        target_engine = create_async_engine(target_url)
        try:
            async with AsyncSession(target_engine) as session:
                restored = await session.scalar(
                    select(VersionRecord).where(VersionRecord.id == published_id)
                )
                assert restored.status == VersionStatus.PUBLISHED
        finally:
            await target_engine.dispose()
        with pytest.raises(ValueError, match="empty"):
            await check_restore_database(
                target_url, source_id=database_id(source_url), confirmation=target_id
            )
    finally:
        await source_engine.dispose()
