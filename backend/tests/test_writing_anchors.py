import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from tacs_database import disposable_database

from app.core.exceptions import AppError
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models import WritingTask
from app.models.enums import ModuleType, VersionStatus


async def frozen_task(session, number=1, status=VersionStatus.PUBLISHED):
    test = DomainTest(title=f"Fictional anchor task {uuid4()}")
    version = DomainVersion(
        version_number=1,
        status=status,
        published_at=datetime.now(UTC) if status != VersionStatus.DRAFT else None,
    )
    module = DomainModule(module_type=ModuleType.WRITING, order_index=0)
    task = WritingTask(
        task_number=number,
        prompt="Describe fictional data." if number == 1 else "Discuss fictional parks.",
        task_type="pie_chart" if number == 1 else "opinion",
        order_index=0,
    )
    test.versions.append(version)
    version.modules.append(module)
    module.writing_tasks.append(task)
    async with session.begin():
        session.add(test)
        await session.flush()
    return task


def anchor_input(task_id, band=7):
    from app.schemas.writing_anchors import HumanAnchorInput

    return HumanAnchorInput(
        writing_task_id=task_id,
        response_text="Fictional introduction.\n\nFictional details.",
        human_scores=dict(ta=6.5, cc=band, lr=band, gra=band),
    )


@pytest.mark.parametrize("bad", ["6.2", "NaN", "Infinity", "-0.5", "9.5"])
def test_labels_reuse_finite_half_band_validation(bad):
    from app.schemas.writing_anchors import HumanAnchorScores

    with pytest.raises(ValidationError):
        HumanAnchorScores(ta=bad, cc=7, lr=7, gra=7)


async def test_empty_and_versioned_human_bank_preserves_four_labels(db_session):
    from app.services.writing_anchors import WritingAnchorService

    svc = WritingAnchorService(db_session)
    assert (await svc.active_snapshot()).anchors == ()
    empty = await svc.coverage()
    assert all(row.readiness == "EMPTY" for row in empty.production_task1)
    task = await frozen_task(db_session)
    draft = await svc.create_draft(db_session.info["current_user_id"], "Human bank")
    added = await svc.create_anchor(
        db_session.info["current_user_id"], draft.id, anchor_input(task.id)
    )
    assert added.response_text == "Fictional introduction.\n\nFictional details."
    assert added.human_scores.ta == Decimal("6.5")
    assert added.human_scores.cc == Decimal("7")
    assert "feedback" not in added.model_dump() and "overall" not in added.model_dump()
    await svc.activate(db_session.info["current_user_id"], draft.id)
    with pytest.raises(AppError) as error:
        await svc.update_anchor(
            db_session.info["current_user_id"], added.id, anchor_input(task.id, 8)
        )
    assert error.value.status_code == 409
    cloned = await svc.create_draft(db_session.info["current_user_id"], "Human bank")
    assert cloned.version == 2
    rows = await svc.list_anchors(set_id=cloned.id)
    assert rows.total == 1 and rows.items[0].human_scores.ta == Decimal("6.5")
    await svc.activate(db_session.info["current_user_id"], cloned.id)
    sets = await svc.list_sets()
    assert [(item.version, item.status) for item in sets] == [(2, "ACTIVE"), (1, "RETIRED")]
    assert (await svc.snapshot(draft.id)).anchors[0].response_text == added.response_text


async def test_draft_crud_and_frozen_task_picker(db_session):
    from app.services.writing_anchors import WritingAnchorService

    svc = WritingAnchorService(db_session)
    draft_task = await frozen_task(db_session, status=VersionStatus.DRAFT)
    published = await frozen_task(db_session)
    archived = await frozen_task(db_session, 2, VersionStatus.ARCHIVED)
    draft = await svc.create_draft(db_session.info["current_user_id"], "Bank")
    with pytest.raises(AppError):
        await svc.create_anchor(
            db_session.info["current_user_id"], draft.id, anchor_input(draft_task.id)
        )
    options = await svc.list_tasks()
    assert {row.id for row in options.items} == {published.id, archived.id}
    row = await svc.create_anchor(
        db_session.info["current_user_id"], draft.id, anchor_input(published.id)
    )
    edited = await svc.update_anchor(
        db_session.info["current_user_id"], row.id, anchor_input(archived.id, 8)
    )
    assert edited.task.task_number == 2 and edited.human_scores.cc == 8
    await svc.delete_anchor(row.id)
    assert (await svc.list_anchors(set_id=draft.id)).total == 0
    await svc.activate(db_session.info["current_user_id"], draft.id)  # recommendations never block


async def test_language_coverage_is_separate_and_ta_never_gates_readiness(db_session):
    from app.services.writing_anchors import WritingAnchorService

    svc = WritingAnchorService(db_session)
    one, two = await frozen_task(db_session), await frozen_task(db_session, 2)
    draft = await svc.create_draft(db_session.info["current_user_id"], "Bank")
    for task, bands in ((one, (6, 7, 8)), (two, (5, 6))):
        for band in bands:
            await svc.create_anchor(
                db_session.info["current_user_id"], draft.id, anchor_input(task.id, band)
            )
    await svc.activate(db_session.info["current_user_id"], draft.id)
    snapshot = await svc.active_snapshot()
    assert len(snapshot.language_anchors(1, "lr")) == 3
    assert len(snapshot.language_anchors(2, "lr")) == 2
    with pytest.raises(ValueError):
        snapshot.language_anchors(1, "ta")
    coverage = await svc.coverage()
    assert all(
        row.ladder == [6, 7, 8] and row.readiness == "PAIRWISE_USABLE"
        for row in coverage.production_task1
    )
    assert coverage.research_task1_ta[0].counts["6.5"] == 3


async def test_postgresql_blocks_raw_active_anchor_mutations(db_session):
    from app.services.writing_anchors import WritingAnchorService

    svc = WritingAnchorService(db_session)
    task = await frozen_task(db_session)
    draft = await svc.create_draft(db_session.info["current_user_id"], "Bank")
    row = await svc.create_anchor(
        db_session.info["current_user_id"], draft.id, anchor_input(task.id)
    )
    await svc.activate(db_session.info["current_user_id"], draft.id)
    for sql in (
        "UPDATE writing_human_anchors SET cc_score=8 WHERE id=:id",
        "DELETE FROM writing_human_anchors WHERE id=:id",
    ):
        with pytest.raises(DBAPIError):
            async with db_session.begin(), db_session.begin_nested():
                await db_session.execute(text(sql), {"id": row.id})


async def test_activation_waits_for_draft_edit_and_freezes_complete_content():
    from app.models import User
    from app.models.enums import UserRole
    from app.services.writing_anchors import WritingAnchorService

    async with disposable_database() as (engine, _):
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            async with session.begin():
                user = User(
                    email=f"{uuid4()}@example.com",
                    display_name="Synthetic admin",
                    role=UserRole.ADMIN,
                    is_active=True,
                )
                session.add(user)
                await session.flush()
            task = await frozen_task(session)
            svc = WritingAnchorService(session)
            draft = await svc.create_draft(user.id, "Bank")
            row = await svc.create_anchor(user.id, draft.id, anchor_input(task.id))
        async with factory() as editor, factory() as activator:
            async with editor.begin():
                await editor.execute(
                    text("UPDATE writing_human_anchors SET cc_score=8 WHERE id=:id"), {"id": row.id}
                )
                started = asyncio.Event()

                async def activate():
                    started.set()
                    return await WritingAnchorService(activator).activate(user.id, draft.id)

                pending = asyncio.create_task(activate())
                await started.wait()
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(pending), 0.1)
            await asyncio.wait_for(pending, 5)
        async with factory() as session:
            assert (await WritingAnchorService(session).active_snapshot()).anchors[
                0
            ].human_scores.cc == 8
