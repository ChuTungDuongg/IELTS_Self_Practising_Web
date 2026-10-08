"""One readiness request and one tiny completion through the backend transport."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import monotonic

# app.py beside this script would otherwise shadow the backend's app package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.config import Settings  # noqa: E402
from app.core.exceptions import AppError  # noqa: E402
from app.providers.writing_llm import create_provider  # noqa: E402
from app.providers.writing_llm.base import ProviderFailure  # noqa: E402
from app.providers.writing_llm.vllm import VLLMProvider  # noqa: E402


async def smoke(base_url: str) -> None:
    # Run from backend/ so Settings reads its ignored .env, just like FastAPI.
    settings = Settings(
        ai_writing_enabled=True,
        ai_writing_provider="vllm",
        ai_writing_vllm_base_url=base_url,
        ai_writing_vllm_model="mistralai/Ministral-3-8B-Instruct-2512",
    )
    provider = create_provider(settings)
    assert isinstance(provider, VLLMProvider)
    started = monotonic()
    await provider.ensure_ready()
    print(
        f"Readiness passed: model={provider.model}; seconds={monotonic() - started:.1f}", flush=True
    )
    body = {
        "model": provider.model,
        "messages": [{"role": "user", "content": 'Return only this JSON object: {"ready": true}'}],
        "temperature": 0,
        "seed": 0,
        "max_tokens": 16,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "smoke",
                "schema": {
                    "type": "object",
                    "properties": {"ready": {"type": "boolean", "const": True}},
                    "required": ["ready"],
                    "additionalProperties": False,
                },
            },
        },
    }
    started = monotonic()
    result = await provider.transport.send(body)
    if json.loads(result.text) != {"ready": True}:
        raise ValueError("Unexpected smoke result")
    print(f"Text-only JSON completion passed: ready=true; seconds={monotonic() - started:.1f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Protected endpoint origin or /v1 base")
    args = parser.parse_args()
    try:
        asyncio.run(smoke(args.base_url))
    except ProviderFailure as exc:
        raise SystemExit(f"Smoke failed: {exc.code}: {exc.message}") from None
    except AppError as exc:
        raise SystemExit(f"Smoke failed: {exc.code}: {exc.message}") from None
    except (ValueError, KeyError, TypeError):
        raise SystemExit("Smoke failed: invalid configuration or completion.") from None


if __name__ == "__main__":
    main()
