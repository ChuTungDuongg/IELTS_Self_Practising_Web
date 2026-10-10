"""Execute the actual revision against PostgreSQL within the test rollback boundary."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_focused_attempts import content, request

from app.models.enums import ModuleType
from app.services.attempts import AttemptService


def revision():
    path = Path(__file__).parents[1] / "alembic/versions/20261010_0021_focused_attempt_scope.py"
    spec = importlib.util.spec_from_file_location("focused_scope_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def migrate(session, direction):
    def run(sync_session):
        context = MigrationContext.configure(sync_session.connection())
        with Operations.context(context):
            getattr(revision(), direction)()

    await session.run_sync(run)


@pytest.mark.integration
async def test_real_migration_preserves_historical_rows_and_server_defaults(db_session):
    version, _ = await content(db_session)
    service = AttemptService(db_session)
    historical = await service.start(request(version, ModuleType.READING))
    async with db_session.begin():
        await migrate(db_session, "downgrade")
        assert (
            await db_session.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'attempts' AND column_name = 'scope'"
                )
            )
            == 0
        )
        await migrate(db_session, "upgrade")
        row = (
            await db_session.execute(
                text(
                    "SELECT scope, focused_reading_passage_id, focused_listening_part_id, focused_writing_task_id FROM attempts WHERE id = :id"
                ),
                {"id": historical.attempt_id},
            )
        ).one()
        assert tuple(row) == ("FULL_MODULE", None, None, None)
        # An old insert omitting scope still receives the non-null server default.
        copied = await db_session.scalar(
            text("""INSERT INTO attempts
            (id, user_id, test_version_id, module_type, timer_mode, started_at, last_active_at, status)
            SELECT gen_random_uuid(), user_id, test_version_id, module_type, timer_mode,
                   started_at, last_active_at, status FROM attempts WHERE id = :id
            RETURNING scope"""),
            {"id": historical.attempt_id},
        )
        assert copied == "FULL_MODULE"
    restored = await service.get(historical.attempt_id)
    assert restored.model_dump(exclude={"server_time", "elapsed_seconds"}) == historical.model_dump(
        exclude={"server_time", "elapsed_seconds"}
    )


@pytest.mark.integration
async def test_downgrade_refuses_to_reinterpret_focused_history(db_session):
    version, units = await content(db_session)
    service = AttemptService(db_session)
    focused = await service.start(
        request(version, ModuleType.READING, units[ModuleType.READING][0])
    )
    with pytest.raises(DBAPIError, match="Cannot remove attempt scope"):
        async with db_session.begin():
            await migrate(db_session, "downgrade")
    recovered = await service.get(focused.attempt_id)
    assert recovered.scope == "FOCUSED_UNIT" and recovered.focused_unit == focused.focused_unit
