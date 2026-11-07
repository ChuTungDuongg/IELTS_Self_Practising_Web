"""Durable CPU queue. Never invoked as a FastAPI background inference task."""

import asyncio
import ipaddress
import os
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import or_, select, update

from app.evaluation.speaking.diarization_backend import (
    LocalDiarizer,
    model_identity,
    normalize_recording,
)
from app.evaluation.speaking.diarization_models import DiarizationResult
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_audio import probe_audio
from app.models.speaking_benchmark import (
    SpeakingBenchmarkJob,
    SpeakingBenchmarkReview,
    SpeakingBenchmarkSample,
)
from app.schemas.speaking_benchmark import JobDTO, LabAvailability
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark import failure
from app.services.speaking_benchmark_review import initial_draft
from app.storage.factory import get_asset_storage

LEASE_SECONDS = 90


def configuration(settings):
    return {
        "version": "admin-diarization-v1",
        "identity": model_identity(),
        "threads": settings.speaking_benchmark_threads,
        "max_speakers": 8,
        "device": "cpu",
        "timeout": settings.speaking_benchmark_timeout_seconds,
        "memory_mb": settings.speaking_benchmark_memory_mb,
    }


def availability(settings):
    mode = settings.speaking_benchmark_execution
    reason = None
    host = urlsplit(settings.database_url).hostname or ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.lower() in {"localhost", "host.docker.internal", ""}
    if mode == "disabled":
        reason = "SPEAKING_BENCHMARK_WORKER_DISABLED"
    elif mode == "remote" and (
        settings.storage_backend == "local"
        or loopback
        or os.environ.get("IELTS_MODAL_DATABASE_MODE") == "embedded"
    ):
        reason = "SPEAKING_BENCHMARK_REMOTE_REQUIRES_SHARED_STORAGE_AND_DATABASE"
    elif mode == "local" and (
        os.environ.get("MODAL_TASK_ID") or os.environ.get("IELTS_MODAL_DATABASE_MODE") == "embedded"
    ):
        reason = "SPEAKING_BENCHMARK_EMBEDDED_WORKER_UNAVAILABLE"
    return LabAvailability(
        execution=mode,
        can_queue=reason is None,
        reason=reason,
        max_bytes=settings.speaking_benchmark_max_upload_mb * 1024**2,
        max_duration_ms=settings.speaking_benchmark_max_duration_seconds * 1000,
    )


async def enqueue(service, sample_id):
    ready = availability(service.settings)
    if not ready.can_queue:
        raise failure(ready.reason, 503)
    config = configuration(service.settings)
    async with service.session.begin():
        sample = await service.owned(sample_id, lock=True)
        digest = fingerprint([sample.source_sha256, config])
        active = await service.session.scalar(
            select(SpeakingBenchmarkJob).where(
                SpeakingBenchmarkJob.sample_id == sample.id,
                SpeakingBenchmarkJob.status.in_(["PENDING", "RUNNING"]),
            )
        )
        if active:
            return JobDTO.model_validate(active, from_attributes=True)
        completed = await service.session.scalar(
            select(SpeakingBenchmarkJob)
            .where(
                SpeakingBenchmarkJob.sample_id == sample.id,
                SpeakingBenchmarkJob.fingerprint == digest,
                SpeakingBenchmarkJob.status == "COMPLETED",
            )
            .order_by(SpeakingBenchmarkJob.created_at.desc())
            .limit(1)
        )
        if completed:
            return JobDTO.model_validate(completed, from_attributes=True)
        job = SpeakingBenchmarkJob(
            sample_id=sample.id,
            fingerprint=digest,
            source_sha256=sample.source_sha256,
            configuration=config,
        )
        service.session.add(job)
        sample.status = "PROCESSING"
        sample.revision += 1
        await service.session.flush()
        return JobDTO.model_validate(job, from_attributes=True)


async def cancel_job(service, sample_id, job_id):
    async with service.session.begin():
        sample = await service.owned(sample_id, lock=True)
        job = await service.session.scalar(
            select(SpeakingBenchmarkJob)
            .where(SpeakingBenchmarkJob.id == job_id, SpeakingBenchmarkJob.sample_id == sample.id)
            .with_for_update()
        )
        if job is None:
            raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
        if job.status in {"PENDING", "RUNNING"}:
            job.status, job.stage, job.finished_at = "CANCELLED", "cancelled", datetime.now(UTC)
            job.lease_token = None
            job.lease_expires_at = None
            sample.status = "REVIEW" if sample.review_revision else "DRAFT"
            sample.revision += 1
        return JobDTO.model_validate(job, from_attributes=True)


class DiarizationJobRunner:
    def __init__(self, factory, settings, *, storage=None, diarizer=None):
        self.factory, self.settings = factory, settings
        self.storage = storage or get_asset_storage(settings)
        self.diarizer = diarizer or LocalDiarizer(
            python=settings.speaking_benchmark_diarization_python or None,
            model_dir=settings.speaking_benchmark_model_dir or None,
            threads=settings.speaking_benchmark_threads,
            timeout=settings.speaking_benchmark_timeout_seconds,
            memory_mb=settings.speaking_benchmark_memory_mb,
            device="cpu",
        )

    async def claim(self):
        exhausted_sample = None
        async with self.factory() as session, session.begin():
            now = datetime.now(UTC)
            job = await session.scalar(
                select(SpeakingBenchmarkJob)
                .where(
                    or_(
                        SpeakingBenchmarkJob.status == "PENDING",
                        (SpeakingBenchmarkJob.status == "RUNNING")
                        & (SpeakingBenchmarkJob.lease_expires_at < now),
                    )
                )
                .order_by(SpeakingBenchmarkJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            if job.attempts >= 3:
                job.status, job.stage, job.error_code, job.finished_at = (
                    "FAILED",
                    "failed",
                    "SPEAKING_BENCHMARK_LEASE_EXHAUSTED",
                    now,
                )
                job.lease_token = None
                job.lease_expires_at = None
                exhausted_sample = job.sample_id
            else:
                job.status, job.stage, job.progress = "RUNNING", "materializing", 5
                job.lease_token = uuid4()
                job.attempts += 1
                job.started_at = job.started_at or now
                job.heartbeat_at, job.lease_expires_at = now, now + timedelta(seconds=LEASE_SECONDS)
                return job.id, job.sample_id, job.lease_token
        # Follow the same sample-before-job lock order as HTTP mutations. Never
        # wait for a sample while holding the scanner's job lock.
        if exhausted_sample is not None:
            async with self.factory() as session, session.begin():
                sample = await session.get(
                    SpeakingBenchmarkSample, exhausted_sample, with_for_update=True
                )
                active = await session.scalar(
                    select(SpeakingBenchmarkJob.id)
                    .where(
                        SpeakingBenchmarkJob.sample_id == exhausted_sample,
                        SpeakingBenchmarkJob.status.in_(["PENDING", "RUNNING"]),
                    )
                    .limit(1)
                )
                if sample is not None and active is None and sample.status == "PROCESSING":
                    sample.status = "REVIEW" if sample.review_revision else "DRAFT"
                    sample.revision += 1
        return None

    async def heartbeat(self, job_id, token, *, stage=None, progress=None):
        now = datetime.now(UTC)
        values = {"heartbeat_at": now, "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS)}
        if stage is not None:
            values.update(stage=stage, progress=progress)
        async with self.factory() as session, session.begin():
            result = await session.execute(
                update(SpeakingBenchmarkJob)
                .where(
                    SpeakingBenchmarkJob.id == job_id,
                    SpeakingBenchmarkJob.lease_token == token,
                    SpeakingBenchmarkJob.status == "RUNNING",
                    SpeakingBenchmarkJob.lease_expires_at > now,
                )
                .values(**values)
            )
            return result.rowcount == 1

    async def finish(self, claim, *, result=None, error_code=None):
        job_id, sample_id, token = claim
        async with self.factory() as session, session.begin():
            sample = await session.scalar(
                select(SpeakingBenchmarkSample)
                .where(SpeakingBenchmarkSample.id == sample_id)
                .with_for_update()
            )
            job = await session.get(SpeakingBenchmarkJob, job_id, with_for_update=True)
            now = datetime.now(UTC)
            if (
                sample is None
                or job is None
                or job.status != "RUNNING"
                or job.lease_token != token
                or job.lease_expires_at <= now
            ):
                return False
            if result is not None and (
                result.source_sha256 != sample.source_sha256
                or any(
                    result.identity.get(k) != v for k, v in job.configuration["identity"].items()
                )
                or fingerprint([sample.source_sha256, job.configuration]) != job.fingerprint
            ):
                error_code, result = "REPLAY_APPROVED_SOURCE_CHANGED", None
            if result is not None:
                job.result = result.model_dump(mode="json")
                review = SpeakingBenchmarkReview(
                    sample_id=sample.id,
                    revision=sample.review_revision + 1,
                    job_id=job.id,
                    draft=initial_draft(result).model_dump(mode="json"),
                )
                session.add(review)
                sample.review_revision = review.revision
                sample.status = "REVIEW"
            else:
                sample.status = "REVIEW" if sample.review_revision else "DRAFT"
            sample.revision += 1
            job.status = "COMPLETED" if result is not None else "FAILED"
            job.stage, job.progress = (
                ("completed", 100) if result is not None else ("failed", job.progress)
            )
            job.error_code = error_code
            job.finished_at, job.lease_token, job.lease_expires_at = now, None, None
            return True

    async def run_once(self):
        if not availability(self.settings).can_queue:
            raise failure(availability(self.settings).reason, 503)
        claim = await self.claim()
        if claim is None:
            return False
        job_id, sample_id, token = claim
        stopped = threading.Event()

        async def pulse():
            while True:
                await asyncio.sleep(10)
                try:
                    if not await self.heartbeat(job_id, token):
                        stopped.set()
                        return
                except Exception:
                    stopped.set()
                    return

        pulse_task = asyncio.create_task(pulse())
        operation = None
        try:
            async with self.factory() as session, session.begin():
                sample = await session.get(SpeakingBenchmarkSample, sample_id)
                job = await session.get(SpeakingBenchmarkJob, job_id)
                if (
                    sample is None
                    or job is None
                    or sample.source_sha256 != job.source_sha256
                    or job.configuration != configuration(self.settings)
                ):
                    raise BenchmarkInputError("SPEAKING_BENCHMARK_SOURCE_OR_CONFIG_CHANGED")
                asset_key, checksum, duration, size, mime = (
                    sample.audio_key,
                    sample.source_sha256,
                    sample.duration_ms,
                    sample.byte_size,
                    sample.mime_type,
                )

            def process():
                self.diarizer.should_cancel = stopped.is_set
                settings = self.diarizer.audio_settings(self.settings)
                with (
                    self.storage.materialize(
                        asset_key,
                        max_bytes=self.settings.speaking_benchmark_max_upload_mb * 1024**2,
                    ) as original,
                    tempfile.TemporaryDirectory(prefix="benchmark-cpu-") as directory,
                ):
                    source_name = "recording.wav" if mime == "audio/wav" else "recording.mp3"
                    # Materialized S3 temp paths intentionally have no source extension. Probe
                    # validates bytes; normalize_recording receives a safe private source alias.
                    media = probe_audio(original, settings)
                    if (
                        media["sha256"] != checksum
                        or media["duration_ms"] != duration
                        or media["size_bytes"] != size
                    ):
                        raise BenchmarkInputError("REPLAY_APPROVED_SOURCE_CHANGED")
                    if stopped.is_set():
                        raise BenchmarkInputError("SPEAKING_BENCHMARK_CANCELLED")
                    import shutil

                    root = Path(directory)
                    shutil.copyfile(original, root / source_name)
                    decoded = root / "normalized.wav"
                    normalize_recording(root, source_name, media, decoded, settings)
                    if stopped.is_set():
                        raise BenchmarkInputError("SPEAKING_BENCHMARK_CANCELLED")
                    return self.diarizer.analyze(
                        decoded,
                        source=source_name,
                        metadata=media,
                        cache_key=fingerprint([checksum, configuration(self.settings)]),
                    )

            await self.heartbeat(job_id, token, stage="cpu_diarization", progress=15)
            operation = asyncio.create_task(asyncio.to_thread(process))
            result = await asyncio.shield(operation)
            await self.finish(claim, result=DiarizationResult.model_validate(result))
        except asyncio.CancelledError:
            stopped.set()
            if operation:
                await asyncio.gather(operation, return_exceptions=True)
            # Shutdown is a recoverable interrupted CPU attempt; do not falsify completion.
            raise
        except Exception as error:
            code = (
                str(error)
                if isinstance(error, BenchmarkInputError)
                else "SPEAKING_BENCHMARK_WORKER_FAILED"
            )
            if len(code) > 100 or not code.replace("_", "").isalnum():
                code = "SPEAKING_BENCHMARK_WORKER_FAILED"
            await self.finish(claim, error_code=code)
        finally:
            stopped.set()
            pulse_task.cancel()
            await asyncio.gather(pulse_task, return_exceptions=True)
        return True
