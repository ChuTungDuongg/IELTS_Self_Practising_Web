"""Owner-scoped dataset transactions. No inference is executed by this service."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.evaluation.speaking.diarization_models import DiarizationResult
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_audio import probe_audio
from app.evaluation.speaking.replay_segmentation import suggest_roles
from app.evaluation.speaking.runner import audio_digest
from app.models.speaking import SpeakingMediaCleanup
from app.models.speaking_benchmark import (
    SpeakingBenchmarkHumanLabel,
    SpeakingBenchmarkJob,
    SpeakingBenchmarkReview,
    SpeakingBenchmarkSample,
)
from app.schemas.speaking_benchmark import (
    JobDTO,
    LabelsDTO,
    ReviewDraft,
    ReviewDTO,
    SampleDTO,
    SamplePage,
)
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark_review import (
    approval_errors,
    manifest_for_review,
    suggest_windows,
    validate_draft,
)
from app.storage.factory import get_asset_storage


def failure(code, status=422):
    return AppError(
        code, "The benchmark operation could not be completed. Review the indicated issue.", status
    )


def check_revision(actual, expected):
    if actual != expected:
        raise failure("SPEAKING_BENCHMARK_REVISION_CONFLICT", 409)


class SpeakingBenchmarkService:
    def __init__(self, session, owner_id, *, settings=None, storage=None):
        self.session, self.owner_id = session, owner_id
        self.settings = settings or get_settings()
        self.storage = storage or get_asset_storage(self.settings)

    async def owned(self, sample_id, *, lock=False):
        query = select(SpeakingBenchmarkSample).where(
            SpeakingBenchmarkSample.id == sample_id,
            SpeakingBenchmarkSample.owner_id == self.owner_id,
            SpeakingBenchmarkSample.deletion_pending_at.is_(None),
        )
        row = await self.session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
        return row

    async def sample_dto(self, row):
        # Database-generated onupdate timestamps may be expired after a mutation.
        await self.session.refresh(row)
        label = (
            await self.session.get(SpeakingBenchmarkHumanLabel, (row.id, row.label_revision))
            if row.label_revision
            else None
        )
        labelled = label is not None and any(
            getattr(label, k) is not None for k in ("fc", "lr", "gra", "pr", "overall")
        )
        return SampleDTO(
            **{key: getattr(row, key) for key in SampleDTO.model_fields if key != "label_status"},
            label_status="HUMAN_VERIFIED"
            if labelled and label.verified
            else "UNVERIFIED"
            if labelled
            else "UNLABELLED",
        )

    async def list(self, offset, limit):
        async with self.session.begin():
            scope = (
                SpeakingBenchmarkSample.owner_id == self.owner_id
            ) & SpeakingBenchmarkSample.deletion_pending_at.is_(None)
            total = await self.session.scalar(
                select(func.count()).select_from(SpeakingBenchmarkSample).where(scope)
            )
            rows = await self.session.scalars(
                select(SpeakingBenchmarkSample)
                .where(scope)
                .order_by(SpeakingBenchmarkSample.created_at.desc(), SpeakingBenchmarkSample.id)
                .offset(offset)
                .limit(limit)
            )
            return SamplePage(
                items=[await self.sample_dto(row) for row in rows],
                total=total,
                offset=offset,
                limit=limit,
            )

    async def detail(self, sample_id):
        async with self.session.begin():
            return await self.sample_dto(await self.owned(sample_id))

    async def patch(self, sample_id, body):
        try:
            async with self.session.begin():
                row = await self.owned(sample_id, lock=True)
                check_revision(row.revision, body.expected_revision)
                for key, value in body.model_dump(exclude={"expected_revision"}).items():
                    setattr(row, key, value)
                row.revision += 1
                await self.session.flush()
                return await self.sample_dto(row)
        except IntegrityError:
            raise failure("SPEAKING_BENCHMARK_DUPLICATE", 409) from None

    async def upload(self, path, metadata):
        maximum = self.settings.speaking_benchmark_max_upload_mb * 1024**2
        if not 0 < path.stat().st_size <= maximum:
            raise failure("SPEAKING_BENCHMARK_UPLOAD_SIZE")
        try:
            # The existing resolver supports the installed Windows shared FFmpeg runtime.
            from app.evaluation.speaking.diarization_backend import LocalDiarizer

            audio_settings = await asyncio.to_thread(LocalDiarizer().audio_settings, self.settings)
            probing = asyncio.create_task(asyncio.to_thread(probe_audio, path, audio_settings))
            try:
                media = await asyncio.shield(probing)
            except asyncio.CancelledError:
                await asyncio.gather(probing, return_exceptions=True)
                raise
        except BenchmarkInputError as error:
            raise failure(str(error)) from None
        if media["duration_ms"] > self.settings.speaking_benchmark_max_duration_seconds * 1000:
            raise failure("SPEAKING_BENCHMARK_DURATION_EXCEEDED")
        sample_id = uuid4()
        key = f"benchmark/speaking/{sample_id}/{uuid4().hex}.{'wav' if media['format'] == 'wav' else 'mp3'}"
        mime = "audio/wav" if media["format"] == "wav" else "audio/mpeg"
        # Durable reservation precedes object creation. Delayed cleanup cannot lose an upload
        # between a successful object write and an uncertain database commit.
        async with self.session.begin():
            existing = await self.session.scalar(
                select(SpeakingBenchmarkSample.id).where(
                    SpeakingBenchmarkSample.owner_id == self.owner_id,
                    (SpeakingBenchmarkSample.source_sha256 == media["sha256"])
                    | (SpeakingBenchmarkSample.code == metadata.code),
                )
            )
            if existing:
                raise failure("SPEAKING_BENCHMARK_DUPLICATE", 409)
            reservation = SpeakingMediaCleanup(storage_key=key)
            self.session.add(reservation)
            await self.session.flush()
            reservation_id = reservation.id
        try:

            def store():
                with path.open("rb") as source:
                    return self.storage.put_stream(
                        key, source, content_type=mime, max_bytes=maximum
                    )

            async with self.session.begin():
                pending = await self.session.get(
                    SpeakingMediaCleanup, reservation_id, with_for_update=True
                )
                if pending is None:
                    raise failure("SPEAKING_BENCHMARK_UPLOAD_EXPIRED", 409)
                write_task = asyncio.create_task(asyncio.to_thread(store))
                try:
                    written = await asyncio.shield(write_task)
                except asyncio.CancelledError:
                    await asyncio.gather(write_task, return_exceptions=True)
                    raise
                if written != media["size_bytes"]:
                    raise failure("SPEAKING_BENCHMARK_UPLOAD_SIZE")
                row = SpeakingBenchmarkSample(
                    id=sample_id,
                    owner_id=self.owner_id,
                    audio_key=key,
                    source_sha256=media["sha256"],
                    mime_type=mime,
                    byte_size=written,
                    duration_ms=media["duration_ms"],
                    **metadata.model_dump(),
                )
                self.session.add(row)
                await self.session.delete(pending)
                await self.session.flush()
                return await self.sample_dto(row)
        except IntegrityError:
            raise failure("SPEAKING_BENCHMARK_DUPLICATE", 409) from None
        # Failed uploads retain their durable cleanup reservation; a separate worker sweeps it.

    async def audio(self, sample_id):
        async with self.session.begin():
            row = await self.owned(sample_id)
            return row.audio_key, row.mime_type

    async def delete(self, sample_id, expected_revision):
        async with self.session.begin():
            row = await self.owned(sample_id, lock=True)
            check_revision(row.revision, expected_revision)
            from app.models.speaking_benchmark_grading import (
                SpeakingBenchmarkGradingCheckpoint,
                SpeakingBenchmarkGradingRun,
            )

            uncertain_runs = select(SpeakingBenchmarkGradingCheckpoint.run_id).where(SpeakingBenchmarkGradingCheckpoint.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]))
            runs = list(
                await self.session.scalars(
                    select(SpeakingBenchmarkGradingRun)
                    .where(
                        SpeakingBenchmarkGradingRun.sample_id == sample_id,
                        (SpeakingBenchmarkGradingRun.status.in_(["PENDING", "RUNNING", "INTERRUPTED"]) | SpeakingBenchmarkGradingRun.id.in_(uncertain_runs)),
                    )
                    .with_for_update()
                )
            )
            self.session.add(SpeakingMediaCleanup(storage_key=row.audio_key))
            if runs:
                row.deletion_pending_at = datetime.now(UTC)
                for run in runs:
                    if run.status in {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}:
                        continue
                    run.status, run.stage, run.finished_at = (
                        "CANCELLED",
                        "sample_deleted",
                        datetime.now(UTC),
                    )
                    run.lease_token, run.lease_expires_at = None, None
                    for attempt in await self.session.scalars(
                        select(SpeakingBenchmarkGradingCheckpoint).where(
                            SpeakingBenchmarkGradingCheckpoint.run_id == run.id,
                            SpeakingBenchmarkGradingCheckpoint.status == "ATTEMPTED",
                        )
                    ):
                        attempt.status = "INTERRUPTED_BILLING_UNKNOWN"
                for job in await self.session.scalars(
                    select(SpeakingBenchmarkJob).where(
                        SpeakingBenchmarkJob.sample_id == sample_id,
                        SpeakingBenchmarkJob.status.in_(["PENDING", "RUNNING"]),
                    )
                ):
                    job.status, job.stage, job.finished_at = (
                        "CANCELLED",
                        "sample_deleted",
                        datetime.now(UTC),
                    )
                    job.lease_token, job.lease_expires_at = None, None
            else:
                await self.session.delete(row)

    async def review_row(self, sample, revision=None):
        row = await self.session.get(
            SpeakingBenchmarkReview, (sample.id, revision or sample.review_revision)
        )
        if row is None:
            raise failure("SPEAKING_BENCHMARK_REVIEW_NOT_READY", 409)
        job = await self.session.get(SpeakingBenchmarkJob, row.job_id)
        result = DiarizationResult.model_validate(job.result)
        if result.source_sha256 != sample.source_sha256:
            raise failure("REPLAY_APPROVED_SOURCE_CHANGED", 409)
        return row, result

    def review_dto(self, row, result):
        draft = ReviewDraft.model_validate(row.draft)
        return ReviewDTO(
            role_suggestions={
                key: value["suggested_role"] for key, value in suggest_roles(result).items()
            },
            revision=row.revision,
            draft=draft,
            diarization=result,
            approved_at=row.approved_at,
            manifest=row.manifest,
            approval_errors=approval_errors(
                result, draft, self.settings.speaking_max_decoded_seconds * 1000
            ),
        )

    async def review(self, sample_id, revision=None):
        async with self.session.begin():
            row, result = await self.review_row(await self.owned(sample_id), revision)
            return self.review_dto(row, result)

    async def save_review(self, sample_id, body, *, suggestions=False):
        async with self.session.begin():
            sample = await self.owned(sample_id, lock=True)
            check_revision(sample.review_revision, body.expected_revision)
            previous, result = await self.review_row(sample)
            try:
                validate_draft(result, body.draft)
                draft = suggest_windows(result, body.draft) if suggestions else body.draft
            except BenchmarkInputError as error:
                raise failure(str(error)) from None
            if suggestions:
                return draft
            row = SpeakingBenchmarkReview(
                sample_id=sample.id,
                revision=sample.review_revision + 1,
                job_id=previous.job_id,
                draft=draft.model_dump(mode="json"),
            )
            self.session.add(row)
            sample.review_revision = row.revision
            sample.revision += 1
            sample.status = "REVIEW"
            # Keep the last approved artifact fingerprint available; it belongs to its revision.
            await self.session.flush()
            return self.review_dto(row, result)

    async def approve(self, sample_id, expected_revision):
        # Hash original bytes before taking a database lock; storage is immutable by contract.
        key, _ = await self.audio(sample_id)

        def checksum():
            with self.storage.materialize(
                key, max_bytes=self.settings.speaking_benchmark_max_upload_mb * 1024**2
            ) as path:
                return audio_digest(path)

        source_hash = await asyncio.to_thread(checksum)
        async with self.session.begin():
            sample = await self.owned(sample_id, lock=True)
            check_revision(sample.review_revision, expected_revision)
            previous, result = await self.review_row(sample)
            if source_hash != sample.source_sha256:
                raise failure("REPLAY_APPROVED_SOURCE_CHANGED", 409)
            if previous.manifest is not None:
                return self.review_dto(previous, result)
            try:
                manifest = manifest_for_review(
                    result,
                    ReviewDraft.model_validate(previous.draft),
                    self.settings.speaking_max_decoded_seconds * 1000,
                )
            except BenchmarkInputError as error:
                raise failure(str(error)) from None
            serialized = manifest.model_dump(mode="json")
            digest = fingerprint([sample.source_sha256, result.identity, serialized])
            # Approval itself is a new append-only revision, preserving the saved draft too.
            row = SpeakingBenchmarkReview(
                sample_id=sample.id,
                revision=sample.review_revision + 1,
                job_id=previous.job_id,
                draft=previous.draft,
                manifest=serialized,
                approved_by=self.owner_id,
                approved_at=datetime.now(UTC),
                fingerprint=digest,
            )
            self.session.add(row)
            sample.review_revision = row.revision
            sample.approved_fingerprint = digest
            sample.revision += 1
            sample.status = "APPROVED"
            await self.session.flush()
            return self.review_dto(row, result)

    async def labels(self, sample_id):
        async with self.session.begin():
            sample = await self.owned(sample_id)
            row = (
                await self.session.get(
                    SpeakingBenchmarkHumanLabel, (sample.id, sample.label_revision)
                )
                if sample.label_revision
                else None
            )
            return self.label_dto(row)

    @staticmethod
    def label_dto(row):
        if row is None:
            return LabelsDTO()
        return LabelsDTO(
            revision=row.revision,
            bands={
                key: float(getattr(row, key)) if getattr(row, key) is not None else None
                for key in ("fc", "lr", "gra", "pr", "overall")
            },
            **{
                key: getattr(row, key)
                for key in ("provenance", "reference", "verified", "examiner", "notes")
            },
        )

    async def save_labels(self, sample_id, body):
        async with self.session.begin():
            sample = await self.owned(sample_id, lock=True)
            check_revision(sample.label_revision, body.expected_revision)
            row = SpeakingBenchmarkHumanLabel(
                sample_id=sample.id,
                revision=sample.label_revision + 1,
                authored_by=self.owner_id,
                **body.bands.model_dump(),
                **body.model_dump(exclude={"expected_revision", "bands"}),
            )
            self.session.add(row)
            sample.label_revision = row.revision
            sample.revision += 1
            await self.session.flush()
            return self.label_dto(row)

    async def jobs(self, sample_id):
        async with self.session.begin():
            await self.owned(sample_id)
            rows = await self.session.scalars(
                select(SpeakingBenchmarkJob)
                .where(SpeakingBenchmarkJob.sample_id == sample_id)
                .order_by(SpeakingBenchmarkJob.created_at.desc())
                .limit(20)
            )
            return [JobDTO.model_validate(row, from_attributes=True) for row in rows]
