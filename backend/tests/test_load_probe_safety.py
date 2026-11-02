"""A fake worker must never scan jobs belonging to another local database user."""

from types import SimpleNamespace

import pytest


class ProbeConnection:
    def __init__(self, *, foreign_rows=0, other_connections=0):
        self.foreign_rows = foreign_rows
        self.other_connections = other_connections
        self.statements = []
        self.dialect = SimpleNamespace(
            identifier_preparer=SimpleNamespace(quote=lambda value: f'"{value}"')
        )

    async def scalars(self, statement):
        self.statements.append(str(statement))
        return ["users", "writing_ai_grading_runs"]

    async def scalar(self, statement, parameters=None):
        self.statements.append(str(statement))
        if "pg_stat_activity" in str(statement):
            return self.other_connections
        return self.foreign_rows


async def test_probe_requires_database_ownership_before_inspecting_fixtures(monkeypatch):
    from benchmarks.load import runtime
    from benchmarks.load.safety import SafetyError

    async def reject(*_args, **_kwargs):
        raise SafetyError("DATABASE_OWNERSHIP_PROOF_MISMATCH")

    monkeypatch.setattr(runtime, "verify_database", reject)
    connection = ProbeConnection()
    with pytest.raises(SafetyError, match="OWNERSHIP"):
        await runtime.verify_fresh_probe_database(connection, {}, {})
    assert connection.statements == []


@pytest.mark.parametrize("foreign_rows,other_connections", [(1, 0), (0, 1)])
async def test_probe_rejects_existing_data_or_live_server(
    monkeypatch, foreign_rows, other_connections
):
    from benchmarks.load import runtime
    from benchmarks.load.safety import SafetyError

    async def allow(*_args, **_kwargs):
        pass

    monkeypatch.setattr(runtime, "verify_database", allow)
    connection = ProbeConnection(foreign_rows=foreign_rows, other_connections=other_connections)
    with pytest.raises(SafetyError, match="FRESH_PROBE_DATABASE_REQUIRED"):
        await runtime.verify_fresh_probe_database(
            connection, {}, {"admin": {"email": "fictional-probe@example.com"}}
        )
    assert all("DELETE" not in sql and "UPDATE" not in sql for sql in connection.statements)


async def test_probe_permits_only_attested_fresh_database(monkeypatch):
    from benchmarks.load import runtime

    checked = []

    async def allow(*args, **_kwargs):
        checked.append(args)

    monkeypatch.setattr(runtime, "verify_database", allow)
    connection = ProbeConnection()
    await runtime.verify_fresh_probe_database(
        connection, {}, {"admin": {"email": "fictional-probe@example.com"}}
    )
    assert len(checked) == 1
    assert any("writing_ai_grading_runs" in sql for sql in connection.statements)


async def test_auth_component_supports_python_without_process_cpu_count(monkeypatch):
    from benchmarks.load import auth_component

    # Replace this module's view, not the shared os module: Python 3.13's
    # ThreadPoolExecutor itself needs os.process_cpu_count during initialization.
    monkeypatch.setattr(auth_component, "os", SimpleNamespace(cpu_count=lambda: 2))
    monkeypatch.setattr(auth_component, "hash_password", lambda _password: "fictional")
    monkeypatch.setattr(auth_component.auth, "verify_password", lambda *_args: True)
    result = await auth_component.measure()
    assert result["process_cpu_count"] == 2
    assert result["total_calls"] == 50
