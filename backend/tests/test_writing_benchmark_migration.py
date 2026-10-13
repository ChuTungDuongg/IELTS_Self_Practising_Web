from benchmark_helpers import isolated_bank, migrate, migration
from sqlalchemy import inspect, text


async def test_actual_postgresql_revision_round_trip():
    assert migration().down_revision == "20261013_0034"
    async with isolated_bank() as (engine, _):
        async with engine.begin() as connection:
            tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
            assert tables == ["writing_benchmark_samples"]
            names = await connection.run_sync(
                lambda conn: [
                    c["name"]
                    for c in inspect(conn).get_check_constraints("writing_benchmark_samples")
                ]
            )
            assert any("complete" in name for name in names)
            await connection.execute(
                text(
                    "INSERT INTO writing_benchmark_samples (id,task_number,sequence_number) VALUES (gen_random_uuid(),2,1)"
                )
            )
            row = (
                await connection.execute(
                    text(
                        "SELECT status,split,prompt,essay,redistributable,revision,human_cc FROM writing_benchmark_samples"
                    )
                )
            ).one()
            assert tuple(row) == ("DRAFT", "DEV", "", "", False, 1, None)
            await connection.run_sync(lambda conn: migrate(conn, "downgrade"))
            assert await connection.run_sync(lambda conn: inspect(conn).get_table_names()) == []
            await connection.run_sync(lambda conn: migrate(conn, "upgrade"))
            assert (
                await connection.scalar(text("SELECT count(*) FROM writing_benchmark_samples")) == 0
            )
