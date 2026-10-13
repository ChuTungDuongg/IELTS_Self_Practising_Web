"""Admin ground-truth lifecycle; no learner records or provider calls."""

import logging
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.domains.writing.task_types import TASK_ONE_TYPES
from app.evaluation.task1.manifest import BenchmarkInputError, load_image
from app.evaluation.writing.metrics import overall_score
from app.models.enums import WritingBenchmarkStatus
from app.models.writing_benchmark import WritingBenchmarkSample
from app.repositories.writing_benchmark import WritingBenchmarkRepository
from app.schemas.writing_benchmark import (
    BenchmarkBankSummary,
    BenchmarkCompletionFailure,
    BenchmarkFieldIssue,
    BenchmarkMutation,
    BenchmarkSampleCreate,
    BenchmarkSampleDetail,
    BenchmarkSampleListItem,
    BenchmarkSamplePatch,
    BenchmarkTaskSummary,
)
from app.services.draft_revisions import advance_revision
from app.storage import LocalAssetStorage

SCORE_MAP = {"cc": "human_cc", "lr": "human_lr", "gra": "human_gra"}
logger = logging.getLogger(__name__)
SUGGESTED_OVERALL = dict(
    zip([4 + i / 2 for i in range(11)], [8, 8, 9, 10, 11, 12, 12, 10, 8, 6, 6], strict=True)
)


def owns_image_key(sample_id: UUID, key: str | None) -> bool:
    return bool(
        key
        and re.fullmatch(
            rf"benchmark/writing/task1/{sample_id}/[0-9a-f]{{32}}\.(png|jpg|webp)", key
        )
    )


def scores(row):
    first = "ta" if row.task_number == 1 else "tr"
    return {
        first: row.human_ta_tr,
        **{key: getattr(row, field) for key, field in SCORE_MAP.items()},
    }


def overall(row):
    values = scores(row)
    return overall_score(values, traits=tuple(values))


def completion_issues(row: WritingBenchmarkSample) -> list[BenchmarkFieldIssue]:
    issues = []
    for field in ("prompt", "essay"):
        if not getattr(row, field).strip():
            issues.append(BenchmarkFieldIssue(path=field, message="This field is required."))
    for trait, value in scores(row).items():
        if value is None:
            issues.append(
                BenchmarkFieldIssue(
                    path=f"human_scores.{trait}", message="Select a half-band score."
                )
            )
    if row.task_number == 1:
        if row.task1_task_type not in TASK_ONE_TYPES:
            issues.append(
                BenchmarkFieldIssue(path="task1_task_type", message="Select a Task 1 type.")
            )
        if not row.task1_image_key:
            issues.append(
                BenchmarkFieldIssue(path="image", message="Upload a valid private image.")
            )
    return issues


def present(row, *, detail=True):
    values = scores(row)
    band = overall(row)
    common = dict(
        id=row.id,
        code=f"T{row.task_number}-{row.sequence_number:03d}",
        task_number=row.task_number,
        sequence_number=row.sequence_number,
        status=row.status,
        split=row.split,
        human_scores={
            key: float(value) if value is not None else None for key, value in values.items()
        },
        human_overall=float(band) if band is not None else None,
        has_image=bool(row.task1_image_key) if detail else row.has_image,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    if not detail:
        return BenchmarkSampleListItem(**common)
    return BenchmarkSampleDetail(
        **common,
        prompt=row.prompt,
        essay=row.essay,
        task1_task_type=row.task1_task_type,
        source_note=row.source_note,
        redistributable=row.redistributable,
    )


class WritingBenchmarkService:
    def __init__(self, session: AsyncSession, storage: LocalAssetStorage | None = None):
        self.session = session
        self.repo = WritingBenchmarkRepository(session)
        self.storage = storage or LocalAssetStorage(get_settings().resolved_storage_root)

    async def _get(self, sample_id, *, lock=False):
        row = await self.repo.get(sample_id, lock=lock)
        if row is None:
            raise AppError(
                "BENCHMARK_SAMPLE_NOT_FOUND", "The benchmark sample does not exist.", 404
            )
        return row

    def _completion_issues(self, row):
        issues = completion_issues(row)
        if row.task_number == 1 and row.task1_image_key:
            try:
                load_image(self.owned_image_path(row.id, row.task1_image_key))
            except (AppError, BenchmarkInputError):
                issues.append(
                    BenchmarkFieldIssue(path="image", message="Upload a valid private image.")
                )
        return issues

    async def create(self, body: BenchmarkSampleCreate):
        async with self.session.begin():
            await self.repo.lock_task_capacity(body.task_number)
            row = WritingBenchmarkSample(
                task_number=body.task_number,
                sequence_number=await self.repo.allocate_slot(body.task_number),
            )
            self.session.add(row)
            await self.session.flush()
            return present(row)

    async def detail(self, sample_id):
        async with self.session.begin():
            return present(await self._get(sample_id))

    async def list(self, task_number):
        async with self.session.begin():
            return [present(row, detail=False) for row in await self.repo.list_rows(task_number)]

    async def summary(self):
        async with self.session.begin():
            rows = await self.repo.summary_labels()
        tasks = []
        for number in (1, 2):
            selected = [row for row in rows if row.task_number == number]
            complete = [row for row in selected if row.status == WritingBenchmarkStatus.COMPLETE]
            bands = [float(overall(row)) for row in complete]
            tasks.append(
                BenchmarkTaskSummary(
                    task_number=number,
                    total=len(selected),
                    draft=len(selected) - len(complete),
                    complete=len(complete),
                    split_counts={
                        split: sum(row.split == split for row in complete)
                        for split in ("DEV", "HOLDOUT")
                    },
                    split_targets={"DEV": 80, "HOLDOUT": 20},
                    overall_distribution=[
                        dict(
                            band=i / 2,
                            actual=bands.count(i / 2),
                            suggested=SUGGESTED_OVERALL.get(i / 2),
                        )
                        for i in range(19)
                    ],
                )
            )
        return BenchmarkBankSummary(tasks=tasks)

    async def patch(self, sample_id, body: BenchmarkSamplePatch):
        async with self.session.begin():
            row = await self._get(sample_id, lock=True)
            advance_revision(row, body.expected_revision)
            edits = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
            if "task1_task_type" in edits and row.task_number != 1:
                raise AppError("BENCHMARK_TASK_MISMATCH", "Task 2 samples are text only.", 422)
            labels = edits.pop("human_scores", {})
            first = "ta" if row.task_number == 1 else "tr"
            if any(trait not in {first, *SCORE_MAP} for trait in labels):
                raise AppError(
                    "BENCHMARK_TASK_MISMATCH", "The criterion does not belong to this task.", 422
                )
            for trait, value in labels.items():
                setattr(row, "human_ta_tr" if trait == first else SCORE_MAP[trait], value)
            for field, value in edits.items():
                setattr(row, field, value)
            if row.status == WritingBenchmarkStatus.COMPLETE and self._completion_issues(row):
                row.status = WritingBenchmarkStatus.DRAFT
            await self.session.flush()
            await self.session.refresh(row)
            return present(row)

    async def complete(self, sample_id, body: BenchmarkMutation):
        async with self.session.begin():
            row = await self._get(sample_id, lock=True)
            advance_revision(row, body.expected_revision)
            issues = self._completion_issues(row)
            if issues:
                raise BenchmarkCompletionFailure(issues)
            row.status = WritingBenchmarkStatus.COMPLETE
            await self.session.flush()
            await self.session.refresh(row)
            return present(row)

    async def delete(self, sample_id, body: BenchmarkMutation):
        async with self.session.begin():
            task = await self.session.scalar(
                select(WritingBenchmarkSample.task_number).where(
                    WritingBenchmarkSample.id == sample_id
                )
            )
            if task is None:
                raise AppError(
                    "BENCHMARK_SAMPLE_NOT_FOUND", "The benchmark sample does not exist.", 404
                )
            await self.repo.lock_task_capacity(task)
            row = await self._get(sample_id, lock=True)
            advance_revision(row, body.expected_revision)
            old_key = row.task1_image_key
            await self.session.delete(row)
        self._cleanup_image(sample_id, old_key)

    def owned_image_path(self, sample_id, key):
        if not owns_image_key(sample_id, key):
            raise AppError("BENCHMARK_IMAGE_NOT_FOUND", "The private image is unavailable.", 404)
        candidate = self.storage.root / key
        # Reject symlinks even when they point to another file within storage.
        if candidate.resolve() != candidate:
            raise AppError("BENCHMARK_IMAGE_NOT_FOUND", "The private image is unavailable.", 404)
        return self.storage.resolve(key)

    def _cleanup_image(self, sample_id, key):
        if not key:
            return
        try:
            self.owned_image_path(sample_id, key)
            self.storage.delete(key)
        except (AppError, OSError):
            logger.warning("BENCHMARK_IMAGE_CLEANUP_UNAVAILABLE")

    async def replace_image(self, sample_id, body, mime_type, original_name, content):
        new_key = None
        committing = False
        try:
            async with self.session.begin():
                row = await self._get(sample_id, lock=True)
                if row.task_number != 1:
                    raise AppError("BENCHMARK_TASK_MISMATCH", "Task 2 samples are text only.", 422)
                advance_revision(row, body.expected_revision)
                old_key = row.task1_image_key
                maximum = min(get_settings().max_image_upload_mb, 10) * 1024 * 1024
                stored = self.storage.store_benchmark_writing_image(
                    sample_id, mime_type, original_name, content, maximum
                )
                new_key = stored.relative_path
                row.task1_image_key = new_key
                await self.session.flush()
                await self.session.refresh(row)
                response = present(row)
                # Once commit starts, a lost ACK is not proof that the image is
                # uncommitted. Retain it on uncertain errors/cancellation.
                committing = True
        except BaseException:
            if new_key and not committing:
                self._cleanup_image(sample_id, new_key)
            raise
        self._cleanup_image(sample_id, old_key)
        return response

    async def remove_image(self, sample_id, body):
        async with self.session.begin():
            row = await self._get(sample_id, lock=True)
            if row.task_number != 1:
                raise AppError("BENCHMARK_TASK_MISMATCH", "Task 2 samples are text only.", 422)
            advance_revision(row, body.expected_revision)
            old_key = row.task1_image_key
            row.task1_image_key = None
            row.status = WritingBenchmarkStatus.DRAFT
            await self.session.flush()
            await self.session.refresh(row)
            response = present(row)
        self._cleanup_image(sample_id, old_key)
        return response

    async def image_content(self, sample_id):
        async with self.session.begin():
            row = await self._get(sample_id, lock=True)
            path = self.owned_image_path(sample_id, row.task1_image_key)
            try:
                image = load_image(path)
            except BenchmarkInputError:
                raise AppError(
                    "BENCHMARK_IMAGE_NOT_FOUND", "The private image is unavailable.", 404
                ) from None
            # Copy bounded bytes while the row lock prevents replacement/deletion;
            # the HTTP response never races a later unlink of the source file.
            return image.data, image.mime_type, row.code + path.suffix
