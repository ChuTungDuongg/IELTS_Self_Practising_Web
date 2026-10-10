"""Offline Task 1 evaluation. From backend/: uv run python ../scripts/benchmark_task1.py."""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.evaluation.task1.manifest import BenchmarkInputError, load_manifest  # noqa: E402
from app.evaluation.task1.runner import configurations, run_benchmark  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Task 1 perception and human score agreement using configured production providers."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Local version-1 JSONL manifest. Relative image paths resolve beside it.",
    )
    parser.add_argument("--split", choices=["dev", "holdout"], required=True)
    parser.add_argument(
        "--limit", type=int, help="Maximum samples, before configuration expansion."
    )
    parser.add_argument("--chart-specialist", choices=["off", "on", "both"], default="off")
    parser.add_argument(
        "--scoring-version",
        choices=["v3", "v5", "v6", "both"],
        default="v6",
        help="v6 production candidate (default); both compares v5 baseline with v6; v3 is historical",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate local data and plan only; no provider calls.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse matching successful checkpoints; retry failed samples.",
    )
    parser.add_argument(
        "--output", type=Path, help="Local output directory; defaults to ignored benchmark reports."
    )
    args = parser.parse_args(argv)
    output = (
        args.output
        or ROOT
        / "benchmarks"
        / "writing_task1"
        / "reports"
        / f"{args.split}-{args.scoring_version}-{args.chart_specialist}"
    )
    try:
        items = load_manifest(args.manifest, args.split, args.limit)
        settings = Settings(_env_file=ROOT / "backend" / ".env")
        configs = configurations(settings, args.scoring_version, args.chart_specialist)
        report = asyncio.run(
            run_benchmark(
                items, configs, output, resume=args.resume, dry_run=args.dry_run, settings=settings
            )
        )
    except BenchmarkInputError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(
            "BENCHMARK_INTERRUPTED: completed samples are checkpointed; use --resume.",
            file=sys.stderr,
        )
        return 130
    except Exception:
        # No traceback, provider body, settings or invalid sample data on stdout.
        print(
            "BENCHMARK_FAILED: check local paths/configuration; safe reports may be available.",
            file=sys.stderr,
        )
        return 2
    failures = sum(record["status"] == "FAILED" for record in report["records"])
    print(
        f"{report['status']}: samples={report['sample_count']} runs={report['evaluated_run_count']} failed={failures}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
