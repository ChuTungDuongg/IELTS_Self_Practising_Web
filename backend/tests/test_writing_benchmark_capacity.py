import asyncio

import pytest
from benchmark_helpers import isolated_bank
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models import WritingBenchmarkSample
from app.schemas.writing_benchmark import BenchmarkMutation, BenchmarkSampleCreate
from app.services.writing_benchmark import WritingBenchmarkService


async def attempt_create(sessions, task=1):
    async with sessions() as session:
        try:
            return await WritingBenchmarkService(session).create(
                BenchmarkSampleCreate(task_number=task)
            )
        except AppError as error:
            return error


@pytest.mark.parametrize("initial", [0, 99])
async def test_independent_connections_serialize_capacity(initial):
    async with isolated_bank() as (_, sessions):
        async with sessions() as session:
            async with session.begin():
                session.add_all(
                    [
                        WritingBenchmarkSample(task_number=1, sequence_number=i)
                        for i in range(1, initial + 1)
                    ]
                )
        results = await asyncio.gather(attempt_create(sessions), attempt_create(sessions))
        good = [r for r in results if not isinstance(r, AppError)]
        if initial == 0:
            assert {r.sequence_number for r in good} == {1, 2}
            assert len({r.id for r in good}) == 2
        else:
            assert len(good) == 1 and good[0].sequence_number == 100
            assert [r.code for r in results if isinstance(r, AppError)] == [
                "BENCHMARK_CAPACITY_REACHED"
            ]
        async with sessions() as session:
            assert await session.scalar(
                select(func.count()).select_from(WritingBenchmarkSample)
            ) == initial + len(good)


async def test_drafts_count_hole_reuse_new_uuid_and_other_task_independence():
    async with isolated_bank() as (_, sessions):
        async with sessions() as session:
            service = WritingBenchmarkService(session)
            async with session.begin():
                session.add_all(
                    [
                        WritingBenchmarkSample(task_number=1, sequence_number=i)
                        for i in range(1, 101)
                    ]
                )
            with pytest.raises(AppError, match="100 samples"):
                await service.create(BenchmarkSampleCreate(task_number=1))
            rows = await service.list(1)
            deleted = rows[36]
            await service.delete(deleted.id, BenchmarkMutation(expected_revision=deleted.revision))
            new = await service.create(BenchmarkSampleCreate(task_number=1))
            assert new.code == "T1-037" and new.id != deleted.id
            assert (await service.list(1))[37].code == "T1-038"
            assert (await service.create(BenchmarkSampleCreate(task_number=2))).code == "T2-001"
