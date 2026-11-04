"""Prepare and replay private MP3/WAV through the production CPU Speaking hybrid pipeline."""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.core.exceptions import AppError  # noqa: E402
from app.evaluation.speaking.manifest import BenchmarkInputError  # noqa: E402
from app.evaluation.speaking.replay_manifest import prepare, private_root  # noqa: E402
from app.evaluation.speaking.replay_runner import run_replay, safe_error  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "benchmarks/speaking/private/replay")
    parser.add_argument(
        "--prepare", action="store_true", help="Create an unverified segment template offline."
    )
    parser.add_argument("--mode", choices=("validate", "azure", "full"), default="validate")
    parser.add_argument(
        "--config", type=Path, help="Private dotenv; default backend/.env. No values are printed."
    )
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Explicit permission to submit selected audio/LLM evidence.",
    )
    parser.add_argument(
        "--max-audio-seconds",
        type=float,
        help="Total selected duration; Azure preview never exceeds 60s.",
    )
    parser.add_argument(
        "--max-estimated-cost-usd",
        type=float,
        help="Operator budget guard, not a provider invoice cap.",
    )
    parser.add_argument(
        "--estimated-cost-usd",
        type=float,
        help="Accept this upper TOTAL estimate including Azure/prosody and Luna.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume known failed Luna criteria; completed Azure is always reused.",
    )
    parser.add_argument(
        "--auto-segment",
        action="store_true",
        help="Run cached local diarization; never calls cloud providers.",
    )
    parser.add_argument(
        "--review-segments",
        action="store_true",
        help="Review private machine proposals without grading.",
    )
    parser.add_argument(
        "--setup-diarization-model",
        action="store_true",
        help="Explicit gated HF model download into the isolated tool cache.",
    )
    parser.add_argument(
        "--diagnose-diarization",
        action="store_true",
        help="Check isolated native runtime/storage offline, without a token or model download.",
    )
    parser.add_argument(
        "--confirm-candidate-speaker",
        help="Confirm one file-scoped speaker ID as the candidate; boundaries remain pending.",
    )
    parser.add_argument(
        "--set-part-boundaries", nargs=2, type=int, metavar=("PART2_MS", "PART3_MS")
    )
    parser.add_argument(
        "--confirm-file-parts",
        action="store_true",
        help="Explicitly confirm part1/part2/part3 file labels.",
    )
    parser.add_argument(
        "--question-context",
        type=Path,
        help="Private verified question JSON, indexed by proposal IDs.",
    )
    parser.add_argument("--edit-segment", nargs=3, metavar=("ID", "START_MS", "END_MS"))
    parser.add_argument("--exclude-segment", action="append", default=[], metavar="ID")
    parser.add_argument(
        "--acknowledge-segment",
        action="append",
        default=[],
        metavar="ID",
        help="Acknowledge a reviewed long silence; never permits known other-speaker overlap.",
    )
    parser.add_argument(
        "--approve-segments",
        action="store_true",
        help="Confirm same candidate across files and selected boundaries/content/Parts/questions; emit segments.json.",
    )
    parser.add_argument(
        "--diarization-python",
        type=Path,
        help="Existing isolated Python, default tools/speaking_diarization/.venv.",
    )
    parser.add_argument("--diarization-model-dir", type=Path)
    parser.add_argument("--diarization-device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--diarization-config",
        type=Path,
        help="Private resource/segmentation options; defaults 2 threads, 4GiB RSS, 30min timeout.",
    )
    args = parser.parse_args(argv)
    try:
        allowed = ROOT / "benchmarks/speaking/private"
        reports = ROOT / "benchmarks/speaking/reports/replay"
        # Do not let a symlinked private/report ancestor redirect sensitive files outside this checkout.
        if allowed.resolve() != allowed.absolute() or reports.resolve() != reports.absolute():
            raise BenchmarkInputError("REPLAY_PRIVATE_ROOT_REQUIRED")
        root = private_root(args.input, allowed)
        config = args.config or ROOT / "backend/.env"
        if args.config and (not config.is_file() or config.stat().st_size > 1024 * 1024):
            raise BenchmarkInputError("REPLAY_DOTENV_INVALID")
        settings = Settings(_env_file=config)
        review_action = (
            args.confirm_candidate_speaker
            or args.set_part_boundaries
            or args.confirm_file_parts
            or args.question_context
            or args.edit_segment
            or args.exclude_segment
            or args.acknowledge_segment
        )
        offline_action = (
            args.auto_segment
            or args.review_segments
            or args.setup_diarization_model
            or args.diagnose_diarization
            or review_action
            or args.approve_segments
        )
        if offline_action:
            if args.prepare or args.mode != "validate" or args.allow_live:
                raise BenchmarkInputError("REPLAY_MODE_CONFLICT")
            from app.evaluation.speaking.replay_diarization_cli import run_diarization_action

            run_diarization_action(root, settings, config, args)
            return 0
        if args.prepare:
            if args.mode != "validate" or args.allow_live:
                raise BenchmarkInputError("REPLAY_MODE_CONFLICT")
            manifest, created = prepare(root, settings)
            print("Created draft segments.json." if created else "Kept existing segments.json.")
            print(
                "Enter answer timestamps/questions, exclude examiner/preparation, then verify candidate-only audio."
            )
            print(f"Draft segments: {len(manifest.segments)}. No providers called.")
            return 0
        output, report = asyncio.run(
            run_replay(
                root,
                reports,
                settings,
                mode=args.mode,
                allow_live=args.allow_live,
                max_audio_seconds=args.max_audio_seconds
                if args.max_audio_seconds is not None
                else (900 if args.mode == "full" else 60),
                max_estimated_cost_usd=args.max_estimated_cost_usd,
                estimated_cost_usd=args.estimated_cost_usd,
                resume=args.resume,
            )
        )
        print(f"{report['status']}: {output.relative_to(ROOT).as_posix()}/summary.md")
        if report["limitations"]:
            print("Limitations: " + ", ".join(report["limitations"]))
        return 2 if report["status"] in {"FAILED", "CANCELLED"} else 0
    except (BenchmarkInputError, AppError) as error:
        code = safe_error(error)
        print(code, file=sys.stderr)
        if hasattr(error, "stage"):
            print(f"stage={error.stage}; exception_class={error.exception_class}", file=sys.stderr)
        if code in {
            "REPLAY_DIARIZATION_HF_AUTHENTICATION_FAILED",
            "REPLAY_DIARIZATION_HF_GATED_ACCESS_DENIED",
        }:
            print(
                "Check your private read token and model access: "
                "https://huggingface.co/pyannote/speaker-diarization-community-1",
                file=sys.stderr,
            )
        elif code in {
            "REPLAY_DIARIZATION_FFMPEG_SHARED_DLLS_MISSING",
            "REPLAY_DIARIZATION_FFMPEG_OVERRIDE_INVALID",
        }:
            print(
                "A complete shared FFmpeg 4–7 installation is required; static ffmpeg.exe alone is insufficient.",
                file=sys.stderr,
            )
        if code == "REPLAY_NO_AUDIO":
            print(
                "Add a local MP3/WAV to the input directory, then run --prepare.", file=sys.stderr
            )
        elif code == "REPLAY_SOURCE_AMBIGUOUS":
            print(
                "Use one full recording OR part1/part2/part3; remove duplicate formats.",
                file=sys.stderr,
            )
        return 2
    except KeyboardInterrupt:
        print("REPLAY_CANCELLED_INSPECT_CHECKPOINTS_BEFORE_RESUBMITTING", file=sys.stderr)
        return 130
    except Exception:
        # Settings validation and native/FFmpeg exceptions can contain secrets or private paths.
        print("REPLAY_CONFIGURATION_OR_PROCESSING_FAILED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
