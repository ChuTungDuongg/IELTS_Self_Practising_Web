import asyncio
import csv
import io
import json
import threading
import zipfile
from uuid import uuid4

import pytest
from benchmark_helpers import isolated_bank
from teacher_helpers import api_client, make_user
from test_writing_benchmark_api import ROOT
from test_writing_benchmark_images import PNG

from app.core.exceptions import AppError
from app.evaluation.task1.manifest import load_manifest as load_task1
from app.evaluation.task1.models import BenchmarkSample as Task1Sample
from app.evaluation.task2.manifest import load_manifest as load_task2
from app.models import WritingBenchmarkSample
from app.models.enums import UserRole
from app.schemas.writing_benchmark import BenchmarkMutation
from app.services.writing_benchmark import WritingBenchmarkService
from app.services.writing_benchmark_export import WritingBenchmarkExportService
from app.storage import LocalAssetStorage

ROOT_FILES = {
    "task1.jsonl",
    "task2.jsonl",
    "task1.csv",
    "task2.csv",
    "manifest.schema.json",
    "README.txt",
}


async def seed(session, storage, task=1, slot=1, **edits):
    row = WritingBenchmarkSample(
        id=uuid4(),
        task_number=task,
        sequence_number=slot,
        status="COMPLETE",
        prompt='Fictional, "prompt"\r\n😀 second line',
        essay=" Fictional essay\r\n\r\nParagraph two\n",
        human_ta_tr=6,
        human_cc=6,
        human_lr=6.5,
        human_gra=6.5,
        **edits,
    )
    if task == 1:
        row.task1_task_type = "PIE_CHART"
        row.task1_image_key = storage.store_benchmark_writing_image(
            row.id, "image/png", "../../hostile.png", PNG, 100
        ).relative_path
    async with session.begin():
        session.add(row)
        await session.flush()
    return row


async def test_empty_bundle_contains_both_manifests_and_csv_headers(db_session, tmp_path):
    path = tmp_path / "empty.zip"
    await WritingBenchmarkExportService(db_session, LocalAssetStorage(tmp_path)).export(path)
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist()) == ROOT_FILES | {"images/"}
        assert archive.read("task1.jsonl") == archive.read("task2.jsonl") == b""
        assert "human_tr" in archive.read("task2.csv").decode("utf-8")
        schema = json.loads(archive.read("manifest.schema.json"))
        assert "$defs" in schema and "anyOf" in schema


async def test_partial_bundle_compatible_current_loaders_and_multiline_csv(db_session, tmp_path):
    storage = LocalAssetStorage(tmp_path / "assets")
    row = await seed(db_session, storage, slot=37)
    await seed(
        db_session,
        storage,
        task=2,
        slot=8,
        split="HOLDOUT",
        source_note="Fictional source",
        redistributable=True,
    )
    async with db_session.begin():
        db_session.add(WritingBenchmarkSample(task_number=1, sequence_number=38))
    path = tmp_path / "bank.zip"
    exporter = WritingBenchmarkExportService(db_session, storage)
    await exporter.export(path)
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist()) == ROOT_FILES | {"images/", "images/T1-037.png"}
        t1 = json.loads(archive.read("task1.jsonl"))
        assert Task1Sample.model_validate(t1).id == "T1-037"
        assert t1["raters"] == 1 and t1["redistributable"] is False and t1["visual_truth"] is None
        assert t1["provenance"] == "admin-labelled benchmark sample"
        assert t1["task_type"] == "PIE_CHART" and t1["image_path"] == "images/T1-037.png"
        assert isinstance(t1["human_scores"]["ta"], (int, float))
        assert "task1_image_key" not in archive.read("task1.jsonl").decode()
        csv_rows = list(
            csv.DictReader(io.StringIO(archive.read("task1.csv").decode("utf-8"), newline=""))
        )
        assert csv_rows[0]["prompt"] == row.prompt and csv_rows[0]["essay"] == row.essay
        assert csv_rows[0]["human_overall"] == "6.5"
        # All archive names here are generated fixed names, safe to extract in a test.
        archive.extractall(tmp_path / "unpacked")
        before = {name: archive.read(name) for name in archive.namelist()}
    assert load_task1(tmp_path / "unpacked/task1.jsonl", "dev")[0].image.data == PNG
    assert load_task2(tmp_path / "unpacked/task2.jsonl", "holdout")[0].sample.id == "T2-008"
    await exporter.export(path)
    with zipfile.ZipFile(path) as archive:
        assert before == {name: archive.read(name) for name in archive.namelist()}


@pytest.mark.parametrize(
    "key", ["../outside.png", "/absolute.png", "images/unrelated.png", "missing"]
)
async def test_export_rejects_unsafe_or_missing_image_without_leak(db_session, tmp_path, key):
    storage = LocalAssetStorage(tmp_path / "assets")
    row = await seed(db_session, storage)
    async with db_session.begin():
        row.task1_image_key = (
            key if key != "missing" else f"benchmark/writing/task1/{row.id}/{uuid4().hex}.png"
        )
    with pytest.raises(AppError) as error:
        await WritingBenchmarkExportService(db_session, storage).export(tmp_path / "bank.zip")
    assert error.value.code == "BENCHMARK_EXPORT_INVALID"
    assert "outside" not in error.value.message


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.TEACHER])
async def test_export_admin_only(db_session, role):
    actor = await make_user(db_session, role)
    async with api_client(db_session, actor) as client:
        assert (await client.get(ROOT + "/export")).status_code == 403


async def test_export_endpoint_download_and_temp_cleanup(db_session, monkeypatch):
    import app.api.v1.writing_benchmark as routes

    paths = []
    original = routes.tempfile.NamedTemporaryFile

    def create_temp(*args, **kwargs):
        handle = original(*args, **kwargs)
        from pathlib import Path

        paths.append(Path(handle.name))
        return handle

    monkeypatch.setattr(routes.tempfile, "NamedTemporaryFile", create_temp)
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        response = await client.get(ROOT + "/export")
        assert response.status_code == 200
        assert "writing-benchmark.zip" in response.headers["content-disposition"]
        assert zipfile.is_zipfile(io.BytesIO(response.content))
    assert paths and all(not path.exists() for path in paths)


async def test_snapshot_row_lock_keeps_image_consistent_during_replacement(tmp_path, monkeypatch):
    storage = LocalAssetStorage(tmp_path / "assets")
    async with isolated_bank() as (_, sessions):
        async with sessions() as session:
            row = await seed(session, storage)
            sample_id, revision = row.id, row.revision
        async with sessions() as session:
            exporter = WritingBenchmarkExportService(session, storage)
            original = exporter._write_bundle
            ready, release = threading.Event(), threading.Event()

            def stage(*args):
                ready.set()
                assert release.wait(5)
                return original(*args)

            monkeypatch.setattr(exporter, "_write_bundle", stage)
            export_task = asyncio.create_task(exporter.export(tmp_path / "bank.zip"))
            assert await asyncio.to_thread(ready.wait, 5)

            async def replace():
                async with sessions() as other:
                    return await WritingBenchmarkService(other, storage).replace_image(
                        sample_id,
                        BenchmarkMutation(expected_revision=revision),
                        "image/png",
                        "new.png",
                        PNG + b"replacement",
                    )

            mutation = asyncio.create_task(replace())
            await asyncio.sleep(0.05)
            assert not mutation.done()
            release.set()
            await export_task
            await mutation
        with zipfile.ZipFile(tmp_path / "bank.zip") as archive:
            assert archive.read("images/T1-001.png") == PNG
