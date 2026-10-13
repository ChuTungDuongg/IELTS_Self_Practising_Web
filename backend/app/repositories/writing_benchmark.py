from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.enums import WritingBenchmarkStatus
from app.models.writing_benchmark import SCORE_FIELDS, WritingBenchmarkSample

# Dedicated transaction-level namespace, with independent locks for each task.
CAPACITY_LOCK_NAMESPACE = 0x57424B


class WritingBenchmarkRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_task_capacity(self, task_number: int) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :task)"),
            {"namespace": CAPACITY_LOCK_NAMESPACE, "task": task_number},
        )

    async def allocate_slot(self, task_number: int) -> int:
        occupied = set(
            await self.session.scalars(
                select(WritingBenchmarkSample.sequence_number).where(
                    WritingBenchmarkSample.task_number == task_number
                )
            )
        )
        for number in range(1, 101):
            if number not in occupied:
                return number
        raise AppError("BENCHMARK_CAPACITY_REACHED", "This task already has 100 samples.", 409)

    async def get(self, sample_id: UUID, *, lock: bool = False):
        query = select(WritingBenchmarkSample).where(WritingBenchmarkSample.id == sample_id)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query.execution_options(populate_existing=True))

    async def list_rows(self, task_number: int):
        model = WritingBenchmarkSample
        columns = [
            getattr(model, field)
            for field in (
                "id",
                "task_number",
                "sequence_number",
                "status",
                "split",
                *SCORE_FIELDS,
                "revision",
                "created_at",
                "updated_at",
            )
        ]
        query = (
            select(*columns, model.task1_image_key.is_not(None).label("has_image"))
            .where(model.task_number == task_number)
            .order_by(model.sequence_number)
        )
        return (await self.session.execute(query)).all()

    async def complete_rows(self, *, lock_shared: bool = False):
        query = (
            select(WritingBenchmarkSample)
            .where(WritingBenchmarkSample.status == WritingBenchmarkStatus.COMPLETE)
            .order_by(WritingBenchmarkSample.task_number, WritingBenchmarkSample.sequence_number)
        )
        if lock_shared:
            query = query.with_for_update(read=True)
        return list(await self.session.scalars(query.execution_options(populate_existing=True)))

    async def summary_labels(self):
        return (
            await self.session.execute(
                select(
                    WritingBenchmarkSample.task_number,
                    WritingBenchmarkSample.status,
                    WritingBenchmarkSample.split,
                    *(getattr(WritingBenchmarkSample, field) for field in SCORE_FIELDS),
                )
            )
        ).all()
