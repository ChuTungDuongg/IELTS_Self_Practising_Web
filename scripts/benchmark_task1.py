"""Offline Task 1 evaluation. From backend/: uv run python ../scripts/benchmark_task1.py."""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.evaluation.task1.anchor_sources import (  # noqa: E402
    AnchorSource,
    guard_leakage,
    load_anchor_manifest,
    load_postgres_anchors,
)
from app.evaluation.task1.architectures import architecture_configurations  # noqa: E402
from app.evaluation.task1.manifest import BenchmarkInputError, load_manifest  # noqa: E402
from app.evaluation.task1.runner import run_benchmark  # noqa: E402


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
    parser.add_argument("--scoring-version", choices=["v3", "v5", "both"], default="v5")
    parser.add_argument(
        "--architecture",
        choices=["direct", "mts", "direct-self-consistency", "anchor-pairwise", "all"],
    )
    parser.add_argument("--tree-node-budget", type=int, choices=[1, 2, 3], default=2)
    anchors = parser.add_mutually_exclusive_group()
    anchors.add_argument(
        "--anchor-source", choices=["postgres"], help="Read-only ACTIVE human bank snapshot."
    )
    anchors.add_argument(
        "--anchor-manifest", type=Path, help="Private version-1 evaluation bank JSON."
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
        if args.limit is not None and args.limit < 1:
            raise BenchmarkInputError("BENCHMARK_SELECTION_INVALID")
        items = load_manifest(args.manifest, args.split)
        settings = Settings(_env_file=ROOT / "backend" / ".env")
        source = (
            load_anchor_manifest(args.anchor_manifest)
            if args.anchor_manifest
            else asyncio.run(load_postgres_anchors(settings))
            if args.anchor_source
            else AnchorSource()
        )
        guard_leakage(items, source)  # Full selected split, before --limit or cache reuse.
        items = items[: args.limit] if args.limit else items
        # An explicitly used historical flag retains its MTS-only meaning.
        arguments = argv if argv is not None else sys.argv[1:]
        architecture = args.architecture or (
            "mts"
            if any(
                v == "--scoring-version" or v.startswith("--scoring-version=") for v in arguments
            )
            else "anchor-pairwise"
        )
        configs = architecture_configurations(
            settings,
            architecture,
            args.chart_specialist,
            scoring_version=args.scoring_version,
            tree_node_budget=args.tree_node_budget,
            source=source,
        )
        report = asyncio.run(
            run_benchmark(
                items,
                configs,
                output,
                resume=args.resume,
                dry_run=args.dry_run,
                settings=settings,
                anchor_source=source,
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
