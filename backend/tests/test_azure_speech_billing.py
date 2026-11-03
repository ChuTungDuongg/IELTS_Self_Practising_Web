"""Billing safety never needs a live resource, ARM permission or a paid API call."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_azure_speech_analysis import audio as shared_audio
from test_azure_speech_analysis import build, emit, final_payload, settings

from app.core.config import Settings
from app.core.exceptions import AppError
from app.providers.speaking_asr import create_provider
from app.services.speaking_hybrid import analysis_to_asr, analyze_response


@pytest.fixture
def audio(tmp_path):
    return shared_audio.__wrapped__(tmp_path)


def test_billing_defaults_do_not_authorize_a_paid_or_unknown_resource():
    configured = Settings(_env_file=None)
    assert configured.speaking_azure_allow_paid is False
    assert configured.speaking_azure_billing_mode == "unknown"


@pytest.mark.parametrize(
    "mode,allow_paid", [("unknown", False), ("paid", False), ("unknown", True)]
)
async def test_unauthorized_billing_never_loads_sdk_or_submits_audio(
    monkeypatch, audio, mode, allow_paid
):
    from app.providers.speech_analysis import azure

    analyzer = azure.AzureSpeechAnalyzer(
        settings(speaking_azure_billing_mode=mode, speaking_azure_allow_paid=allow_paid)
    )
    monkeypatch.setattr(azure, "_load_sdk", lambda: pytest.fail("No SDK/provider may be started"))
    result = await analyzer.analyze(audio)
    assert result.error_code == "SPEAKING_AZURE_BILLING_NOT_AUTHORIZED"
    assert result.status == "FAILED"
    assert result.usage.attempted_calls == 0
    assert result.usage.outcome == "NOT_ATTEMPTED"


def test_paid_credentials_do_not_enable_fallback_when_opt_in_is_false():
    configured = Settings(
        _env_file=None,
        speaking_profile="speaking_hybrid_v1",
        speaking_asr_enabled=True,
        speaking_azure_key="fictional-paid-key",
        speaking_azure_region="southeastasia",
        speaking_azure_billing_mode="paid",
        speaking_azure_allow_paid=False,
        speaking_asr_provider="azure",
        ai_writing_modal_key="alternate-key",
        ai_writing_modal_secret="alternate-secret",
        ai_writing_openai_api_key="alternate-openai",
    )
    with pytest.raises(AppError) as caught:
        create_provider(configured)
    assert caught.value.code == "SPEAKING_AZURE_BILLING_NOT_AUTHORIZED"


@pytest.mark.parametrize("mode,allow_paid", [("free_only", False), ("paid", True)])
async def test_explicit_billing_configuration_pins_one_key_and_region(
    monkeypatch, audio, mode, allow_paid
):
    def action(recognizer):
        emit(recognizer, final_payload())
        recognizer.session_stopped.emit(SimpleNamespace())

    analyzer, sdk = build(
        monkeypatch, action, speaking_azure_billing_mode=mode, speaking_azure_allow_paid=allow_paid
    )
    result = await analyzer.analyze(audio)
    assert result.status == "COMPLETE"
    assert sdk.config.subscription == "offline-key" and sdk.config.region == "offline-region"
    assert len(sdk.recognizers) == result.usage.attempted_calls == 1


@pytest.mark.parametrize(
    "detail,reason",
    [
        ("ErrorCode=RateLimitExceeded", "PROVIDER_RATE_LIMIT"),
        ("ErrorCode=ConcurrencyLimitExceeded", "PROVIDER_CONCURRENCY_LIMIT"),
        ("ErrorCode=QuotaExhausted", "PROVIDER_QUOTA_EXHAUSTED"),
        ("private provider body", "SDK_TOO_MANY_REQUESTS"),
    ],
)
async def test_sdk_throttling_is_terminal_and_preserves_only_a_safe_reason(
    monkeypatch, audio, detail, reason
):
    def action(recognizer):
        recognizer.canceled.emit(
            SimpleNamespace(
                reason="error", error_code="quota", error_details=detail + " secret-key"
            )
        )

    analyzer, sdk = build(monkeypatch, action)
    result = await analyzer.analyze(audio)
    assert result.error_code == "SPEAKING_AZURE_QUOTA_EXCEEDED"
    assert result.provider_reason_code == reason
    assert result.usage.attempted_calls == len(sdk.recognizers) == 1
    assert result.usage.automatic_retries == 0
    assert "secret-key" not in result.model_dump_json()
    with pytest.raises(AppError) as caught:
        analysis_to_asr([result], audio)
    assert caught.value.code == "SPEAKING_AZURE_QUOTA_EXCEEDED"


async def test_http_429_exception_is_not_retried_or_replaced(monkeypatch, audio):
    def action(_):
        error = RuntimeError("private raw body")
        error.status_code = 429
        raise error

    analyzer, sdk = build(monkeypatch, action)
    result = await analyzer.analyze(audio)
    assert result.error_code == "SPEAKING_AZURE_QUOTA_EXCEEDED"
    assert result.provider_reason_code == "HTTP_429"
    assert len(sdk.recognizers) == result.usage.attempted_calls == 1


async def test_quota_stops_recovery_segments_without_losing_successful_final_text(
    monkeypatch, audio
):
    from app.schemas.speaking_timeline import AudioSegmentMapping

    def action(recognizer):
        emit(recognizer, final_payload())
        recognizer.canceled.emit(SimpleNamespace(reason="error", error_code="quota"))

    analyzer, sdk = build(monkeypatch, action)
    rid = uuid4()
    mappings = tuple(
        AudioSegmentMapping(
            response_id=rid,
            take_number=1,
            segment_id=uuid4(),
            normalized_start_ms=start,
            normalized_end_ms=end,
            gap_before_unknown=start > 0,
        )
        for start, end in [(0, 30000), (30000, 60000)]
    )
    source = replace(audio, timeline=mappings, segment_count=2)
    results = await analyze_response(source, analyzer.settings, analyzer=analyzer)
    assert len(results) == len(sdk.recognizers) == 1
    assert results[0].status == "PARTIAL"
    assert results[0].error_code == "SPEAKING_AZURE_QUOTA_EXCEEDED"
    assert analysis_to_asr(results, source).text == "Um I paint"


def test_resource_and_billing_identity_change_invalidates_cached_analysis():
    from app.providers.speech_analysis.azure import AzureSpeechAnalyzer

    original = settings()
    analyzer = AzureSpeechAnalyzer(original)
    identity = analyzer.identity.configuration_fingerprint
    original.speaking_azure_key = "another-resource-key"
    assert analyzer.settings.speaking_azure_key == "offline-key"
    assert AzureSpeechAnalyzer(original).identity.configuration_fingerprint != identity
    assert (
        AzureSpeechAnalyzer(
            settings(speaking_azure_allow_paid=True)
        ).identity.configuration_fingerprint
        != identity
    )
    assert "offline-key" not in analyzer.identity.model_dump_json()


async def test_quota_error_survives_late_callback_and_startup_failure(monkeypatch, audio):
    def action(recognizer):
        recognizer.canceled.emit(SimpleNamespace(reason="error", error_code="quota"))
        recognizer.canceled.emit(SimpleNamespace(reason="error", error_code="other"))
        raise RuntimeError("private late startup failure")

    analyzer, sdk = build(monkeypatch, action)
    result = await analyzer.analyze(audio)
    assert result.error_code == "SPEAKING_AZURE_QUOTA_EXCEEDED"
    assert result.provider_reason_code == "SDK_TOO_MANY_REQUESTS"
    assert len(sdk.recognizers) == 1 and result.usage.automatic_retries == 0
