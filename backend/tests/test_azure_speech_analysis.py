"""Offline Azure boundary tests. All transcripts are fictional fixtures."""

import asyncio
import importlib
import json
import threading
import wave
from types import SimpleNamespace

import pytest

from app.services.speaking_audio import NormalizedAudio


def adapter_module():
    try:
        return importlib.import_module("app.providers.speech_analysis.azure")
    except ModuleNotFoundError:
        pytest.fail("Azure continuous speech adapter is not implemented")


def settings(**overrides):
    return SimpleNamespace(
        **{
            "speaking_azure_key": "offline-key",
            "speaking_azure_region": "offline-region",
            "speaking_azure_locale": "en-US",
            "speaking_azure_prosody": True,
            "speaking_azure_timeout_seconds": 0.3,
            "speaking_azure_max_concurrency": 1,
            "speaking_azure_max_queue": 1,
            "speaking_azure_billing_mode": "free_only",
            "speaking_azure_allow_paid": False,
            **overrides,
        }
    )


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "fixture.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000 * 60)
    return NormalizedAudio(path, "source-fixture", "normalizer-v1", "cache-fixture", 60000)


def final_payload(offset=17000000, text="Um I paint", display="Um, I paint."):
    return {
        "Id": str(offset),
        "RecognitionStatus": "Success",
        "Offset": offset,
        "Duration": 10000000,
        "DisplayText": display,
        "NBest": [
            {
                "Lexical": text,
                "Display": display,
                "Confidence": 0.82,
                "PronunciationAssessment": {"AccuracyScore": 64, "ProsodyScore": 70},
                "Words": [
                    {
                        "Word": "um",
                        "Offset": offset,
                        "Duration": 2000000,
                        "PronunciationAssessment": {
                            "AccuracyScore": 64,
                            "ErrorType": "Mispronunciation",
                        },
                        "Phonemes": [
                            {
                                "Phoneme": "ax",
                                "Offset": offset,
                                "Duration": 1000000,
                                "PronunciationAssessment": {"AccuracyScore": 62},
                            }
                        ],
                    }
                ],
            }
        ],
    }


class Signal:
    def __init__(self):
        self.handlers = []

    def connect(self, callback):
        self.handlers.append(callback)

    def disconnect_all(self):
        self.handlers.clear()

    def emit(self, event):
        for callback in list(self.handlers):
            callback(event)


class FakeSDK:
    CancellationErrorCode = SimpleNamespace(AuthenticationFailure="auth", TooManyRequests="quota")
    __version__ = "offline-sdk"
    OutputFormat = SimpleNamespace(Detailed="Detailed")
    PropertyId = SimpleNamespace(SpeechServiceResponse_JsonResult="json")
    ResultReason = SimpleNamespace(
        RecognizedSpeech="final", RecognizingSpeech="interim", NoMatch="no-match"
    )
    CancellationReason = SimpleNamespace(Error="error", EndOfStream="eof")
    PronunciationAssessmentGradingSystem = SimpleNamespace(HundredMark=100)
    PronunciationAssessmentGranularity = SimpleNamespace(Phoneme="phoneme")

    def __init__(self, action):
        self.action = action
        self.recognizers = []
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.audio = SimpleNamespace(
            AudioConfig=lambda **kwargs: SimpleNamespace(**kwargs),
            AudioStreamFormat=lambda **kwargs: SimpleNamespace(**kwargs),
            PushAudioInputStream=lambda _: SimpleNamespace(
                write=lambda data: None, close=lambda: None
            ),
        )

    def SpeechConfig(self, **kwargs):
        self.config = SimpleNamespace(**kwargs)
        self.config.request_word_level_timestamps = lambda: None
        return self.config

    def PronunciationAssessmentConfig(self, **kwargs):
        assert kwargs["reference_text"] == ""
        assert kwargs["enable_miscue"] is False
        self.prosody_requested = False

        def enable():
            self.prosody_requested = True

        return SimpleNamespace(enable_prosody_assessment=enable, apply_to=lambda _: None)

    def SpeechRecognizer(self, **kwargs):
        recognizer = SimpleNamespace(**kwargs)
        for name in ("recognized", "recognizing", "session_stopped", "canceled"):
            setattr(recognizer, name, Signal())

        def start():
            self.started.set()
            self.action(recognizer)
            return SimpleNamespace(get=lambda: None)

        def stop():
            self.stopped.set()
            return SimpleNamespace(get=lambda: None)

        recognizer.start_continuous_recognition_async = start
        recognizer.stop_continuous_recognition_async = stop
        self.recognizers.append(recognizer)
        return recognizer


def emit(recognizer, payload, *, reason="final", result_id=None):
    result = SimpleNamespace(
        reason=reason,
        result_id=result_id or str(payload.get("Offset")),
        properties={"json": json.dumps(payload)},
    )
    getattr(recognizer, "recognizing" if reason == "interim" else "recognized").emit(
        SimpleNamespace(result=result)
    )


def build(monkeypatch, action, **overrides):
    module = adapter_module()
    sdk = FakeSDK(action)
    monkeypatch.setattr(module, "_load_sdk", lambda: sdk)
    return module.AzureSpeechAnalyzer(settings(**overrides)), sdk


async def test_final_only_multiple_utterances_absolute_ticks_and_separate_scores(
    monkeypatch, audio
):
    def action(recognizer):
        emit(recognizer, final_payload(), reason="interim")
        emit(recognizer, final_payload())
        emit(recognizer, final_payload())  # Duplicate delivery cannot duplicate evidence.
        emit(recognizer, final_payload(407150000, "I sketch", "I sketch."))
        recognizer.session_stopped.emit(SimpleNamespace())

    analyzer, sdk = build(monkeypatch, action)
    result = await analyzer.analyze(audio, response_id="response", take_number=2, segment_id="seg")
    assert result.status == "COMPLETE"
    assert result.lexical_transcript == "Um I paint I sketch"
    assert result.display_transcript == "Um, I paint. I sketch."
    assert [(w.start_ms, w.end_ms) for w in result.words] == [(1700, 1900), (40715, 40915)]
    assert result.words[0].recognition_confidence is None
    assert result.utterances[0].recognition_confidence == 0.82
    assert result.observations[0].score == 64
    assert {o.kind for o in result.observations} >= {"pronunciation", "phoneme", "prosody"}
    assert result.source.segment_id == "seg"
    assert result.capabilities.prosody_observed is True
    assert result.provider.model_version is None
    assert result.usage.attempted_calls == 1
    assert result.usage.billed_duration_ms is None
    assert sdk.stopped.is_set()
    assert len({w.evidence_id for w in result.words}) == 2


async def test_missing_fields_stay_unknown_and_locale_does_not_claim_prosody(monkeypatch, audio):
    def action(recognizer):
        emit(
            recognizer,
            {
                "RecognitionStatus": "Success",
                "Offset": 0,
                "Duration": 10000000,
                "NBest": [
                    {
                        "Lexical": "uh maybe",
                        "Words": [{"Word": "uh", "Offset": 0, "Duration": 1000000}],
                    }
                ],
            },
        )
        recognizer.session_stopped.emit(SimpleNamespace())

    analyzer, sdk = build(monkeypatch, action, speaking_azure_locale="en-GB")
    result = await analyzer.analyze(audio)
    assert result.status == "COMPLETE"
    assert result.lexical_transcript == "uh maybe"
    assert result.display_transcript is None
    assert result.utterances[0].recognition_confidence is None
    assert result.capabilities.prosody_observed is None
    assert not sdk.prosody_requested
    assert "PROSODY_LOCALE_UNSUPPORTED" in result.limitations


@pytest.mark.parametrize("with_final,expected", [(False, "FAILED"), (True, "PARTIAL")])
async def test_provider_error_preserves_partial_without_private_details(
    monkeypatch, audio, with_final, expected
):
    def action(recognizer):
        if with_final:
            emit(recognizer, final_payload())
        recognizer.canceled.emit(SimpleNamespace(reason="error", error_details="secret-token"))

    analyzer, _ = build(monkeypatch, action)
    result = await analyzer.analyze(audio)
    assert result.status == expected
    assert result.error_code == "AZURE_SERVICE_ERROR"
    assert "secret-token" not in result.model_dump_json()
    assert result.usage.attempted_calls == 1


async def test_timeout_stops_and_fences_late_events(monkeypatch, audio):
    analyzer, sdk = build(monkeypatch, lambda _: None, speaking_azure_timeout_seconds=0.04)
    result = await analyzer.analyze(audio)
    assert result.status == "FAILED"
    assert result.error_code == "AZURE_TIMEOUT"
    assert sdk.stopped.is_set()
    emit(sdk.recognizers[0], final_payload())
    assert result.words == []


async def test_caller_cancellation_stops_native_work_before_propagating(monkeypatch, audio):
    analyzer, sdk = build(monkeypatch, lambda _: None)
    task = asyncio.create_task(analyzer.analyze(audio))
    await asyncio.to_thread(sdk.started.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sdk.stopped.is_set()


async def test_process_capacity_is_shared_and_queue_is_bounded(monkeypatch, audio):
    analyzer, sdk = build(monkeypatch, lambda _: None)
    other = adapter_module().AzureSpeechAnalyzer(settings())
    first = asyncio.create_task(analyzer.analyze(audio))
    await asyncio.to_thread(sdk.started.wait, 1)
    queued = asyncio.create_task(other.analyze(audio))
    await asyncio.sleep(0.01)
    rejected = await other.analyze(audio)
    assert rejected.status == "FAILED"
    assert rejected.error_code == "AZURE_CAPACITY_EXCEEDED"
    assert rejected.usage.attempted_calls == 0
    first.cancel()
    queued.cancel()
    await asyncio.gather(first, queued, return_exceptions=True)


async def test_malformed_final_is_partial_and_cannot_invent_zero_scores(monkeypatch, audio):
    def action(recognizer):
        emit(recognizer, final_payload())
        emit(recognizer, {"RecognitionStatus": "Success", "NBest": []}, result_id="broken")
        recognizer.session_stopped.emit(SimpleNamespace())

    analyzer, _ = build(monkeypatch, action)
    result = await analyzer.analyze(audio)
    assert result.status == "PARTIAL"
    assert result.error_code == "AZURE_RESULT_INVALID"
    assert len(result.utterances) == 1


async def test_identity_is_secret_free_and_configuration_sensitive(monkeypatch):
    first, _ = build(monkeypatch, lambda _: None)
    second, _ = build(monkeypatch, lambda _: None, speaking_azure_prosody=False)
    assert first.identity.configuration_fingerprint != second.identity.configuration_fingerprint
    assert "offline-key" not in first.identity.model_dump_json()


async def test_empty_final_session_is_no_match_without_retry(monkeypatch, audio):
    analyzer, _ = build(monkeypatch, lambda r: r.session_stopped.emit(SimpleNamespace()))
    result = await analyzer.analyze(audio)
    assert result.status == "FAILED"
    assert result.error_code == "AZURE_NO_MATCH"
    assert result.usage.attempted_calls == 1


async def test_partial_timeout_retains_final_and_deduplicates_observations(monkeypatch, audio):
    def action(recognizer):
        emit(recognizer, final_payload())
        emit(recognizer, final_payload())

    analyzer, _ = build(monkeypatch, action, speaking_azure_timeout_seconds=0.03)
    result = await analyzer.analyze(audio)
    assert result.status == "PARTIAL"
    assert result.error_code == "AZURE_TIMEOUT"
    assert result.lexical_transcript == "Um I paint"
    assert len(result.observations) == 5


@pytest.mark.parametrize(
    "code,expected",
    [("auth", "SPEAKING_AZURE_AUTHENTICATION_FAILED"), ("quota", "SPEAKING_AZURE_QUOTA_EXCEEDED")],
)
async def test_classified_errors_do_not_expose_private_details(monkeypatch, audio, code, expected):
    def action(recognizer):
        recognizer.canceled.emit(
            SimpleNamespace(reason="error", error_code=code, error_details="private-key-and-text")
        )

    analyzer, sdk = build(monkeypatch, action)
    sdk.CancellationErrorCode = SimpleNamespace(
        AuthenticationFailure="auth", TooManyRequests="quota"
    )
    result = await analyzer.analyze(audio)
    assert result.error_code == expected
    assert result.usage.attempted_calls == 1
    assert "private-key" not in result.model_dump_json()


async def test_public_identity_does_not_import_sdk(monkeypatch):
    module = adapter_module()

    def forbidden():
        raise AssertionError("SDK import must be lazy")

    monkeypatch.setattr(module, "_load_sdk", forbidden)
    assert module.azure_analysis_identity(settings()).provider == "azure-speech"


async def test_stalled_native_cleanup_is_bounded_and_keeps_capacity(monkeypatch, audio):
    analyzer, sdk = build(
        monkeypatch, lambda _: None, speaking_azure_max_queue=0, speaking_azure_timeout_seconds=0.02
    )
    release = threading.Event()
    original = sdk.SpeechRecognizer

    def recognizer(**kwargs):
        item = original(**kwargs)

        def stop():
            sdk.stopped.set()
            return SimpleNamespace(get=lambda: release.wait(3))

        item.stop_continuous_recognition_async = stop
        return item

    sdk.SpeechRecognizer = recognizer
    try:
        result = await asyncio.wait_for(analyzer.analyze(audio), 1)
        assert result.error_code == "AZURE_TIMEOUT"
        emit(sdk.recognizers[0], final_payload())
        assert not result.words
        rejected = await analyzer.analyze(audio)
        assert rejected.error_code == "AZURE_CAPACITY_EXCEEDED"
    finally:
        release.set()


async def test_observations_carry_provenance_and_deduplicate_utterance_monotone(monkeypatch, audio):
    def action(recognizer):
        raw = final_payload()
        words = raw["NBest"][0]["Words"]
        words[0]["PronunciationAssessment"]["ErrorType"] = "Monotone"
        words.append(
            {
                "Word": "paint",
                "Offset": 20000000,
                "Duration": 1000000,
                "PronunciationAssessment": {"ErrorType": "Monotone"},
            }
        )
        emit(recognizer, raw)
        recognizer.session_stopped.emit(SimpleNamespace())

    analyzer, _ = build(monkeypatch, action)
    result = await analyzer.analyze(audio)
    assert sum(o.label == "Monotone" for o in result.observations) == 1
    assert all(o.source == "azure-pronunciation-assessment" for o in result.observations)
    assert result.observations[0].certainty == "provider_measurement"
    assert "LOW_ACCURACY_DOES_NOT_IDENTIFY_SUBSTITUTION" in result.observations[0].limitations
    assert result.latency_ms >= 0


async def test_secret_key_is_unwrapped_only_at_sdk_boundary(monkeypatch, audio):
    from pydantic import SecretStr

    analyzer, sdk = build(
        monkeypatch,
        lambda r: r.session_stopped.emit(SimpleNamespace()),
        speaking_azure_key=SecretStr("private-key"),
    )
    await analyzer.analyze(audio)
    assert sdk.config.subscription == "private-key"
    assert "private-key" not in analyzer.identity.model_dump_json()


async def test_documented_nested_prosody_flags_numeric_success_and_changed_event_id(
    monkeypatch, audio
):
    def action(recognizer):
        raw = final_payload()
        raw["RecognitionStatus"] = 0
        assessment = raw["NBest"][0]["Words"][0]["PronunciationAssessment"]
        assessment["ErrorType"] = "UnexpectedBreak"
        assessment["Feedback"] = {
            "Break": {
                "ErrorTypes": ["UnexpectedBreak"],
                "UnexpectedBreak": {"Confidence": 0.81},
                "MissingBreak": {"Confidence": 0.12},
            },
            "Intonation": {
                "ErrorTypes": ["Monotone"],
                "Monotone": {"SyllablePitchDeltaConfidence": 0.7},
            },
        }
        emit(recognizer, raw, result_id="first-delivery")
        emit(recognizer, raw, result_id="duplicate-delivery")
        recognizer.session_stopped.emit(SimpleNamespace())

    analyzer, _ = build(monkeypatch, action)
    result = await analyzer.analyze(audio)
    assert result.status == "COMPLETE"
    assert len(result.utterances) == 1
    assert result.capabilities.recognition_confidence_observed is True
    assert sum(o.label == "Monotone" for o in result.observations) == 1
    assert sum(o.label == "UnexpectedBreak" for o in result.observations) == 1
    measured = next(o for o in result.observations if o.metric == "UnexpectedBreak.Confidence")
    assert measured.provider_confidence == 0.81
    assert measured.label is None  # Adapter applies no unvalidated threshold.


async def test_missing_timing_and_phoneme_names_remain_unknown(monkeypatch, audio):
    def action(recognizer):
        raw = final_payload()
        del raw["Offset"]
        del raw["Duration"]
        word = raw["NBest"][0]["Words"][0]
        del word["Offset"]
        del word["Duration"]
        unit = word["Phonemes"][0]
        del unit["Phoneme"]
        del unit["Offset"]
        del unit["Duration"]
        emit(recognizer, raw)
        recognizer.session_stopped.emit(SimpleNamespace())

    analyzer, _ = build(monkeypatch, action)
    result = await analyzer.analyze(audio)
    assert result.words[0].start_ms is None
    assert next(o for o in result.observations if o.kind == "phoneme").token is None
    assert result.capabilities.word_timing_observed is None


async def test_owned_stream_is_closed_once_before_native_shutdown(monkeypatch, audio):
    analyzer, sdk = build(monkeypatch, lambda r: r.session_stopped.emit(SimpleNamespace()))
    closed = []

    def close():
        closed.append(True)
        if len(closed) > 1:
            raise RuntimeError("A closed input stream must not be reused")

    sdk.audio.PushAudioInputStream = lambda _: SimpleNamespace(write=lambda data: None, close=close)
    result = await analyzer.analyze(audio)
    assert result.error_code == "AZURE_NO_MATCH"
    assert len(closed) == 1


async def test_no_match_after_success_is_partial_with_localized_uncertainty(monkeypatch, audio):
    def action(recognizer):
        emit(recognizer, final_payload())
        emit(
            recognizer,
            {"RecognitionStatus": "NoMatch", "Offset": 40000000, "Duration": 10000000},
            reason="no-match",
        )
        recognizer.session_stopped.emit(SimpleNamespace())

    analyzer, _ = build(monkeypatch, action)
    result = await analyzer.analyze(audio)
    assert result.status == "PARTIAL" and result.lexical_transcript == "Um I paint"
    assert result.uncertain_regions[0].start_ms == 4000
    assert result.uncertain_regions[0].end_ms == 5000
    assert result.uncertain_regions[0].reason == "RECOGNITION_NO_MATCH"
