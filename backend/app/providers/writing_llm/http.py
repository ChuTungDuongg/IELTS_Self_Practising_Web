import asyncio
import json
from typing import Any

import httpx

from app.providers.writing_llm.base import Completion, ProviderFailure


class ChatCompletionHTTP:
    def __init__(self, base_url: str, headers: dict[str, str], timeout: float) -> None:
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self.headers = headers
        self.timeout = timeout

    async def send(self, body: dict[str, Any]) -> Completion:
        try:
            async with (
                asyncio.timeout(self.timeout),
                httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client,
            ):
                async with client.stream(
                    "POST", self.url, headers=self.headers, json=body
                ) as response:
                    response.raise_for_status()
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 128_000:
                            raise ProviderFailure("INVALID_PROVIDER_OUTPUT")
            data = json.loads(content)
            choice = data["choices"][0]
            text = choice["message"]["content"]
            if not isinstance(text, str) or choice.get("finish_reason") != "stop":
                raise ProviderFailure("INVALID_PROVIDER_OUTPUT")
            # Discard reasoning fields, provider metadata and arbitrary usage properties.
            usage = data.get("usage") or {}
            safe_usage = {
                key: value
                for key, value in usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and type(value) is int
                and 0 <= value <= 10_000_000
            }
            return Completion(text, safe_usage)
        except (httpx.TimeoutException, TimeoutError):
            raise ProviderFailure("PROVIDER_TIMEOUT") from None
        except httpx.HTTPError:
            raise ProviderFailure("PROVIDER_HTTP_ERROR") from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ProviderFailure("INVALID_PROVIDER_OUTPUT") from None
