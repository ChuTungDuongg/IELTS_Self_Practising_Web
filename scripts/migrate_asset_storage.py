"""Operator-invoked, source-preserving copy; dry-run is the default."""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.storage.migration import (  # noqa: E402
    SUCCESS,
    copy_keys,
    iter_object_keys,
    reconcile,
    reference_map,
    write_report,
)
from app.storage.operations import (  # noqa: E402
    database_inventory,
    probe_target,
    require_write_confirmation,
    storage_target,
    validate_distinct,
    validate_report_path,
)


def storage_from_environment(prefix, backend):
    return storage_target(prefix, backend).storage


async def inventory(database_url):
    async with database_inventory(database_url) as (references, _, _):
        return sorted(reference_map(references))


async def load_inventory(database_url):
    async with database_inventory(database_url) as (references, cleanup, _):
        return references, cleanup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=("local", "s3", "r2"))
    parser.add_argument("--destination", choices=("local", "s3", "r2"))
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=1)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--copy", action="store_true", help="Copy; omission performs dry-run")
    action.add_argument("--inventory-only", action="store_true")
    action.add_argument("--reconcile", action="store_true")
    parser.add_argument(
        "--list-orphans", action="store_true", help="Explicit paginated namespace listing"
    )
    parser.add_argument("--listing-limit", type=int, default=100000)
    parser.add_argument("--report", type=Path, required=True, help="Private JSON checkpoint")
    parser.add_argument("--expected-report", type=Path)
    parser.add_argument("--confirm-target")
    parser.add_argument("--maintenance-window", action="store_true")
    parser.add_argument("--allow-cross-environment", action="store_true")
    args = parser.parse_args(argv)
    try:
        validate_report_path(args.report)
    except ValueError:
        print("Report must be a JSON file outside asset namespaces.", file=sys.stderr)
        return 1
    report = {"format_version": 1, "operation": "migration", "complete": False, "results": []}
    try:
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise ValueError("DATABASE_URL must be set explicitly")
        source = storage_target("SOURCE", args.source)
        report["source"] = source.description()
        probe_target(source, source=True)
        references, cleanup = asyncio.run(load_inventory(url))
        report["pending_cleanup_keys"] = cleanup
        if args.inventory_only:
            report.update(operation="inventory", references=[asdict(item) for item in references])
            reference_map(references)
            report["complete"] = True
        elif args.reconcile:
            report["operation"] = "reconciliation"
            expected = None
            if args.expected_report:
                previous = json.loads(args.expected_report.read_text(encoding="utf-8"))
                expected = {row["key"]: row for row in previous["results"] if row.get("sha256")}
                if set(expected) != {item.key for item in references}:
                    raise ValueError("Expected report does not cover current references")
            rows = reconcile(source.storage, references, expected=expected)
            report.update(
                results=[asdict(row) for row in rows],
                complete=all(row.status in SUCCESS for row in rows),
            )
        else:
            if not args.destination:
                raise ValueError("--destination is required for migration")
            destination = storage_target("DESTINATION", args.destination)
            report["destination"] = destination.description()
            validate_distinct(source.storage, destination.storage)
            probe_target(destination)
            if args.copy:
                require_write_confirmation(
                    destination,
                    args.confirm_target,
                    args.maintenance_window,
                    source_environment=source.environment,
                    allow_cross_environment=args.allow_cross_environment,
                )
            refs = reference_map(references)
            report.update(dry_run=not args.copy, required_objects=len(refs))

            def checkpoint(rows):
                report["results"] = [
                    {
                        **row,
                        "source_backend": source.backend,
                        "destination_backend": destination.backend,
                    }
                    for row in rows
                ]
                write_report(args.report, report)

            rows = copy_keys(
                source.storage,
                destination.storage,
                refs,
                dry_run=not args.copy,
                workers=args.workers,
                references=refs,
                progress=checkpoint,
            )
            checkpoint([asdict(row) for row in rows])
            report["complete"] = len(rows) == len(refs) and all(
                row.status in SUCCESS for row in rows
            )
        if args.list_orphans:
            if not 1 <= args.listing_limit <= 1000000:
                raise ValueError("Listing limit must be between 1 and 1000000")
            referenced = {item.key for item in references}
            report.update(potential_orphans=[], listing_truncated=False)
            for index, key in enumerate(iter_object_keys(source.storage)):
                if index >= args.listing_limit:
                    report["listing_truncated"] = True
                    break
                if key not in referenced and key != ".gitkeep" and not key.endswith("/.gitkeep"):
                    report["potential_orphans"].append(key)
        write_report(args.report, report)
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k in {"complete", "dry_run", "source", "destination", "operation"}
                }
            )
        )
        allowed = SUCCESS | ({"would_copy"} if report.get("dry_run") else set())
        return 0 if all(row["status"] in allowed for row in report["results"]) else 1
    except (Exception, KeyboardInterrupt) as error:
        # Provider/database diagnostics can contain credentials: emit only the error type.
        report.update(complete=False, failure=type(error).__name__)
        write_report(args.report, report)
        print(
            f"Storage migration failed: {type(error).__name__}. Check configuration and connectivity.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
