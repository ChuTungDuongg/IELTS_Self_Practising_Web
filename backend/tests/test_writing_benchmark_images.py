import asyncio
from uuid import uuid4

import pytest
from benchmark_helpers import isolated_bank
from teacher_helpers import api_client, make_user
from test_writing_benchmark_api import ROOT, create, patch

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import WritingBenchmarkSample
from app.models.enums import UserRole
from app.schemas.writing_benchmark import (
    BenchmarkMutation,
    BenchmarkSampleCreate,
)
from app.services.writing_benchmark import WritingBenchmarkService, owns_image_key
from app.storage import LocalAssetStorage

PNG = b"\x89PNG\r\n\x1a\nfictional image"
JPEG = b"\xff\xd8\xfffictional image"
WEBP = b"RIFF1234WEBPfictional image"


@pytest.mark.parametrize(
    "mime,name,content,ext",
    [
        ("image/png", "../hostile.png", PNG, ".png"),
        ("image/jpeg", "test.jpeg", JPEG, ".jpg"),
        ("image/webp", "test.webp", WEBP, ".webp"),
    ],
)
def test_private_immutable_namespace(tmp_path, mime, name, content, ext):
    storage = LocalAssetStorage(tmp_path)
    sample_id = uuid4()
    first = storage.store_benchmark_writing_image(sample_id, mime, name, content, 100)
    second = storage.store_benchmark_writing_image(sample_id, mime, name, content, 100)
    assert first.relative_path != second.relative_path
    assert owns_image_key(sample_id, first.relative_path)
    assert first.relative_path.endswith(ext)
    assert "hostile" not in first.relative_path
    assert storage.resolve(first.relative_path).read_bytes() == content


@pytest.mark.parametrize(
    "mime,name,content,limit",
    [
        ("text/plain", "test.png", PNG, 100),
        ("image/png", "test.exe", PNG, 100),
        ("image/png", "test.png", JPEG, 100),
        ("image/jpeg", "test.jpg", PNG, 100),
        ("image/webp", "test.webp", b"RIFFwrong", 100),
        ("image/png", "test.png", b"", 100),
        ("image/png", "test.png", PNG, 5),
    ],
)
def test_image_guards(tmp_path, mime, name, content, limit):
    with pytest.raises(AppError):
        LocalAssetStorage(tmp_path).store_benchmark_writing_image(
            uuid4(), mime, name, content, limit
        )
    assert not list(tmp_path.rglob("*.png"))


async def upload(client, sample, content=PNG, filename="fictional.png", mime="image/png"):
    return await client.post(
        f"{ROOT}/samples/{sample['id']}/image",
        data={"expected_revision": sample["revision"]},
        files={"file": (filename, content, mime)},
    )


async def test_upload_private_read_complete_remove_and_delete(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        sample = await create(client, 1)
        uploaded = (await upload(client, sample)).json()
        assert uploaded["has_image"] and uploaded["revision"] == 2
        assert "task1_image_key" not in uploaded
        url = f"{ROOT}/samples/{sample['id']}"
        image = await client.get(url + "/image")
        assert image.status_code == 200 and image.content == PNG
        assert image.headers["cache-control"] == "no-store"
        saved = (
            await client.patch(
                url,
                json=patch(
                    uploaded,
                    prompt="Fictional visual",
                    essay="Fictional essay",
                    task1_task_type="PIE_CHART",
                    human_scores={"ta": 6, "cc": 6, "lr": 6, "gra": 6},
                ),
            )
        ).json()
        complete = (await client.post(url + "/complete", json=patch(saved))).json()
        removed = (
            await client.delete(url + "/image", params={"expected_revision": complete["revision"]})
        ).json()
        assert removed["status"] == "DRAFT" and not removed["has_image"]
        assert not list(tmp_path.rglob("*.png"))
        uploaded = (await upload(client, removed)).json()
        assert (
            await client.delete(url, params={"expected_revision": uploaded["revision"]})
        ).status_code == 204
        assert not list(tmp_path.rglob("*.png"))


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.TEACHER])
async def test_all_image_routes_are_admin_only(db_session, role):
    actor = await make_user(db_session, role)
    async with api_client(db_session, actor) as client:
        url = f"{ROOT}/samples/{uuid4()}/image"
        assert (await client.get(url)).status_code == 403
        assert (
            await client.post(
                url,
                data={"expected_revision": 1},
                files={"file": ("fictional.png", PNG, "image/png")},
            )
        ).status_code == 403
        assert (await client.delete(url, params={"expected_revision": 1})).status_code == 403


async def test_task2_image_and_stale_upload_rejected(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        assert (await upload(client, await create(client, 2))).status_code == 422
        sample = await create(client, 1)
        first = (await upload(client, sample)).json()
        assert (await upload(client, sample)).status_code == 409
        assert len(list(tmp_path.rglob("*.png"))) == 1
        second = (await upload(client, first)).json()
        assert second["revision"] == 3
        assert len(list(tmp_path.rglob("*.png"))) == 1


async def test_failed_db_mutation_preserves_old_image(db_session, tmp_path, monkeypatch):
    service = WritingBenchmarkService(db_session, LocalAssetStorage(tmp_path))
    sample = await service.create(BenchmarkSampleCreate(task_number=1))
    first = await service.replace_image(
        sample.id,
        BenchmarkMutation(expected_revision=sample.revision),
        "image/png",
        "fictional.png",
        PNG,
    )
    old = list(tmp_path.rglob("*.png"))[0]

    async def fail():
        raise RuntimeError("fictional DB flush failure")

    monkeypatch.setattr(db_session, "flush", fail)
    with pytest.raises(RuntimeError):
        await service.replace_image(
            sample.id,
            BenchmarkMutation(expected_revision=first.revision),
            "image/png",
            "fictional.png",
            PNG,
        )
    assert list(tmp_path.rglob("*.png")) == [old]
    assert old.read_bytes() == PNG


@pytest.mark.parametrize("key_kind", ["traversal", "foreign", "symlink", "missing", "corrupt"])
async def test_invalid_owned_path_cannot_read_or_delete_unrelated_file(
    db_session, tmp_path, key_kind
):
    service = WritingBenchmarkService(db_session, LocalAssetStorage(tmp_path))
    sample = await service.create(BenchmarkSampleCreate(task_number=1))
    unrelated = tmp_path / "unrelated.png"
    unrelated.write_bytes(PNG)
    good = f"benchmark/writing/task1/{sample.id}/{uuid4().hex}.png"
    key = {
        "traversal": "../unrelated.png",
        "foreign": "unrelated.png",
        "symlink": good,
        "missing": good,
        "corrupt": good,
    }[key_kind]
    if key_kind == "symlink":
        link = tmp_path / good
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(unrelated)
        except OSError:
            pytest.skip("Symlinks unavailable on this Windows host; Linux CI covers this guard")
    if key_kind == "corrupt":
        key = good
        file = tmp_path / key
        file.parent.mkdir(parents=True)
        file.write_bytes(b"invalid image")
    async with db_session.begin():
        row = await db_session.get(WritingBenchmarkSample, sample.id)
        row.task1_image_key = key
    with pytest.raises(AppError):
        await service.image_content(sample.id)
    await service.delete(sample.id, BenchmarkMutation(expected_revision=sample.revision))
    assert unrelated.read_bytes() == PNG


async def test_commit_ack_loss_retains_possibly_committed_new_image(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    async with isolated_bank() as (_, sessions):
        async with sessions() as session:
            service = WritingBenchmarkService(session, LocalAssetStorage(tmp_path))
            sample = await service.create(BenchmarkSampleCreate(task_number=1))
            original = session.begin

            @asynccontextmanager
            async def lost_ack():
                async with original():
                    yield
                raise RuntimeError("fictional acknowledgement lost after commit")

            monkeypatch.setattr(session, "begin", lost_ack)
            with pytest.raises(RuntimeError):
                await service.replace_image(
                    sample.id,
                    BenchmarkMutation(expected_revision=sample.revision),
                    "image/png",
                    "fictional.png",
                    PNG,
                )
        assert len(list(tmp_path.rglob("*.png"))) == 1
        async with sessions() as session:
            service = WritingBenchmarkService(session, LocalAssetStorage(tmp_path))
            current = await service.detail(sample.id)
            assert current.has_image and current.revision == sample.revision + 1
            with pytest.raises(AppError) as error:
                await service.replace_image(
                    sample.id,
                    BenchmarkMutation(expected_revision=sample.revision),
                    "image/png",
                    "fictional.png",
                    PNG,
                )
            assert error.value.code == "DRAFT_REVISION_CONFLICT"
        assert len(list(tmp_path.rglob("*.png"))) == 1


async def test_real_concurrent_replace_remove_revision_barrier(tmp_path):
    async with isolated_bank() as (_, sessions):
        async with sessions() as session:
            service = WritingBenchmarkService(session, LocalAssetStorage(tmp_path))
            sample = await service.create(BenchmarkSampleCreate(task_number=1))
            sample = await service.replace_image(
                sample.id,
                BenchmarkMutation(expected_revision=sample.revision),
                "image/png",
                "fictional.png",
                PNG,
            )

        async def mutation(remove):
            async with sessions() as session:
                service = WritingBenchmarkService(session, LocalAssetStorage(tmp_path))
                try:
                    if remove:
                        return await service.remove_image(
                            sample.id, BenchmarkMutation(expected_revision=sample.revision)
                        )
                    return await service.replace_image(
                        sample.id,
                        BenchmarkMutation(expected_revision=sample.revision),
                        "image/png",
                        "fictional.png",
                        PNG,
                    )
                except AppError as error:
                    return error

        results = await asyncio.gather(mutation(True), mutation(False))
        assert sum(isinstance(r, AppError) for r in results) == 1
        async with sessions() as session:
            current = await WritingBenchmarkService(session, LocalAssetStorage(tmp_path)).detail(
                sample.id
            )
        assert current.revision == sample.revision + 1
        assert len(list(tmp_path.rglob("*.png"))) == int(current.has_image)
