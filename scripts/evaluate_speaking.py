"""Offline reports by default; manual live scoring requires an explicit flag."""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.evaluation.speaking.manifest import (  # noqa: E402
    BenchmarkInputError,
    load_manifest,
    load_predictions,
)
from app.evaluation.speaking.report import build_report, write_reports  # noqa: E402
from app.evaluation.speaking.runner import evaluate_samples  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--predictions", type=Path, help="Versioned score-only JSON; never constructs providers."
    )
    parser.add_argument("--validate-manifest", "--dry-run", action="store_true")
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Explicitly invoke configured production ASR/LLM providers.",
    )
    parser.add_argument(
        "--config", type=Path, help="Private dotenv file for Settings (default: backend .env)."
    )
    parser.add_argument("--max-samples", type=int)
    parser.add_argument("--minimum-subgroup-samples", type=int, default=20)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        # 1. Validate before provider construction or report writes.
        items = load_manifest(args.manifest, args.max_samples)
        if args.validate_manifest:
            print(f"Validated {len(items)} labelled samples; no providers invoked.")
            return 0
        if args.output is None:
            raise BenchmarkInputError("BENCHMARK_OUTPUT_REQUIRED")
        if args.allow_live and args.predictions:
            raise BenchmarkInputError("BENCHMARK_MODE_CONFLICT")
        if not args.predictions and not args.allow_live:
            raise BenchmarkInputError("LIVE_SCORING_REQUIRES_EXPLICIT_FLAG")
        destinations = {
            args.output.resolve() / name
            for name in (
                "predictions.json",
                "summary.json",
                "summary.md",
                "samples.csv",
                "samples.jsonl",
            )
        }
        if (
            args.manifest.resolve() in destinations
            or args.predictions
            and args.predictions.resolve() in destinations
        ):
            raise BenchmarkInputError("BENCHMARK_INPUT_OUTPUT_OVERLAP")
        if not 5 <= args.minimum_subgroup_samples <= 10000:
            raise BenchmarkInputError("BENCHMARK_SUBGROUP_MINIMUM_INVALID")
        # 2. Imported offline scores or explicitly configured current scorer.
        if args.predictions:
            result = load_predictions(args.predictions)
        else:
            settings = Settings(_env_file=args.config) if args.config else Settings()
            result = asyncio.run(
                evaluate_samples(
                    items, args.manifest.resolve().parent, args.output, settings, resume=args.resume
                )
            )
        # 3. Pure score-only metrics/report generation.
        report = build_report(items, result, minimum_subgroup_samples=args.minimum_subgroup_samples)
        write_reports(args.output, items, result, report)
        print(
            f"Reported {len(items)} labelled samples; overall failure rate={report['criteria']['overall']['failure_rate']}."
        )
        return 0
    except BenchmarkInputError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        print("BENCHMARK_PROCESSING_FAILED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
