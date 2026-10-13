from decimal import Decimal
from uuid import uuid4

import pytest
from benchmark_helpers import isolated_bank
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Base, WritingBenchmarkSample
from app.repositories.writing_benchmark import WritingBenchmarkRepository


def test_ground_truth_model_registered_with_named_constraints():
    table = Base.metadata.tables["writing_benchmark_samples"]
    assert "human_overall" not in table.c
    assert {"task_number", "sequence_number", "revision", "human_ta_tr"} <= set(table.c.keys())
    assert all(constraint.name for constraint in table.constraints)
    assert table.c.human_cc.type.scale is None  # Do not round 6.49 to a valid 6.5.
    assert WritingBenchmarkSample(task_number=1, sequence_number=37).code == "T1-037"


@pytest.mark.parametrize(
    "changes",
    [
        {"task_number": 3},
        {"sequence_number": 101},
        {"sequence_number": 0},
        {"human_cc": Decimal("6.3")},
        {"human_lr": Decimal("6.49")},
        {"human_gra": Decimal("9.5")},
        {"revision": -1},
        {"status": "COMPLETE"},
        {"task1_task_type": "OPINION"},
        {"task_number": 2, "task1_task_type": "PIE_CHART"},
        {"task_number": 2, "task1_image_key": "private.png"},
    ],
)
async def test_database_rejects_invalid_ground_truth(changes):
    async with isolated_bank() as (_, sessions):
        async with sessions() as session:
            with pytest.raises(IntegrityError):
                async with session.begin():
                    session.add(
                        WritingBenchmarkSample(
                            task_number=changes.get("task_number", 1),
                            sequence_number=changes.get("sequence_number", 1),
                            **{
                                k: v
                                for k, v in changes.items()
                                if k not in {"task_number", "sequence_number"}
                            },
                        )
                    )
                    await session.flush()


async def test_slots_unique_partial_drafts_and_gap_reuse():
    async with isolated_bank() as (_, sessions):
        async with sessions() as session:
            repo = WritingBenchmarkRepository(session)
            async with session.begin():
                await repo.lock_task_capacity(1)
                for number in (1, 2, 4):
                    session.add(WritingBenchmarkSample(task_number=1, sequence_number=number))
                await session.flush()
                assert await repo.allocate_slot(1) == 3
            with pytest.raises(IntegrityError):
                async with session.begin():
                    session.add(WritingBenchmarkSample(task_number=1, sequence_number=1))
                    await session.flush()
            async with session.begin():
                old = await session.scalar(
                    text("SELECT id FROM writing_benchmark_samples WHERE sequence_number=2")
                )
                await session.execute(
                    text("DELETE FROM writing_benchmark_samples WHERE sequence_number=2")
                )
                assert await repo.allocate_slot(1) == 2
                new = WritingBenchmarkSample(id=uuid4(), task_number=1, sequence_number=2)
                session.add(new)
                assert new.id != old
                assert [r.sequence_number for r in await repo.list_rows(1)] == [1, 2, 4]
