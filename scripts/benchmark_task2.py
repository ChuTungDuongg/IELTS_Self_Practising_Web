"""Offline Task 2 evaluation; requires local JSONL and provider configuration only."""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.evaluation.task2.manifest import BenchmarkInputError, load_manifest  # noqa: E402
from app.evaluation.task2.runner import configuration, run_benchmark  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Writing Task 2 human score agreement using current production scoring."
    )
    parser.add_argument(
        "--manifest", type=Path, required=True, help="Local schema-version-1 JSONL file."
    )
    parser.add_argument("--split", choices=["dev", "holdout"], required=True)
    parser.add_argument("--limit", type=int, help="Maximum sequential samples.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate and plan with zero provider calls."
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse matching successful checkpoints; retry failed samples.",
    )
    parser.add_argument("--output", type=Path, help="Local output directory.")
    parser.add_argument(
        "--max-concurrent-llm-requests",
        type=int,
        choices=range(1, 5),
        help="Production criterion request limit, 1..4. Samples execute sequentially.",
    )
    args = parser.parse_args(argv)
    output = args.output or ROOT / "benchmarks/writing_task2/reports" / args.split
    try:
        items = load_manifest(args.manifest, args.split, args.limit)
        settings = Settings(_env_file=ROOT / "backend/.env")
        config = configuration(settings, args.max_concurrent_llm_requests)
        report = asyncio.run(
            run_benchmark(
                items, config, output, resume=args.resume, dry_run=args.dry_run, settings=settings
            )
        )
    except BenchmarkInputError as error:
        print(str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(
            "BENCHMARK_INTERRUPTED: completed samples are checkpointed; use --resume.",
            file=sys.stderr,
        )
        return 130
    except Exception:
        print(
            "BENCHMARK_FAILED: check local paths/configuration; safe reports may be available.",
            file=sys.stderr,
        )
        return 2
    failures = sum(row["status"] == "FAILED" for row in report["records"])
    print(
        f"{report['status']}: samples={report['sample_count']} runs={len(report['records'])} failed={failures}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
