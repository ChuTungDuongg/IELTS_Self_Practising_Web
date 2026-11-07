"""P2-only wrappers. Production provider protocols/prompts are unchanged."""

import asyncio
from contextvars import ContextVar

from app.providers.writing_llm.base import Completion, ProviderFailure, safe_completion_usage
from app.schemas.speech_analysis import SpeechAnalysisResult
from app.services.speaking_audio import fingerprint

_stage = ContextVar("benchmark_completion_stage", default="openai:unknown")


class LedgerTransport:
    def __init__(self, delegate, ledger, config):
        self.delegate, self.ledger, self.config = delegate, ledger, config

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    async def send(self, body):
        stage = _stage.get()
        identity = fingerprint([self.config, stage, body])
        cached = await self.ledger.cached(stage, identity)
        if cached:
            if cached.get("known_length_failure"):
                raise ProviderFailure(
                    "AI_PROVIDER_BAD_RESPONSE",
                    reason="PROVIDER_FINISH_LENGTH",
                    finish_reason="length",
                    usage=cached["usage"],
                )
            return Completion(cached["text"], cached.get("usage", {}), cached.get("finish_reason"))
        identifier = await self.ledger.begin(stage, "openai", identity)
        try:
            value = await self.delegate.send(body)
            # Store only normalized completion content, not raw provider payloads.
            result = {
                "text": value.text,
                "usage": safe_completion_usage(value.usage),
                "finish_reason": value.finish_reason,
            }
            await self.ledger.finish(identifier, result, usage=result["usage"])
            return value
        except ProviderFailure as error:
            if error.reason == "PROVIDER_FINISH_LENGTH":
                await self.ledger.finish(
                    identifier,
                    {"known_length_failure": True, "usage": safe_completion_usage(error.usage)},
                    usage=safe_completion_usage(error.usage),
                )
            else:
                await self.ledger.interrupt(identifier, "PROVIDER_REQUEST_UNCERTAIN")
            raise
        except BaseException:
            await asyncio.shield(self.ledger.interrupt(identifier, "PROVIDER_REQUEST_UNCERTAIN"))
            raise

    async def send_stream(self, body, on_content):
        # P2 deliberately uses score-first non-streamed calls; no request escapes
        # the durable send boundary if a caller accidentally enables streaming.
        raise RuntimeError("BENCHMARK_STREAMING_UNSUPPORTED")


class LedgerSpeakingProvider:
    def __init__(self, provider, ledger, config):
        self.provider = provider
        delegate = getattr(provider, "delegate", provider)
        delegate.transport = LedgerTransport(delegate.transport, ledger, config)

    async def ensure_ready(self):
        # Static readiness is checked before the worker; no readiness GET needed.
        return None

    async def complete(self, messages, schema, *, options=None):
        token = _stage.set(f"openai:{options.criterion}:{options.stage}:{options.attempt}")
        try:
            return await self.provider.complete(messages, schema, options=options)
        finally:
            _stage.reset(token)


class LedgerAnalyzer:
    def __init__(self, delegate, ledger, stage, identity):
        self.delegate, self.ledger, self.stage, self.identity = delegate, ledger, stage, identity

    async def analyze(self, audio, **kwargs):
        identity = fingerprint([self.identity, audio.cache_key, kwargs])
        cached = await self.ledger.cached(self.stage, identity)
        if cached is not None:
            return SpeechAnalysisResult.model_validate(cached)
        identifier = await self.ledger.begin(self.stage, self.identity["provider"], identity)
        try:
            value = await self.delegate.analyze(audio, **kwargs)
            # A partial/uncompleted stream is not declared free or complete.
            if not value.coverage.stream_completed:
                await self.ledger.interrupt(identifier, "SPEECH_STREAM_UNCERTAIN")
                raise RuntimeError("SPEECH_STREAM_UNCERTAIN")
            result = value.model_dump(mode="json")
            await self.ledger.finish(
                identifier,
                result,
                usage={"submitted_audio_ms": audio.duration_ms, "latency_ms": value.latency_ms},
            )
            return value
        except BaseException:
            await asyncio.shield(self.ledger.interrupt(identifier, "SPEECH_REQUEST_UNCERTAIN"))
            raise
