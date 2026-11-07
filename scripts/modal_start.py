"""One-command isolated Modal staging, using existing backend AI credentials."""

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402

VAD_SHA256 = "597d30b3ec076608d059477bb14cfeffdf951bf5cae370d38f65d33bbfe82004"

REQUIRED = {
    "MODAL_PROFILE",
    "MODAL_ENVIRONMENT",
    "IELTS_MODAL_MODE",
    "IELTS_MODAL_STORAGE_BACKEND",
    "IELTS_MODAL_DATABASE_MODE",
    "IELTS_MODAL_DATABASE_VOLUME",
    "IELTS_MODAL_ASSETS_VOLUME",
    "IELTS_MODAL_SNAPSHOTS_VOLUME",
    "IELTS_MODAL_CONFIG_SECRET",
}
DEFAULTS = {
    "IELTS_MODAL_REQUIRE_ASSET_ISOLATION": "true",
    "IELTS_WEB_AI_ENABLED": "true",
    "IELTS_WEB_SPEAKING_ASR_ENABLED": "true",
    "IELTS_WEB_SPEAKING_PROFILE": "legacy",
    "IELTS_WEB_SPEAKING_VAD_MODEL_PATH": "storage/models/silero-v6.0.onnx",
    "IELTS_WEB_CHART_SPECIALIST_ENABLED": "false",
    "IELTS_WRITING_LLM_PROFILE": "cost",
    "IELTS_WRITING_LLM_SCALEDOWN_SECONDS": "60",
}


def configuration(path):
    if not path.is_file():
        raise ValueError(
            "Missing .env.modal; copy .env.modal.example and select existing staging resources"
        )
    values = {
        key: value.strip() if isinstance(value, str) else ""
        for key, value in dotenv_values(path, interpolate=False).items()
    }
    if set(values) - (REQUIRED | DEFAULTS.keys() | {"MODAL_CLI_PATH", "IELTS_WEB_AI_PROVIDER"}):
        raise ValueError("Unsupported .env.modal field; keep credentials in backend/.env")
    for key in REQUIRED:
        if not values.get(key):
            raise ValueError(f"Missing configuration: {key}")
    for key in DEFAULTS:
        if key in values and not values[key]:
            raise ValueError(f"Empty configuration: {key}")
    if (
        values["IELTS_MODAL_MODE"] != "dev"
        or values["IELTS_MODAL_STORAGE_BACKEND"] != "local"
        or values["IELTS_MODAL_DATABASE_MODE"] != "embedded"
        or values["IELTS_MODAL_ASSETS_VOLUME"] == "ielts-web-assets"
        or values["IELTS_MODAL_DATABASE_VOLUME"] in {"ielts-web-postgres", "ielts-web-postgres-dev"}
        or values["IELTS_MODAL_CONFIG_SECRET"] == "ielts-web-config"
    ):
        raise ValueError(
            "This launcher requires isolated dev Volumes and a dedicated staging Secret"
        )
    values = {**DEFAULTS, **values}
    # Isolation is not optional for this convenience launcher.
    values["IELTS_MODAL_REQUIRE_ASSET_ISOLATION"] = "true"
    return values


def openai_environment(settings):
    """Validate locally and forward backend-only settings through ephemeral Secrets."""
    from app.core.exceptions import AppError
    from app.providers.speaking_llm import create_provider as speaking_provider
    from app.providers.writing_llm import create_provider as writing_provider

    selected = settings.model_copy(
        update={
            "ai_writing_enabled": True,
            "ai_writing_provider": "openai",
            "speaking_ai_enabled": True,
            "speaking_ai_provider": "openai",
        }
    )
    try:
        # Constructors validate capabilities/configuration without any API call.
        writing_provider(selected)
        speaking_provider(selected)
    except AppError:
        raise ValueError(
            "OpenAI configuration invalid; check AI_WRITING_OPENAI_API_KEY, model, "
            "reasoning/token budgets and Speaking overrides in backend/.env"
        ) from None
    environment = {}
    for name, value in selected.model_dump(mode="json", exclude_none=True).items():
        if not name.startswith(("ai_writing_", "speaking_ai_")):
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, separators=(",", ":"))
        elif isinstance(value, bool):
            value = str(value).lower()
        else:
            value = str(value)
        environment[name.upper()] = value
    # Empty means inherit; override a stale model in the persistent staging Secret.
    environment["SPEAKING_AI_MODEL"] = selected.speaking_ai_model or ""
    return environment


def hybrid_environment(settings, model_path):
    """Validate speech configuration without contacting Azure or loading native SDKs."""
    key = settings.speaking_azure_key
    key = key.get_secret_value() if key else ""
    if not key.strip() or not settings.speaking_azure_region:
        raise ValueError(
            "Configure SPEAKING_AZURE_KEY and SPEAKING_AZURE_REGION in backend/.env; "
            "see docs/modal-web.md#speaking-hybrid-cpu. No service was started."
        )
    from app.providers.speech_analysis.azure_policy import billing_authorized

    if not billing_authorized(settings):
        raise ValueError(
            "Azure billing blocked: set SPEAKING_AZURE_BILLING_MODE after verifying the resource "
            "outside the worker. Paid mode also requires SPEAKING_AZURE_ALLOW_PAID=true."
        )
    path = Path(model_path)
    path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_file():
        raise ValueError(
            "Missing pinned VAD asset; run python scripts/setup_speaking_vad.py "
            "storage/models/silero-v6.0.onnx before starting Modal"
        )
    if (
        path.stat().st_size > 16 * 1024 * 1024
        or hashlib.sha256(path.read_bytes()).hexdigest() != VAD_SHA256
    ):
        raise ValueError("Pinned VAD checksum mismatch; rerun scripts/setup_speaking_vad.py")
    environment = {"IELTS_WEB_SPEAKING_VAD_MODEL_PATH": str(path), "SPEAKING_AZURE_KEY": key}
    for name, value in settings.model_dump(mode="json", exclude_none=True).items():
        if (
            name.startswith(("speaking_azure_", "speaking_lexical_"))
            and name != "speaking_azure_key"
        ) or name in {
            "speaking_asr_base_url",
            "speaking_asr_model",
            "speaking_asr_version",
            "speaking_asr_model_revision",
            "speaking_asr_model_directory",
        }:
            environment[name.upper()] = (
                str(value).lower() if isinstance(value, bool) else str(value)
            )
    return environment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / ".env.modal")
    parser.add_argument(
        "--provider",
        choices=("vllm", "openai"),
        help="Both graders' provider; OpenAI reads private backend/.env settings",
    )
    parser.add_argument("--speaking-profile", choices=("legacy", "speaking_hybrid_v1"))
    parser.add_argument("--asr-provider", choices=("azure", "modal", "local"))
    parser.add_argument(
        "--no-asr",
        action="store_true",
        help="Disable speech analysis/transcription for either profile",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--check", action="store_true", help="Check configuration offline; do not deploy"
    )
    action.add_argument("--stop", action="store_true", help="Stop only ielts-practice-web-dev")
    action.add_argument(
        "--deploy", action="store_true", help="Deploy persistently instead of serving"
    )
    args = parser.parse_args(argv)
    try:
        values = configuration(args.config)
        profile = args.speaking_profile or values["IELTS_WEB_SPEAKING_PROFILE"]
        if profile not in {"legacy", "speaking_hybrid_v1"}:
            raise ValueError("IELTS_WEB_SPEAKING_PROFILE must be legacy or speaking_hybrid_v1")
        configured_provider = args.provider or values.get("IELTS_WEB_AI_PROVIDER")
        provider = configured_provider or ("openai" if profile == "speaking_hybrid_v1" else "vllm")
        if provider not in {"openai", "vllm"}:
            raise ValueError("IELTS_WEB_AI_PROVIDER must be openai or vllm")
        values["IELTS_WEB_SPEAKING_PROFILE"] = profile
        values["IELTS_WEB_AI_PROVIDER"] = provider
        values["IELTS_WEB_SPEAKING_AI_PROVIDER"] = provider
        cli = values.pop("MODAL_CLI_PATH", None) or shutil.which("modal")
        if not cli or not Path(cli).is_file():
            raise ValueError("Modal CLI missing; set MODAL_CLI_PATH in .env.modal")
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(
                ("AI_WRITING_", "SPEAKING_AI_", "SPEAKING_AZURE_", "SPEAKING_VAD_")
            )
        }
        environment.update(values)
        if args.no_asr:
            environment["IELTS_WEB_SPEAKING_ASR_ENABLED"] = "false"
        if args.stop:
            command = [
                cli,
                "app",
                "stop",
                "ielts-practice-web-dev",
                "--yes",
                "--env",
                values["MODAL_ENVIRONMENT"],
            ]
        else:
            try:
                settings = Settings(_env_file=ROOT / "backend/.env")
            except Exception:
                raise ValueError("Cannot load backend/.env; verify backend configuration") from None
            provider = configured_provider or getattr(settings, "ai_writing_provider", "vllm")
            if provider not in {"openai", "vllm"}:
                raise ValueError("AI_WRITING_PROVIDER must be openai or vllm")
            asr_provider = args.asr_provider or getattr(settings, "speaking_asr_provider", "modal")
            profile = (
                "speaking_hybrid_v1"
                if asr_provider == "azure"
                else (args.speaking_profile or "legacy")
            )
            speech_enabled = getattr(settings, "speaking_asr_enabled", True) and environment[
                "IELTS_WEB_SPEAKING_ASR_ENABLED"
            ].lower() in {
                "true",
                "1",
                "yes",
            }
            if speech_enabled and asr_provider == "local":
                raise ValueError(
                    "Modal Web does not include local ASR; select azure/modal or use --no-asr"
                )
            environment.update(
                IELTS_WEB_AI_PROVIDER=provider,
                IELTS_WEB_SPEAKING_AI_PROVIDER=provider,
                IELTS_WEB_SPEAKING_PROFILE=profile,
                IELTS_WEB_SPEAKING_ASR_PROVIDER=asr_provider,
                IELTS_WEB_SPEAKING_ASR_ENABLED=str(speech_enabled).lower(),
                SPEAKING_ASR_PROVIDER=asr_provider,
                SPEAKING_ASR_ENABLED=str(speech_enabled).lower(),
            )
            for name in ("speaking_asr_language", "speaking_processing_timeout_seconds"):
                if hasattr(settings, name):
                    environment[name.upper()] = str(getattr(settings, name))
            if asr_provider == "azure" and speech_enabled:
                environment.update(
                    hybrid_environment(settings, values["IELTS_WEB_SPEAKING_VAD_MODEL_PATH"])
                )
            else:
                environment.pop("IELTS_WEB_SPEAKING_VAD_MODEL_PATH", None)
            if provider == "openai":
                environment.update(openai_environment(settings))
                if (
                    (
                        asr_provider == "modal"
                        or getattr(settings, "speaking_lexical_asr_provider", "azure_pa")
                        == "faster_whisper_modal"
                    )
                    and speech_enabled
                    and not (settings.ai_writing_modal_key and settings.ai_writing_modal_secret)
                ):
                    raise ValueError(
                        "ASR requires AI_WRITING_MODAL_KEY and AI_WRITING_MODAL_SECRET; "
                        "use --no-asr for OpenAI grading without ASR"
                    )
                if (
                    asr_provider == "modal"
                    or getattr(settings, "speaking_lexical_asr_provider", "azure_pa")
                    == "faster_whisper_modal"
                ) and speech_enabled:
                    environment.update(
                        AI_WRITING_MODAL_KEY=settings.ai_writing_modal_key,
                        AI_WRITING_MODAL_SECRET=settings.ai_writing_modal_secret,
                    )
            elif not settings.ai_writing_modal_key or not settings.ai_writing_modal_secret:
                raise ValueError(
                    "Configure AI_WRITING_MODAL_KEY and AI_WRITING_MODAL_SECRET in backend/.env"
                )
            else:
                environment.update(
                    AI_WRITING_PROVIDER="vllm",
                    SPEAKING_AI_PROVIDER="vllm",
                    AI_WRITING_MODAL_KEY=settings.ai_writing_modal_key,
                    AI_WRITING_MODAL_SECRET=settings.ai_writing_modal_secret,
                )
            print(
                f"Modal {values['MODAL_PROFILE']}/{values['MODAL_ENVIRONMENT']}: "
                f"ielts-practice-web-dev; AI {'enabled' if values['IELTS_WEB_AI_ENABLED'] == 'true' else 'disabled'}, "
                f"provider {provider}; speech profile {profile}; "
                f"ASR {environment['IELTS_WEB_SPEAKING_ASR_ENABLED']}."
            )
            if args.check:
                print("Configuration checked offline; no deployment or AI request was made.")
                return 0
            if not args.deploy:
                # Share the terminal so Modal receives Ctrl+C. Keep this parent
                # waiting while Modal closes its ephemeral App and its workers;
                # subprocess.run would kill the child on KeyboardInterrupt.
                process = subprocess.Popen(
                    [cli, "serve", "deploy/modal/app.py"], cwd=ROOT, env=environment
                )
                previous = signal.signal(signal.SIGINT, lambda *_: None)
                try:
                    return process.wait()
                finally:
                    signal.signal(signal.SIGINT, previous)
            command = [cli, "deploy", "deploy/modal/app.py", "--strategy", "recreate"]
        return subprocess.run(command, cwd=ROOT, env=environment).returncode
    except (ValueError, OSError) as error:
        # Report our validation messages, but never SDK/configuration tracebacks.
        message = str(error) if isinstance(error, ValueError) else "Cannot execute Modal CLI"
        print(f"Modal startup: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
