from decimal import Decimal

import pytest
from teacher_helpers import api_client, make_user
from test_writing_benchmark_api import ROOT

from app.models import WritingBenchmarkSample
from app.models.enums import UserRole


async def summary(session):
    async with api_client(session, session.info["current_user_identity"]) as client:
        response = await client.get(ROOT + "/summary")
        assert response.status_code == 200
        return response.json()


async def test_empty_summary_advisory_targets(db_session):
    bank = await summary(db_session)
    assert len(bank["tasks"]) == 2
    for task in bank["tasks"]:
        assert (task["total"], task["draft"], task["complete"], task["capacity"]) == (0, 0, 0, 100)
        assert task["split_counts"] == {"DEV": 0, "HOLDOUT": 0}
        assert task["split_targets"] == {"DEV": 80, "HOLDOUT": 20}
        bins = task["overall_distribution"]
        assert len(bins) == 19 and sum(b["suggested"] or 0 for b in bins) == 100
        assert [b["suggested"] for b in bins if b["band"] >= 4] == [
            8,
            8,
            9,
            10,
            11,
            12,
            12,
            10,
            8,
            6,
            6,
        ]
        assert all(b["suggested"] is None for b in bins if b["band"] < 4)
        assert all(b["actual"] == 0 for b in bins)


async def test_complete_only_distribution_all_legal_bands_and_task_isolation(db_session):
    async with db_session.begin():
        db_session.add(
            WritingBenchmarkSample(
                task_number=1,
                sequence_number=1,
                split="HOLDOUT",
                human_ta_tr=9,
                human_cc=9,
                human_lr=9,
                human_gra=9,
            )
        )
        for i in range(19):
            band = Decimal(i) / 2
            db_session.add(
                WritingBenchmarkSample(
                    task_number=2,
                    sequence_number=i + 1,
                    status="COMPLETE",
                    split="DEV" if i < 15 else "HOLDOUT",
                    prompt="Fictional prompt",
                    essay="Fictional essay",
                    human_ta_tr=band,
                    human_cc=band,
                    human_lr=band,
                    human_gra=band,
                )
            )
        db_session.add(
            WritingBenchmarkSample(
                task_number=2,
                sequence_number=20,
                status="COMPLETE",
                prompt="Fictional tie",
                essay="Fictional essay",
                human_ta_tr=6,
                human_cc=6,
                human_lr=6.5,
                human_gra=6.5,
            )
        )
    bank = await summary(db_session)
    first, second = bank["tasks"]
    assert (first["total"], first["draft"], first["complete"]) == (1, 1, 0)
    assert first["split_counts"]["HOLDOUT"] == 0
    assert (second["total"], second["draft"], second["complete"]) == (20, 0, 20)
    assert second["split_counts"] == {"DEV": 16, "HOLDOUT": 4}
    assert [b["actual"] for b in second["overall_distribution"]] == [
        2 if i == 13 else 1 for i in range(19)
    ]
    assert not any(
        secret in str(bank) for secret in ("Fictional prompt", "Fictional essay", "task1_image_key")
    )


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.TEACHER])
async def test_summary_requires_admin(db_session, role):
    actor = await make_user(db_session, role)
    async with api_client(db_session, actor) as client:
        assert (await client.get(ROOT + "/summary")).status_code == 403
