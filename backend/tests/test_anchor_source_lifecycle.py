from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_writing_anchors import anchor_input, frozen_task

from app.core.exceptions import AppError
from app.schemas.writing_anchors import HumanAnchorInput
from app.services.writing_anchors import WritingAnchorService


def custom_input(number=1, band=7, **changes):
    return HumanAnchorInput(
        **{
            "source_kind": "CUSTOM_TASK",
            "task_number": number,
            "custom_prompt": "Describe a fictional chart."
            if number == 1
            else "Discuss fictional gardens.",
            "custom_task_type": "BAR_CHART" if number == 1 else "OPINION",
            "response_text": "Fictional introduction.\n\nFictional details.",
            "human_scores": {"ta": 6.5, "cc": band, "lr": band, "gra": band},
            "provenance": "Administrator-authored fictional fixture",
            "admin_note": "Private note",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"writing_task_id": uuid4()},
        {"task_number": None},
        {"custom_prompt": " "},
        {"custom_prompt": None},
        {"custom_task_type": "OPINION"},
        {"custom_task_type": "unknown"},
        {"human_scores": {"ta": 7, "cc": 6.2, "lr": 7, "gra": 7}},
    ],
)
def test_custom_source_rejects_incoherent_or_invalid_data(changes):
    with pytest.raises(ValidationError):
        custom_input(**changes)


def test_builder_source_rejects_custom_fields():
    with pytest.raises(ValidationError):
        HumanAnchorInput(**{**anchor_input(uuid4()).model_dump(), "custom_prompt": "Mixed source"})


@pytest.mark.parametrize("number", [1, 2])
async def test_standalone_source_persists_without_a_builder_task(db_session, number):
    svc = WritingAnchorService(db_session)
    admin = db_session.info["current_user_id"]
    working = await svc.begin_edit(admin)
    body = custom_input(number)
    added = await svc.create_anchor(admin, working.id, body)
    assert added.source_kind == "CUSTOM_TASK" and added.task.id is None
    assert added.task.task_number == number and added.custom_prompt == body.custom_prompt
    assert added.response_text == body.response_text
    assert added.human_scores.ta == Decimal("6.5")
    assert added.provenance == body.provenance and added.admin_note == body.admin_note
    assert (await svc.list_anchors(set_id=working.id, task_number=number)).total == 1
    assert (
        await svc.list_anchors(set_id=working.id, search="chart" if number == 1 else "gardens")
    ).total == 1
    assert (await svc.list_anchors(set_id=working.id, task_type=body.custom_task_type)).total == 1
    for band in (6, 8):
        await svc.create_anchor(admin, working.id, custom_input(number, band))
    preview = await svc.coverage(set_id=working.id)
    assert preview.active_set is None and preview.evaluated_set.id == working.id
    await svc.activate(admin, working.id)
    snapshot = await svc.active_snapshot()
    assert all(
        row.writing_task_id is None and row.test_version_id is None for row in snapshot.anchors
    )
    assert snapshot.anchors[0].prompt == body.custom_prompt
    with pytest.raises(ValueError):
        snapshot.language_anchors(1, "ta")
    coverage = await svc.coverage()
    assert all(
        row.ladder == ([6, 7, 8] if number == 1 else []) for row in coverage.production_task1
    )
    assert len(coverage.research_task1_ta) == (3 if number == 1 else 0)
    assert coverage.research_task2[0].counts["6.5"] == (3 if number == 2 else 0)


async def test_source_replacement_clears_the_other_sources_fields(db_session):
    svc = WritingAnchorService(db_session)
    admin = db_session.info["current_user_id"]
    task = await frozen_task(db_session)
    working = await svc.begin_edit(admin)
    added = await svc.create_anchor(admin, working.id, anchor_input(task.id))
    custom = await svc.update_anchor(admin, added.id, custom_input())
    assert custom.task.id is None and custom.custom_prompt
    builder = await svc.update_anchor(admin, added.id, anchor_input(task.id))
    assert builder.source_kind == "BUILDER_TASK" and builder.task.id == task.id
    assert builder.custom_prompt is None
    async with db_session.begin():
        values = (
            await db_session.execute(
                text(
                    "SELECT task_number, custom_prompt, custom_task_type FROM writing_human_anchors WHERE id=:id"
                ),
                {"id": added.id},
            )
        ).one()
    assert tuple(values) == (None, None, None)


async def test_language_coverage_pools_builder_and_custom_prompts_and_types(db_session):
    svc = WritingAnchorService(db_session)
    admin = db_session.info["current_user_id"]
    builder = await frozen_task(db_session)
    working = await svc.begin_edit(admin)
    await svc.create_anchor(admin, working.id, anchor_input(builder.id, 6))
    await svc.create_anchor(admin, working.id, custom_input(band=7))
    await svc.create_anchor(
        admin,
        working.id,
        custom_input(
            band=8, custom_prompt="Describe another fictional map.", custom_task_type="MAP_PLAN"
        ),
    )
    await svc.create_anchor(admin, working.id, custom_input(number=2, band=9))
    await svc.activate(admin, working.id)
    snapshot = await svc.active_snapshot()
    assert len(snapshot.language_anchors(1, "cc")) == 3
    assert {row.source_kind for row in snapshot.language_anchors(1, "lr")} == {
        "BUILDER_TASK",
        "CUSTOM_TASK",
    }
    coverage = await svc.coverage()
    for row in coverage.production_task1:
        assert row.ladder == [6, 7, 8] and row.readiness == "PAIRWISE_USABLE"
        assert [row.counts[str(band)] for band in (6, 7, 8, 9)] == [1, 1, 1, 0]


async def test_copy_on_write_apply_cancel_and_logical_delete(db_session):
    svc = WritingAnchorService(db_session)
    admin = db_session.info["current_user_id"]
    original = await svc.begin_edit(admin)
    first = await svc.create_anchor(admin, original.id, custom_input())
    await svc.activate(admin, original.id)
    frozen = await svc.snapshot(original.id)
    working = await svc.begin_edit(admin)
    assert working.version == 2
    assert (await svc.begin_edit(admin)).id == working.id  # resumable shared working copy
    copied = (await svc.list_anchors(set_id=working.id)).items[0]
    assert copied.id != first.id and copied.source_kind == "CUSTOM_TASK"
    await svc.update_anchor(admin, copied.id, custom_input(band=8))
    added = await svc.create_anchor(admin, working.id, custom_input(band=6))
    await svc.delete_anchor(added.id)
    assert await svc.snapshot(original.id) == frozen
    await svc.activate(admin, working.id)
    assert (await svc.active_snapshot()).anchors[0].human_scores.cc == 8
    assert await svc.snapshot(original.id) == frozen
    canceled = await svc.begin_edit(admin)
    await svc.create_anchor(admin, canceled.id, custom_input(band=9))
    await svc.discard_working(canceled.id)
    state = await svc.bank_state()
    assert state.working is None and state.current.id == working.id and state.current_count == 1
    with pytest.raises(AppError):
        await svc.discard_working(working.id)
    pending = await svc.begin_edit(admin)
    await svc.deactivate(working.id)
    assert (await svc.active_snapshot()).anchors == ()
    assert (await svc.bank_state()).working is None
    assert (await svc.snapshot(working.id)).anchors[0].human_scores.cc == 8
    assert await svc.snapshot(original.id) == frozen
    with pytest.raises(AppError):
        await svc.activate(admin, pending.id)  # deactivation discards unapplied work
    with pytest.raises(AppError):
        await svc.deactivate(working.id)  # stale requests cannot delete a replacement
    new = await svc.begin_edit(admin)
    assert new.version == 3 and (await svc.list_anchors(set_id=new.id)).total == 0


@pytest.mark.parametrize(
    "field,value", [("task_number", None), ("writing_task_id", uuid4()), ("custom_prompt", " ")]
)
async def test_database_enforces_custom_source_coherence(db_session, field, value):
    svc = WritingAnchorService(db_session)
    admin = db_session.info["current_user_id"]
    working = await svc.begin_edit(admin)
    added = await svc.create_anchor(admin, working.id, custom_input())
    with pytest.raises(DBAPIError):
        async with db_session.begin(), db_session.begin_nested():
            await db_session.execute(
                text(f"UPDATE writing_human_anchors SET {field}=:value WHERE id=:id"),
                {"value": value, "id": added.id},
            )
