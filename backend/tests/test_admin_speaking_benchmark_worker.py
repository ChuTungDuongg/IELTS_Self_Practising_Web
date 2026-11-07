"""Real PostgreSQL claims and fencing; synthetic audio and an injected CPU adapter."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_admin_speaking_benchmark import BYTES, fake_probe, result_for
from test_admin_speaking_benchmark import lab_settings as shared_lab_settings

from app.core.config import get_settings
from app.models import User
from app.models.enums import UserRole
from app.models.speaking_benchmark import (
    SpeakingBenchmarkJob,
    SpeakingBenchmarkReview,
    SpeakingBenchmarkSample,
)
from app.services import speaking_benchmark_jobs as jobs
from app.services.speaking_benchmark import SpeakingBenchmarkService
from app.services.speaking_benchmark_jobs import DiarizationJobRunner, configuration, enqueue
from app.storage.local import LocalAssetStorage
from testsupport.test_database import validate_test_database_url


@pytest.fixture
def lab_settings(tmp_path, monkeypatch):
    return shared_lab_settings.__wrapped__(tmp_path, monkeypatch)


@pytest_asyncio.fixture
async def durable_lab(lab_settings):
    url = os.environ.get("P2_TEST_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Explicit disposable TEST_DATABASE_URL required")
    validate_test_database_url(url, get_settings().database_url)
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_id, sample_id = uuid4(), uuid4()
    key = f"benchmark/speaking/{sample_id}/fixture.wav"
    storage = LocalAssetStorage(lab_settings.resolved_storage_root)
    path = lab_settings.resolved_storage_root / "input.wav"
    path.write_bytes(BYTES)
    media = fake_probe(path, lab_settings)
    import io

    storage.put_stream(key, io.BytesIO(BYTES), content_type="audio/wav", max_bytes=10000)
    async with factory() as session, session.begin():
        session.add(
            User(
                id=owner_id,
                email=f"worker-{owner_id}@example.com",
                display_name="Fictional admin",
                role=UserRole.ADMIN,
                is_active=True,
                email_verified=True,
            )
        )
        await session.flush()
        session.add(
            SpeakingBenchmarkSample(
                id=sample_id,
                owner_id=owner_id,
                code="WORKER-FIXTURE",
                audio_key=key,
                source_sha256=media["sha256"],
                mime_type="audio/wav",
                byte_size=len(BYTES),
                duration_ms=60000,
                source_note="Synthetic authorized fixture",
                rights_confirmed=True,
            )
        )
    async with factory() as session:
        queued = await enqueue(
            SpeakingBenchmarkService(session, owner_id, settings=lab_settings, storage=storage),
            sample_id,
        )
    try:
        yield factory, owner_id, sample_id, queued.id, storage
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(SpeakingBenchmarkSample).where(SpeakingBenchmarkSample.id == sample_id)
            )
            await session.execute(delete(User).where(User.id == owner_id))
        await engine.dispose()


def runner_for(factory, settings, storage):
    return DiarizationJobRunner(factory, settings, storage=storage)


async def test_atomic_claim_and_stale_worker_fencing(durable_lab, lab_settings):
    factory, _, sample_id, job_id, storage = durable_lab
    runner = runner_for(factory, lab_settings, storage)
    claims = await asyncio.gather(runner.claim(), runner.claim())
    assert sum(c is not None for c in claims) == 1
    old = next(c for c in claims if c)
    async with factory() as session, session.begin():
        await session.execute(
            update(SpeakingBenchmarkJob)
            .where(SpeakingBenchmarkJob.id == job_id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    new = await runner.claim()
    assert new[2] != old[2]
    assert not await runner.heartbeat(job_id, old[2])
    assert not await runner.finish(old, error_code="OLD_WORKER")
    assert await runner.finish(new, error_code="FIXTURE_FAILURE")
    async with factory() as session, session.begin():
        job = await session.get(SpeakingBenchmarkJob, job_id)
        assert job.status == "FAILED" and job.error_code == "FIXTURE_FAILURE" and job.attempts == 2
        assert (await session.get(SpeakingBenchmarkSample, sample_id)).status == "DRAFT"


async def test_lease_exhaustion_is_bounded_and_sample_recovers(durable_lab, lab_settings):
    factory, _, sample_id, job_id, storage = durable_lab
    runner = runner_for(factory, lab_settings, storage)
    for _attempt in range(3):
        assert await runner.claim()
        async with factory() as session, session.begin():
            await session.execute(
                update(SpeakingBenchmarkJob)
                .where(SpeakingBenchmarkJob.id == job_id)
                .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
    assert await runner.claim() is None
    async with factory() as session, session.begin():
        job = await session.get(SpeakingBenchmarkJob, job_id)
        assert job.attempts == 3 and job.error_code.endswith("LEASE_EXHAUSTED")
        assert (await session.get(SpeakingBenchmarkSample, sample_id)).status == "DRAFT"


async def test_real_runner_reuses_cpu_adapter_and_preserves_three_speakers(
    durable_lab, lab_settings, monkeypatch
):
    factory, _, sample_id, job_id, storage = durable_lab
    observed = []

    class FakeDiarizer:
        def audio_settings(self, settings):
            return settings

        def analyze(self, path, *, source, metadata, cache_key):
            observed.append((path, source, metadata, cache_key))
            assert path.exists() and not self.should_cancel()
            result = result_for(metadata["sha256"])
            return result.model_copy(update={"identity": configuration(lab_settings)["identity"]})

    monkeypatch.setattr(jobs, "probe_audio", fake_probe)

    def normalize(root, name, media, decoded, settings):
        decoded.write_bytes(b"synthetic normalized placeholder")

    monkeypatch.setattr(jobs, "normalize_recording", normalize)
    runner = DiarizationJobRunner(factory, lab_settings, storage=storage, diarizer=FakeDiarizer())
    assert await runner.run_once()
    assert len(observed) == 1 and not observed[0][0].exists()
    async with factory() as session, session.begin():
        job = await session.get(SpeakingBenchmarkJob, job_id)
        assert job.status == "COMPLETED" and job.progress == 100
        review = await session.get(SpeakingBenchmarkReview, (sample_id, 1))
        assert review.draft["candidate_confirmed"] is False and review.manifest is None
        assert set(review.draft["roles"]) == {"candidate", "examiner", "third"}
        assert job.result["regular"] == job.result["exclusive"]
    async with factory() as session:
        cached = await enqueue(
            SpeakingBenchmarkService(
                session, durable_lab[1], settings=lab_settings, storage=storage
            ),
            sample_id,
        )
        assert cached.id == job_id


async def test_cancelled_job_cannot_accept_late_result(durable_lab, lab_settings):
    factory, owner, sample_id, job_id, storage = durable_lab
    runner = runner_for(factory, lab_settings, storage)
    claim = await runner.claim()
    async with factory() as session:
        await jobs.cancel_job(
            SpeakingBenchmarkService(session, owner, settings=lab_settings, storage=storage),
            sample_id,
            job_id,
        )
    assert not await runner.heartbeat(job_id, claim[2])
    assert not await runner.finish(claim, error_code="LATE_ERROR")
    async with factory() as session, session.begin():
        assert (await session.get(SpeakingBenchmarkJob, job_id)).status == "CANCELLED"
        assert (
            await session.scalar(
                select(SpeakingBenchmarkReview).where(
                    SpeakingBenchmarkReview.sample_id == sample_id
                )
            )
            is None
        )
