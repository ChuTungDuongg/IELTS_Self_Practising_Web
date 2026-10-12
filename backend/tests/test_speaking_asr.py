"""Offline contracts for the local adapter and protected remote GPU service."""

import importlib.util
import io
import logging
import sys
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.providers.speaking_asr import create_provider, provider_identity
from app.providers.speaking_asr.modal import MAX_WAV_BYTES, ModalASRProvider
from app.services.speaking_audio import NormalizedAudio
from app.services.speaking_transcript import response_cache

ROOT = Path(__file__).resolve().parents[2]
MODEL = "Systran/faster-whisper-large-v3"
REVISION = "edaa852ec7e145841d8ffdb056a99866b5f0a478"
VERSION = "fw1.2.1-av18.1.0-ct2-4.8.2-int8fp16-beam5-v2-edaa852"


def wav_bytes(seconds=1, *, channels=1, rate=16000):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x20" * (rate * channels * seconds))
    return output.getvalue()


def normalized(tmp_path, content=None):
    path = tmp_path / "private.wav"
    path.write_bytes(content or wav_bytes())
    return NormalizedAudio(path, "a" * 64, "pcm-v1", "b" * 64, 1000)


def modal_settings(**overrides):
    return Settings(
        speaking_asr_enabled=True,
        speaking_asr_provider="modal",
        speaking_asr_base_url="https://fictional-asr.modal.run",
        speaking_asr_model=MODEL,
        speaking_asr_model_revision=REVISION,
        speaking_asr_version=VERSION,
        ai_writing_modal_key="fictional-key",
        ai_writing_modal_secret="fictional-secret",
        **overrides,
    )


def response_body(**changes):
    return {
        "text": "Fictional speech.",
        "words": [{"word": "Fictional", "start": 0.1, "end": 0.5, "confidence": 0.9}],
        "provider": "modal",
        "model": MODEL,
        "version": VERSION,
        "language": "en",
        **changes,
    }


def test_local_provider_remains_lazy_and_remote_is_selectable(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    local = create_provider(
        Settings(speaking_asr_enabled=True, speaking_asr_model_directory="fictional-local")
    )
    assert local.identity["provider"] == "faster-whisper"
    assert isinstance(create_provider(modal_settings()), ModalASRProvider)


@pytest.mark.parametrize("replacement", ["model", "revision", "version", "language"])
def test_remote_identity_tracks_model_not_url_or_secrets(replacement):
    first = modal_settings()
    rotated = first.model_copy(
        update={"speaking_asr_base_url": "https://new-asr.modal.run", "ai_writing_modal_key": "new"}
    )
    assert provider_identity(first) == provider_identity(rotated)
    field = {
        "model": "speaking_asr_model",
        "revision": "speaking_asr_model_revision",
        "version": "speaking_asr_version",
        "language": "speaking_asr_language",
    }[replacement]
    changed = first.model_copy(update={field: "changed"})
    assert provider_identity(first) != provider_identity(changed)
    assert response_cache("audio", {"asr": provider_identity(first)}) != response_cache(
        "audio", {"asr": provider_identity(changed)}
    )
    assert response_cache("audio", {"asr": provider_identity(first)}) == response_cache(
        "audio", {"asr": provider_identity(rotated)}
    )
    assert "fictional-secret" not in str(provider_identity(first))


async def test_remote_sends_only_bounded_normalized_wav_and_validates_result(tmp_path):
    seen = []

    async def handler(request):
        seen.append(request)
        return httpx.Response(200, json=response_body())

    provider = ModalASRProvider(modal_settings(), transport=httpx.MockTransport(handler))
    result = await provider.transcribe(normalized(tmp_path))
    assert result.words[0].start == 0.1
    assert len(seen) == 1
    assert seen[0].headers["content-type"] == "audio/wav"
    assert seen[0].headers["Modal-Key"] == "fictional-key"
    assert seen[0].content.startswith(b"RIFF")
    assert seen[0].url.path == "/transcribe"
    assert "fictional-secret" not in result.model_dump_json()


@pytest.mark.parametrize(
    "case", ["webm", "oversize", "stereo", "wrong_rate", "duration"]
)
async def test_remote_rejects_non_normalized_or_oversized_input_before_network(tmp_path, case):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response_body())

    audio = normalized(tmp_path)
    if case == "webm":
        audio.path.write_bytes(b"\x1a\x45\xdf\xa3raw-webm")
    elif case == "oversize":
        audio.path.write_bytes(b"x" * (MAX_WAV_BYTES + 1))
    elif case == "duration":
        audio = NormalizedAudio(audio.path, audio.source_audio_fingerprint, "pcm-v1", "b" * 64, 2000)
    else:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(2 if case == "stereo" else 1)
            wav.setsampwidth(2)
            wav.setframerate(8000 if case == "wrong_rate" else 16000)
            wav.writeframes(b"\x00\x20" * 16000)
        audio.path.write_bytes(output.getvalue())
    with pytest.raises(AppError) as error:
        await ModalASRProvider(modal_settings(), transport=httpx.MockTransport(handler)).transcribe(audio)
    assert error.value.code == "SPEAKING_AUDIO_UNASSESSABLE"
    assert not calls


@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(503, text="private path and secret"), "SPEAKING_ASR_UNAVAILABLE"),
        (httpx.Response(422, json={"detail": "No speech"}), "ASR_UNUSABLE"),
        (httpx.Response(200, content=b"not json"), "SPEAKING_ASR_UNAVAILABLE"),
        (httpx.Response(200, json=response_body(words=[{"word": "bad", "start": -1, "end": 1}])), "SPEAKING_ASR_UNAVAILABLE"),
        (httpx.Response(200, json=response_body(words=[{"word": "bad", "start": 0.5, "end": 0.1}])), "SPEAKING_ASR_UNAVAILABLE"),
        (httpx.Response(200, json=response_body(model="wrong")), "SPEAKING_ASR_UNAVAILABLE"),
    ],
)
async def test_remote_failures_are_safe_and_never_log_private_bodies(
    tmp_path, caplog, response, code
):
    async def handler(_request):
        return response

    with caplog.at_level(logging.DEBUG), pytest.raises(AppError) as error:
        await ModalASRProvider(
            modal_settings(), transport=httpx.MockTransport(handler)
        ).transcribe(normalized(tmp_path))
    assert error.value.code == code
    assert "private path" not in error.value.message + caplog.text
    assert "fictional-secret" not in error.value.message + caplog.text


async def test_remote_timeout_is_bounded_and_safe(tmp_path, monkeypatch):
    async def slow_request(_content):
        import asyncio

        await asyncio.sleep(0.02)

    provider = ModalASRProvider(modal_settings())
    provider.timeout = 0.001
    monkeypatch.setattr(provider, "_request", slow_request)
    with pytest.raises(AppError) as error:
        await provider.transcribe(normalized(tmp_path))
    assert error.value.code == "SPEAKING_ASR_UNAVAILABLE"


async def test_remote_network_error_and_redirect_fail_closed(tmp_path):
    requests = []

    async def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(302, headers={"Location": "https://unrelated.example/steal"})
        raise httpx.ConnectError("private request", request=request)

    provider = ModalASRProvider(modal_settings(), transport=httpx.MockTransport(handler))
    for _ in range(2):
        with pytest.raises(AppError) as error:
            await provider.transcribe(normalized(tmp_path))
        assert error.value.code == "SPEAKING_ASR_UNAVAILABLE"
    assert len(requests) == 2
    assert all(request.url.host == "fictional-asr.modal.run" for request in requests)


@pytest.mark.parametrize("url", ["http://asr.modal.run", "https://evil.example", "https://asr.modal.run/redirect", "https://user:secret@asr.modal.run", "https://[broken"])
def test_remote_rejects_untrusted_endpoint_before_credentials_are_sent(url):
    settings = modal_settings().model_copy(update={"speaking_asr_base_url": url})
    with pytest.raises(AppError) as error:
        ModalASRProvider(settings)
    assert error.value.code == "SPEAKING_ASR_UNAVAILABLE"


@pytest.fixture
def service(monkeypatch):
    modal = MagicMock()
    image = MagicMock()
    modal.Image.from_registry.return_value = image
    for operation in ("entrypoint", "pip_install", "env"):
        getattr(image, operation).return_value = image
    modal.App.return_value.function.return_value = lambda function: function
    modal.asgi_app.return_value = lambda function: function
    monkeypatch.setitem(sys.modules, "modal", modal)
    spec = importlib.util.spec_from_file_location(
        "speaking_asr_service_test", ROOT / "deploy/modal/speaking_asr.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, modal


def test_service_has_pinned_separate_gpu_and_proxy_auth(service):
    module, modal = service
    assert module.serve_asr.__name__ == "serve_asr"  # Distinct from included Ministral serve.
    assert module.MODEL == MODEL and module.REVISION == REVISION
    assert module.FASTER_WHISPER_VERSION == "1.2.1"
    assert module.PYAV_VERSION == "18.1.0"
    assert "av==18.1.0" in modal.Image.from_registry.return_value.pip_install.call_args.args
    assert module.COMPUTE_TYPE == "int8_float16"
    kwargs = modal.App.return_value.function.call_args.kwargs
    assert kwargs["gpu"] == "T4" and kwargs["cpu"] == 4 and kwargs["memory"] == 16384
    assert kwargs["min_containers"] == 0 and kwargs["max_containers"] == 1
    assert kwargs["scaledown_window"] == 60 and kwargs["timeout"] == 600
    assert kwargs["volumes"] == {"/cache": module.cache}
    modal.Volume.from_name.assert_called_once_with(
        "ielts-speaking-asr-model-cache", create_if_missing=True
    )
    modal.asgi_app.assert_called_once_with(requires_proxy_auth=True)


@pytest.mark.parametrize(
    "case,status",
    [("valid", 200), ("webm", 422), ("stereo", 422), ("rate", 422), ("size", 413), ("mime", 415), ("empty", 422), ("failure", 503)],
)
async def test_service_endpoint_validates_before_inference_and_cleans_temp(
    service, monkeypatch, tmp_path, caplog, case, status
):
    module, _ = service
    paths = []

    def transcribe(path, **options):
        paths.append(Path(path))
        assert paths[-1].is_file() and options["word_timestamps"] and options["language"] == "en"
        if case == "failure":
            raise RuntimeError("private audio and secret")
        if case == "empty":
            return iter([]), None
        segment = SimpleNamespace(
            text=" Fictional speech.",
            words=[SimpleNamespace(word=" Fictional", start=0.1, end=0.5, probability=0.9)],
        )
        return iter([segment]), None

    model = SimpleNamespace(transcribe=transcribe)
    loader = MagicMock(return_value=model)
    monkeypatch.setattr(module, "load_model", loader)
    if case == "size":
        monkeypatch.setattr(module, "MAX_WAV_BYTES", 100)
    api = module.serve_asr()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.post(
            "/transcribe",
            content=(
                b"raw-webm"
                if case == "webm"
                else wav_bytes(channels=2 if case == "stereo" else 1, rate=8000 if case == "rate" else 16000)
            ),
            headers={"Content-Type": "audio/webm" if case == "mime" else "audio/wav"},
        )
        assert (await client.get("/health")).status_code == 200
    assert response.status_code == status
    assert "private audio" not in response.text and "secret" not in response.text
    assert "private audio" not in caplog.text and "secret" not in caplog.text
    loader.assert_called_once()
    if case in {"valid", "failure", "empty"}:
        assert paths and not paths[0].exists()
    else:
        assert not paths
    if case == "valid":
        assert response.json()["words"][0]["end"] == 0.5
        assert response.json()["version"] == VERSION
