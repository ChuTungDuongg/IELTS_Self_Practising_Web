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
