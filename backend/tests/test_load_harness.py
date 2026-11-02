"""Offline safety/contracts for the opt-in load tool; no database or network required."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest


def test_configured_profile_rejects_nonfinite_and_bounds_local_timing():
    from benchmarks.load.profiles import configured_profile
    from benchmarks.load.safety import SafetyError

    value = configured_profile(
        "smoke",
        {"LOAD_STEADY_SECONDS": "90", "LOAD_THINK_SCALE": "2", "LOAD_MAX_RPS_PER_USER": "3"},
    )
    assert value["steady"] == 90 and value["think_scale"] == 2 and value["max_rps_per_user"] == 3
    for key in ("LOAD_STEADY_SECONDS", "LOAD_THINK_SCALE", "LOAD_MAX_RPS_PER_USER"):
        with pytest.raises(SafetyError):
            configured_profile("smoke", {key: "nan"})


def manifest(tmp_path):
    return {
        "run_id": "ab12cd34ef56",
        "base_url": "http://127.0.0.1:18991",
        "environment": "isolated-load",
        "database_name": "ielts_load_ab12cd34ef56",
        "database_user": "load_ab12cd34ef56",
        "storage_root": str(tmp_path / "ab12cd34ef56" / "storage"),
        "credential_id": "load-ab12cd34ef56",
        "deployment_id": "load-ab12cd34ef56",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "max_users": 10,
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost:8000",
        "http://127.0.0.1.evil.test",
        "http://u:p@127.0.0.1:8000",
        "http://127.0.0.1:8000/api",
        "http://127.0.0.1:8000?target=prod",
    ],
)
def test_load_guard_rejects_arbitrary_targets(tmp_path, url):
    from benchmarks.load.safety import SafetyError, validate_manifest

    data = manifest(tmp_path)
    data["base_url"] = url
    with pytest.raises(SafetyError):
        validate_manifest(data, requested_users=1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("database_name", "ielts"),
        ("database_user", "ielts"),
        ("credential_id", "production"),
        ("deployment_id", "demo"),
        ("environment", "staging"),
        ("storage_root", "C:/storage"),
        ("max_users", 5000),
    ],
)
def test_load_guard_requires_independent_identity_not_staging_flag(tmp_path, field, value):
    from benchmarks.load.safety import SafetyError, validate_manifest

    data = manifest(tmp_path)
    data[field] = value
    with pytest.raises(SafetyError):
        validate_manifest(data, requested_users=1)


def test_load_guard_matches_attested_identity_and_expires(tmp_path):
    from benchmarks.load.safety import SafetyError, validate_attestation, validate_manifest

    data = manifest(tmp_path)
    validate_manifest(data, requested_users=10)
    validate_attestation(data, dict(data, runner_owned=True))
    with pytest.raises(SafetyError):
        validate_attestation(data, dict(data, database_user="postgres", runner_owned=True))
    with pytest.raises(SafetyError):
        validate_attestation(data, dict(data, runner_owned=False))
    data["expires_at"] = "2020-01-01T00:00:00+00:00"
    with pytest.raises(SafetyError):
        validate_manifest(data, requested_users=1)


def test_load_runtime_rejects_shared_credentials_and_external_ai(tmp_path):
    from benchmarks.load.safety import SafetyError, validate_runtime_values

    data = manifest(tmp_path)
    env = {
        "DATABASE_URL": "postgresql+asyncpg://load_ab12cd34ef56:separate-password@127.0.0.1:15439/ielts_load_ab12cd34ef56",
        "STORAGE_ROOT": data["storage_root"],
        "STORAGE_BACKEND": "local",
        "JWT_ISSUER": data["credential_id"],
        "JWT_SECRET": "x" * 48,
        "AI_WRITING_ENABLED": "false",
        "SPEAKING_AI_ENABLED": "false",
        "SPEAKING_ASR_ENABLED": "false",
    }
    validate_runtime_values(data, env)
    for key, value in [
        ("DATABASE_URL", "postgresql+asyncpg://ielts:p@127.0.0.1:5433/ielts"),
        ("STORAGE_BACKEND", "s3"),
        ("JWT_ISSUER", "production"),
        ("AI_WRITING_ENABLED", "true"),
        ("SPEAKING_ASR_ENABLED", "true"),
    ]:
        with pytest.raises(SafetyError):
            validate_runtime_values(data, dict(env, **{key: value}))


@pytest.mark.parametrize(
    "changes",
    [
        {"worker": True},
        {"master": True},
        {"processes": 2},
        {"num_users": 5000},
        {"host": "https://production.example.com"},
    ],
)
def test_load_runner_options_reject_unowned_or_distributed_execution(tmp_path, changes):
    from types import SimpleNamespace

    from benchmarks.load.safety import SafetyError, validate_runner_options

    options = {"worker": False, "master": False, "processes": None, "num_users": None, "host": None}
    options.update(changes)
    with pytest.raises(SafetyError):
        validate_runner_options(manifest(tmp_path), SimpleNamespace(**options), requested_users=5)


def test_load_source_identity_changes_when_application_bytes_change(tmp_path):
    from benchmarks.load.source_identity import source_identity

    app = tmp_path / "app"
    app.mkdir()
    (app / "main.py").write_text("value = 1", encoding="utf-8")
    first = source_identity(tmp_path)
    (app / "main.py").write_text("value = 2", encoding="utf-8")
    second = source_identity(tmp_path)
    assert first["app_source_sha256"] != second["app_source_sha256"]


def test_load_child_environment_does_not_inherit_deployment_or_provider_secrets(
    tmp_path, monkeypatch
):
    from benchmarks.load.runtime import child_environment

    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-inherit")
    monkeypatch.setenv("AI_WRITING_OPENAI_API_KEY", "must-not-inherit")
    env = child_environment(tmp_path, {"environment": {"DATABASE_URL": "isolated"}})
    assert env["DATABASE_URL"] == "isolated"
    assert "WEB_CONCURRENCY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "AI_WRITING_OPENAI_API_KEY" not in env


async def test_load_client_never_follows_redirect_or_leaks_cookie(tmp_path):
    from benchmarks.load.client import GuardedClient, RequestFailure

    seen = []

    def response(request):
        seen.append(str(request.url))
        return httpx.Response(307, headers={"location": "https://example.com/stolen"})

    async with GuardedClient(
        manifest(tmp_path), "hidden-token", transport=httpx.MockTransport(response)
    ) as client:
        with pytest.raises(RequestFailure, match="HTTP_307"):
            await client.request("GET", "/api/v1/history", name="history")
        with pytest.raises(RequestFailure, match="TARGET_PATH"):
            await client.request("GET", "https://example.com", name="history")
    assert seen == ["http://127.0.0.1:18991/api/v1/history"]


def test_load_client_rejects_invalid_target_before_constructing_session(tmp_path):
    from benchmarks.load.client import GuardedClient
    from benchmarks.load.safety import SafetyError

    data = manifest(tmp_path)
    data["base_url"] = "https://production.example.com"
    with pytest.raises(SafetyError):
        GuardedClient(data, "hidden-token")


def test_load_active_answer_key_leaks_are_failures():
    from benchmarks.load.contracts import ContractFailure, assert_key_free

    assert_key_free({"passages": [{"questions": [{"id": "q", "config": {}}]}]})
    for leaked in (
        {"answer_key": {}},
        {"nested": [{"correct_answers": ["secret"]}]},
        {"accepted": ["secret"]},
    ):
        with pytest.raises(ContractFailure, match="ACTIVE_KEY_LEAK"):
            assert_key_free(leaked)


def test_load_payloads_validate_actual_backend_schemas():
    from benchmarks.load.contracts import (
        answer_payload,
        attempt_payload,
        mock_payload,
        writing_payload,
    )

    from app.schemas.attempts import AnswerUpdate, AttemptCreate, WritingResponseUpdate
    from app.schemas.classroom_assignments import AssignmentStart
    from app.schemas.test_sessions import TestSessionCreate as SessionCreate

    version = "834abec1-1b6d-422b-bd13-b336e60c70a4"
    assert AttemptCreate.model_validate(attempt_payload(version, "READING")).module == "READING"
    assert (
        AttemptCreate.model_validate(attempt_payload(version, "LISTENING")).timer.mode == "COUNT_UP"
    )
    assert AnswerUpdate.model_validate(answer_payload("fixture", 3)).expected_revision == 3
    assert (
        WritingResponseUpdate.model_validate(writing_payload("fictional", 2)).content == "fictional"
    )
    assert str(SessionCreate.model_validate(mock_payload(version)).test_version_id) == version
    assert (
        AssignmentStart.model_validate({"mode": "MODULE", "module": "READING"}).module == "READING"
    )


def test_load_metrics_percentiles_use_only_actual_steady_samples():
    from benchmarks.load.metrics import Metrics

    metrics = Metrics()
    metrics.record("save", 200, 100, 0.2)
    metrics.record("save", 200, 10, 2.0)
    metrics.record("save", 409, 30, 3.0, "REVISION_CONFLICT")
    metrics.record("save", 200, 900, 7.0)
    result = metrics.report(steady_start=1, steady_end=5, actual_end=4)
    assert result["steady_window"] == {"start_seconds": 1, "end_seconds": 4, "duration_seconds": 3}
    assert result["steady"]["save"]["requests"] == 2
    assert result["steady"]["save"]["p50_ms"] == 10
    assert result["steady"]["save"]["p95_ms"] == 30
    assert result["steady"]["save"]["failures"] == 1
    assert result["steady"]["save"]["statuses"] == {"200": 1, "409": 1}
    assert result["steady"]["save"]["successful_requests"] == 1
    assert result["steady"]["save"]["successful_rps"] == 0.333
    assert result["steady"]["save"]["http_4xx"] == 1
    assert result["steady"]["save"]["http_5xx"] == 0
    assert result["steady"]["save"]["p99_sample_warning"] is True


def test_load_metrics_never_fabricates_a_steady_window_before_ramp_finishes():
    from benchmarks.load.metrics import Metrics

    metrics = Metrics()
    metrics.record("login", 200, 2, 0.1)
    result = metrics.report(steady_start=10, steady_end=20, actual_end=3)
    assert result["steady_window"] is None
    assert result["steady"] == {}


def test_load_fixture_blueprint_is_fictional_and_schema_valid():
    from benchmarks.load.fixtures import fictional_group

    from app.schemas.content import QuestionGroupWrite

    group = QuestionGroupWrite.model_validate(fictional_group(1, 10))
    assert len(group.questions) == 10
    assert group.questions[0].number == 1
    assert group.questions[-1].number == 10
    assert group.questions[0].answer_key == {"kind": "TEXT", "accepted": ["fixture"]}
