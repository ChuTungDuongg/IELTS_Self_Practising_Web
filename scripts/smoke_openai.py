"""Opt-in, one tiny paid completion; never print credentials or model output."""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import OpenAIStageOverride, Settings  # noqa: E402
from app.providers.writing_llm import create_provider  # noqa: E402
from app.providers.writing_llm.base import CompletionOptions, ProviderFailure  # noqa: E402
from app.providers.writing_llm.http import api_base_url  # noqa: E402


async def smoke(settings):
    started = time.perf_counter()
    result = {
        "status": "FAIL",
        "provider": "openai",
        "model": "gpt-6-luna",
        "completion_requests": 0,
        "whole_grading_pipeline": "NOT_VERIFIED",
        "modal_deployment": "NOT_VERIFIED",
    }
    try:
        if (
            settings.ai_writing_provider != "openai"
            or settings.ai_writing_openai_model != "gpt-6-luna"
            or api_base_url(settings.ai_writing_openai_base_url) != "https://api.openai.com/v1"
        ):
            result["code"] = "OPENAI_SMOKE_CONFIG_REQUIRED"
            return result
        # Connectivity smoke intentionally has its own fixed tiny inference
        # settings, not the grading profile. It cannot trigger budget repair.
        smoke_settings = settings.model_copy(
            update={
                "ai_writing_openai_repair_completion_tokens": 128,
                "ai_writing_openai_stage_overrides": {
                    "default.default": OpenAIStageOverride(
                        reasoning_effort="none",
                        total_completion_tokens=128,
                    )
                },
            }
        )
        provider = create_provider(smoke_settings)
        result["inference"] = {
            "reasoning_effort": "none",
            "total_completion_tokens": 128,
            "budget_repairs": 0,
        }
        # No readiness/model-list call and no repair loop. Exactly one completion
        # is attempted; reaching the model is checked by that response itself.
        result["completion_requests"] = 1
        completion = await provider.complete(
            [{"role": "user", "content": 'Return exactly this JSON object: {"ready":true}.'}],
            {"type": "object", "properties": {"ready": {"type": "boolean"}}, "required": ["ready"]},
            options=CompletionOptions(max_tokens=64),
        )
        result["usage"] = completion.usage
        if json.loads(completion.text) != {"ready": True}:
            result["code"] = "OPENAI_SMOKE_INVALID_RESPONSE"
        else:
            result["status"] = "PASS"
    except ProviderFailure as error:
        result["code"] = error.code
        result["usage"] = error.usage
    except Exception:
        # Neither configuration errors nor provider errors may print a traceback
        # containing headers, secrets, URLs, request bodies or source material.
        result["code"] = "OPENAI_SMOKE_FAILED"
    finally:
        result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid-request", action="store_true")
    parser.add_argument("--env-file", type=Path, default=ROOT / "backend/.env")
    parser.add_argument("--output", type=Path, help="Optional sanitized JSON evidence file")
    args = parser.parse_args(argv)
    if not args.allow_paid_request:
        parser.error("Explicit --allow-paid-request is required; this consumes API credits")
    try:
        result = asyncio.run(smoke(Settings(_env_file=args.env_file)))
    except Exception:
        result = {
            "status": "FAIL",
            "code": "OPENAI_SMOKE_CONFIG_INVALID",
            "completion_requests": 0,
            "modal_deployment": "NOT_VERIFIED",
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
