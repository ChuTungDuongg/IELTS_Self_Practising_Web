"""Admin ground-truth lifecycle; no learner records or provider calls."""

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
    BenchmarkCompletionFailure,
    BenchmarkFieldIssue,
    BenchmarkMutation,
    BenchmarkSampleCreate,
    BenchmarkSampleDetail,
    BenchmarkSampleListItem,
    BenchmarkSamplePatch,
)
from app.services.draft_revisions import advance_revision
from app.storage import LocalAssetStorage

SCORE_MAP = {"cc": "human_cc", "lr": "human_lr", "gra": "human_gra"}


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
                if not owns_image_key(row.id, row.task1_image_key):
                    raise BenchmarkInputError("BENCHMARK_IMAGE_INVALID")
                load_image(self.storage.resolve(row.task1_image_key))
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
            await self.session.delete(row)
