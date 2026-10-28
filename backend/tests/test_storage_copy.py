from io import BytesIO

from app.storage.local import LocalAssetStorage
from app.storage.migration import copy_keys


def test_copy_dry_run_resume_and_conflict_without_deleting_source(tmp_path):
    source = LocalAssetStorage(tmp_path / "source")
    dest = LocalAssetStorage(tmp_path / "dest")
    source.put_stream("images/a.png", BytesIO(b"abc"), content_type="image/png", max_bytes=3)
    preview = copy_keys(source, dest, ["images/a.png", "images/missing.png"], dry_run=True)
    assert {row.key: row.status for row in preview} == {
        "images/a.png": "would_copy",
        "images/missing.png": "missing_source",
    }
    assert not dest.exists("images/a.png")
    assert copy_keys(source, dest, ["images/a.png"], dry_run=False)[0].status == "copied"
    assert copy_keys(source, dest, ["images/a.png"], dry_run=False)[0].status == "identical"
    (tmp_path / "dest" / "images" / "a.png").write_bytes(b"different")
    assert copy_keys(source, dest, ["images/a.png"], dry_run=False)[0].status == "conflict"
    assert (tmp_path / "source" / "images" / "a.png").read_bytes() == b"abc"
    assert (tmp_path / "dest" / "images" / "a.png").read_bytes() == b"different"


def test_copy_detects_corrupt_destination(tmp_path):
    source = LocalAssetStorage(tmp_path / "source")
    source.put_stream("images/a.png", BytesIO(b"abc"), content_type="image/png", max_bytes=3)

    class CorruptStorage(LocalAssetStorage):
        def put_stream(self, key, _source, *, content_type, max_bytes):
            super().put_stream(key, BytesIO(b"bad"), content_type=content_type, max_bytes=max_bytes)

    dest = CorruptStorage(tmp_path / "dest")
    assert (
        copy_keys(source, dest, ["images/a.png"], dry_run=False)[0].status == "verification_failed"
    )
    assert source.exists("images/a.png")


async def test_inventory_collects_and_deduplicates_all_referenced_categories():
    from app.storage.migration import inventory_referenced_keys

    class Session:
        async def scalars(self, statement):
            sql = str(statement)
            for table in (
                "assets",
                "test_covers",
                "classroom_resources",
                "speaking_audio_chunks",
                "speaking_normalized_audio",
                "writing_benchmark_samples",
            ):
                assert table in sql
            return ["images/a.png", "speaking-private/chunk.webm", "images/a.png", None]

    assert await inventory_referenced_keys(Session()) == [
        "images/a.png",
        "speaking-private/chunk.webm",
    ]
