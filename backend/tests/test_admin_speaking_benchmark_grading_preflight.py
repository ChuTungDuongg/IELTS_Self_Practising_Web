import pytest

from app.core.config import Settings


def test_default_grading_is_disabled_and_static():
    from app.services.speaking_benchmark_preflight import grading_availability

    result = grading_availability(Settings(_env_file=None))
    assert result["can_queue"] is False
    assert result["live_status"] == "LIVE_UNVERIFIED"
    assert len(result["providers"]) == 4
    assert "key" not in str(result).lower()


def test_all_selected_provider_estimates_are_required():
    from app.schemas.speaking_benchmark_grading import Consent
    from app.services.speaking_benchmark_preflight import validate_consent

    body = Consent(
        azure_audio=True,
        llm_text=True,
        independent_provider=True,
        estimates_usd={"azure_pa": 0.1, "openai": 0.2},
        max_estimated_cost_usd=1,
    )
    with pytest.raises(Exception, match="CONSENT"):
        validate_consent(body, "azure_stt")


def test_unknown_billing_and_remote_embedded_topology_stay_blocked():
    from app.services.speaking_benchmark_preflight import grading_availability

    settings = Settings(
        _env_file=None,
        speaking_benchmark_execution="remote",
        speaking_benchmark_grading_enabled=True,
        speaking_benchmark_grading_allow_live=True,
    )
    result = grading_availability(settings)
    assert not result["can_queue"]
    assert all(
        "SPEAKING_BENCHMARK_REMOTE_REQUIRES_SHARED_STORAGE_AND_DATABASE" in p["reasons"]
        for p in result["providers"]
    )
    assert all("SPEAKING_AZURE_BILLING_NOT_AUTHORIZED" in p["reasons"] for p in result["providers"])


def test_physical_call_budget_includes_schema_and_transport_repairs():
    from app.services.speaking_benchmark_preflight import request_budget

    assert request_budget(3, "azure_stt") == {
        "azure_pa": 3,
        "azure_stt": 3,
        "openai_typical": 8,
        "openai_maximum": 20,
    }
