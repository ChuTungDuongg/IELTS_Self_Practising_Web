"""One-command isolated Modal staging, using existing backend AI credentials."""

import argparse
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
    if set(values) - (REQUIRED | DEFAULTS.keys() | {"MODAL_CLI_PATH"}):
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / ".env.modal")
    parser.add_argument(
        "--provider",
        choices=("vllm", "openai"),
        default="vllm",
        help="Both graders' provider; OpenAI reads private backend/.env settings",
    )
    parser.add_argument(
        "--no-asr", action="store_true", help="Disable the optional ASR GPU service"
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
        cli = values.pop("MODAL_CLI_PATH", None) or shutil.which("modal")
        if not cli or not Path(cli).is_file():
            raise ValueError("Modal CLI missing; set MODAL_CLI_PATH in .env.modal")
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("AI_WRITING_", "SPEAKING_AI_"))
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
            if args.provider == "openai":
                environment.update(openai_environment(settings))
                if environment["IELTS_WEB_SPEAKING_ASR_ENABLED"].lower() in {
                    "true",
                    "1",
                    "yes",
                } and not (settings.ai_writing_modal_key and settings.ai_writing_modal_secret):
                    raise ValueError(
                        "ASR requires AI_WRITING_MODAL_KEY and AI_WRITING_MODAL_SECRET; "
                        "use --no-asr for OpenAI grading without ASR"
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
                f"provider {args.provider}; "
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
