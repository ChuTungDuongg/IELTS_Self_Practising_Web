from sqlalchemy import text
from tacs_database import disposable_database, migrate


async def test_anchor_schema_constraints_and_empty_tables(db_session):
    async with db_session.begin():
        tables = set(
            await db_session.scalars(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        )
        assert {"writing_anchor_sets", "writing_human_anchors"} <= tables
        assert await db_session.scalar(text("SELECT count(*) FROM writing_human_anchors")) == 0
        guards = set(
            await db_session.scalars(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"))
        )
        assert {"writing_anchor_content_immutable", "writing_anchor_set_immutable"} <= guards


async def test_real_upgrade_downgrade_upgrade_preserves_preexisting_tables():
    async with disposable_database() as (engine, url):
        await migrate(url, "downgrade", "20261008_0020")
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT to_regclass('writing_anchor_sets')")) is None
            )
            assert (
                await connection.scalar(text("SELECT to_regclass('writing_ai_grading_runs')"))
                is not None
            )
        await migrate(url, "upgrade", "head")
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM writing_human_anchors")) == 0
            columns = set(
                await connection.scalars(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name='writing_ai_grading_runs'"
                    )
                )
            )
            assert {
                "execution_config_json",
                "anchor_set_id",
                "scoring_architecture",
                "scoring_diagnostics_json",
            } <= columns
        await migrate(url, "downgrade", "20261008_0021")
        await migrate(url, "upgrade", "head")


async def test_source_migration_preserves_existing_frozen_builder_anchors():
    from uuid import uuid4

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from test_writing_anchors import anchor_input, frozen_task

    from app.models import User
    from app.models.enums import UserRole
    from app.services.writing_anchors import WritingAnchorService

    async with disposable_database() as (engine, url):
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            admin = User(
                email=f"{uuid4()}@example.com",
                display_name="Fixture admin",
                role=UserRole.ADMIN,
                is_active=True,
            )
            async with session.begin():
                session.add(admin)
                await session.flush()
            task = await frozen_task(session)
            svc = WritingAnchorService(session)
            bank = await svc.create_draft(admin.id, "Preserved bank")
            original = await svc.create_anchor(admin.id, bank.id, anchor_input(task.id))
            await svc.activate(admin.id, bank.id)
            working = await svc.begin_edit(admin.id)
        await migrate(url, "downgrade", "20261008_0022")
        await migrate(url, "upgrade", "head")
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            restored = await WritingAnchorService(session).get_anchor(original.id)
            assert restored == original and restored.source_kind == "BUILDER_TASK"
            snapshot = await WritingAnchorService(session).snapshot(bank.id)
            assert snapshot.anchors[0].writing_task_id == task.id
            state = await WritingAnchorService(session).bank_state()
            assert state.working.id == working.id and state.working_count == 1
            applied = await WritingAnchorService(session).activate(admin.id, working.id)
            assert applied.status == "ACTIVE" and applied.version == 2


async def test_source_downgrade_refuses_to_erase_custom_anchors():
    from uuid import uuid4

    import pytest
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from test_anchor_source_lifecycle import custom_input

    from app.models import User
    from app.models.enums import UserRole
    from app.services.writing_anchors import WritingAnchorService

    async with disposable_database() as (engine, url):
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            admin = User(
                email=f"{uuid4()}@example.com",
                display_name="Fixture admin",
                role=UserRole.ADMIN,
                is_active=True,
            )
            async with session.begin():
                session.add(admin)
                await session.flush()
            svc = WritingAnchorService(session)
            working = await svc.begin_edit(admin.id)
            original = await svc.create_anchor(admin.id, working.id, custom_input())
            await svc.activate(admin.id, working.id)
        with pytest.raises(AssertionError, match="Cannot downgrade while custom anchors exist"):
            await migrate(url, "downgrade", "20261008_0022")
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            assert (await WritingAnchorService(session).get_anchor(original.id)) == original
