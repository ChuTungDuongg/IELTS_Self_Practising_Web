import asyncio
import json
import logging
from typing import Any

import httpx

from app.providers.writing_llm.base import (
    Completion,
    ProviderFailure,
    safe_finish_reason,
    validate_finish,
)

logger = logging.getLogger(__name__)


def api_base_url(value: str) -> str:
    """Accept either an origin or a /v1 base, without silently duplicating /v1."""
    url = httpx.URL(value)
    if (
        url.scheme not in {"http", "https"}
        or not url.host
        or url.userinfo
        or url.query
        or url.fragment
        or url.path.rstrip("/").endswith("/v1/v1")
    ):
        raise ValueError("Invalid provider base URL")
    base = str(url).rstrip("/")
    return base if url.path.rstrip("/").endswith("/v1") else base + "/v1"


class ChatCompletionHTTP:
    def __init__(self, base_url: str, headers: dict[str, str], timeout: float) -> None:
        self.base_url = api_base_url(base_url)
        self.headers = headers
        self.timeout = timeout

    async def _json_request(
        self, method: str, path: str, budget_seconds: float, body: dict[str, Any] | None = None
    ) -> Any:
        original_url = httpx.URL(self.base_url + path)
        url = original_url
        timeout_code = "AI_PROVIDER_STARTUP_TIMEOUT" if path == "/models" else "AI_PROVIDER_TIMEOUT"
        status = None
        try:
            async with (
                asyncio.timeout(budget_seconds),
                httpx.AsyncClient(timeout=budget_seconds, follow_redirects=False) as client,
            ):
                # Modal returns a result-poll URL after 150s. Follow only bounded,
                # same-origin 303s to the same path. GET retrieves the original
                # request; never submit the completion POST a second time.
                for redirects in range(5):
                    async with client.stream(
                        method, url, headers=self.headers, json=body
                    ) as response:
                        status = response.status_code
                        if status == 303:
                            location = response.headers.get("location")
                            target = response.url.join(location) if location else None
                            if (
                                redirects == 4
                                or not original_url.host.endswith((".modal.run", ".modal.direct"))
                                or target is None
                                or (target.scheme, target.host, target.port)
                                != (original_url.scheme, original_url.host, original_url.port)
                                or target.path != original_url.path
                                or target.userinfo
                                or target.fragment
                                or not target.query
                            ):
                                raise ProviderFailure("AI_PROVIDER_ENDPOINT_ERROR")
                            url, method, body = target, "GET", None
                            continue
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > 128_000:
                                raise ProviderFailure(
                                    "AI_PROVIDER_BAD_RESPONSE", reason="OUTPUT_TOO_LARGE"
                                )
                        if status in {401, 403}:
                            raise ProviderFailure("AI_PROVIDER_AUTH_FAILED")
                        if status in {400, 404} and self._missing_model(content):
                            raise ProviderFailure("AI_MODEL_UNAVAILABLE")
                        if status in {502, 503}:
                            raise ProviderFailure("AI_MODEL_UNAVAILABLE")
                        if status in {408, 504}:
                            raise ProviderFailure(timeout_code)
                        if status == 429:
                            raise ProviderFailure("AI_PROVIDER_RATE_LIMITED")
                        if 300 <= status < 500:
                            raise ProviderFailure("AI_PROVIDER_ENDPOINT_ERROR")
                        if status >= 500:
                            raise ProviderFailure("AI_PROVIDER_HTTP_ERROR")
                        if status != 200:
                            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE")
                        return json.loads(content)
        except (httpx.TimeoutException, TimeoutError):
            raise ProviderFailure(timeout_code) from None
        except httpx.RequestError:
            raise ProviderFailure("AI_PROVIDER_UNREACHABLE") from None
        except (ValueError, TypeError):
            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="INVALID_JSON") from None
        except ProviderFailure as exc:
            # Only fixed operations/codes/statuses. No URL, headers or response body.
            logger.warning(
                "AI provider failure: operation=%s code=%s status=%s", path, exc.code, status
            )
            raise

    @staticmethod
    def _missing_model(content: bytes) -> bool:
        try:
            error = json.loads(content).get("error", {})
            return error.get("code") in {"model_not_found", "model_not_available"} or (
                error.get("type") == "NotFoundError"
                and "model" in str(error.get("message", "")).lower()
            )
        except (ValueError, AttributeError, TypeError):
            return False

    async def ensure_model(self, model: str, budget_seconds: float) -> None:
        data = await self._json_request("GET", "/models", budget_seconds)
        try:
            available = [entry["id"] for entry in data["data"]]
            if model not in available:
                raise ProviderFailure("AI_MODEL_UNAVAILABLE")
        except (KeyError, TypeError):
            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE") from None

    async def send(self, body: dict[str, Any]) -> Completion:
        data = await self._json_request("POST", "/chat/completions", self.timeout, body)
        try:
            choice = data["choices"][0]
            finish = safe_finish_reason(choice.get("finish_reason"))
            logger.info("AI provider completion: finish_reason=%s", finish)
            validate_finish(finish)
            text = choice["message"]["content"]
            if not isinstance(text, str):
                raise ProviderFailure(
                    "AI_PROVIDER_BAD_RESPONSE", reason="MALFORMED_COMPLETION_ENVELOPE"
                )
            if not text.strip():
                raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="EMPTY_MODEL_CONTENT")
            # Discard reasoning fields, provider metadata and arbitrary usage properties.
            usage = data.get("usage") or {}
            safe_usage = {
                key: value
                for key, value in usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and type(value) is int
                and 0 <= value <= 10_000_000
            }
            return Completion(text, safe_usage, finish)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ProviderFailure(
                "AI_PROVIDER_BAD_RESPONSE", reason="MALFORMED_COMPLETION_ENVELOPE"
            ) from None
