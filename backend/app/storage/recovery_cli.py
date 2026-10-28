"""Explicit portable workflows used by the existing backup/restore entrypoints."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from app.backup_restore import DATABASE_FILE, MANIFEST_FILE, sha256_file
from app.storage.migration import SUCCESS, write_report
from app.storage.operations import (
    check_restore_database,
    postgres_tool,
    probe_target,
    require_write_confirmation,
    storage_target,
    validate_report_path,
)
from app.storage.recovery import (
    create_portable_backup,
    reconcile_restored_database,
    restore_objects,
    verify_portable_backup,
)


def backup_main(argv=None):
    parser = argparse.ArgumentParser(
        description="Portable PostgreSQL + referenced-object v2 backup"
    )
    parser.add_argument("--source", required=True, choices=("local", "s3", "r2"))
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--maintenance-window", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate_report_path(args.report)
    except ValueError:
        print("Report must be a JSON file outside asset namespaces.", file=sys.stderr)
        return 1
    report = {"operation": "backup", "complete": False}
    try:
        source = storage_target("SOURCE", args.source)
        probe_target(source, source=True)
        path = asyncio.run(
            create_portable_backup(
                os.environ.get("DATABASE_URL", ""),
                source,
                args.backup_root,
                maintenance=args.maintenance_window,
            )
        )
        report.update(
            complete=True, backup_dir=str(path), manifest_sha256=sha256_file(path / MANIFEST_FILE)
        )
        write_report(args.report, report)
        print(json.dumps(report))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        report.update(complete=False, failure=type(error).__name__)
        write_report(args.report, report)
        print(
            f"Portable backup incomplete: {type(error).__name__}; preserve private incomplete bundle for investigation.",
            file=sys.stderr,
        )
        return 1


def restore_main(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify portable v2 backup; explicitly recover into an isolated destination"
    )
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--destination", choices=("local", "s3", "r2"))
    parser.add_argument("--report", type=Path, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--verify-only", action="store_true")
    action.add_argument("--restore-objects", action="store_true")
    action.add_argument("--restore-database", action="store_true")
    action.add_argument("--database-preflight", action="store_true")
    action.add_argument("--reconcile-database", action="store_true")
    parser.add_argument("--confirm-target")
    parser.add_argument("--confirm-database")
    parser.add_argument(
        "--confirm-backup", help="Reviewed manifest SHA-256 from a trusted preflight"
    )
    parser.add_argument("--maintenance-window", action="store_true")
    parser.add_argument("--allow-cross-environment", action="store_true")
    args = parser.parse_args(argv)
    try:
        validate_report_path(args.report, backup_dir=args.backup_dir.resolve())
    except ValueError:
        print("Report must be outside the backup and asset namespaces.", file=sys.stderr)
        return 1
    report = {"operation": "restore", "complete": False, "results": []}
    try:
        manifest = verify_portable_backup(args.backup_dir)
        report["manifest_sha256"] = sha256_file(args.backup_dir / MANIFEST_FILE)
        if args.verify_only:
            report.update(operation="backup-verification", complete=True)
        else:
            if not args.destination:
                raise ValueError("--destination is required unless --verify-only")
            destination = storage_target("DESTINATION", args.destination)
            if destination.environment != "recovery":
                raise ValueError("Portable restore requires DESTINATION_ENVIRONMENT=recovery")
            if destination.target_id == manifest["source"].get("target_id"):
                raise ValueError("Restore destination must differ from backup source")
            report["destination"] = destination.description()
            probe_target(destination)
            execute = args.restore_objects or args.restore_database
            if execute:
                require_write_confirmation(
                    destination,
                    args.confirm_target,
                    args.maintenance_window,
                    source_environment=manifest["source"]["environment"],
                    allow_cross_environment=args.allow_cross_environment,
                )
                if args.confirm_backup != report["manifest_sha256"]:
                    raise ValueError("Pass --confirm-backup with the reviewed manifest SHA-256")
            if args.restore_database or args.database_preflight:
                url = os.environ.get("RESTORE_DATABASE_URL", "")
                report["database_id"] = asyncio.run(
                    check_restore_database(
                        url,
                        source_id=manifest["source_database_id"],
                        confirmation=args.confirm_database if args.restore_database else None,
                    )
                )
                if args.restore_database and not args.confirm_database:
                    raise ValueError("--confirm-database is required")

            def checkpoint(rows):
                report["results"] = rows
                write_report(args.report, report)

            _, rows = restore_objects(
                args.backup_dir,
                destination.storage,
                execute=args.restore_objects,
                progress=checkpoint,
            )
            report.update(
                results=rows,
                dry_run=not execute,
                objects_verified=all(row["status"] in SUCCESS for row in rows),
            )
            if args.restore_database or args.reconcile_database:
                if not report["objects_verified"]:
                    raise ValueError("Restore all verified objects before recovering database")
                url = os.environ.get("RESTORE_DATABASE_URL", "")
                if args.restore_database:
                    postgres_tool("pg_restore", url, args.backup_dir / DATABASE_FILE)
                    report["database_restored"] = True
                elif os.environ.get("RESTORE_ENVIRONMENT") != "recovery":
                    raise ValueError(
                        "Reconciliation requires an explicitly isolated recovery target"
                    )
                report["reconciliation"] = asyncio.run(
                    reconcile_restored_database(url, destination.storage, manifest)
                )
            # Object restoration alone is not a complete application recovery.
            report["complete"] = bool(report.get("reconciliation", {}).get("verified"))
        write_report(args.report, report)
        print(json.dumps({k: v for k, v in report.items() if k != "results"}))
        valid = SUCCESS | ({"would_copy"} if report.get("dry_run") else set())
        return 0 if all(row["status"] in valid for row in report["results"]) else 1
    except (Exception, KeyboardInterrupt) as error:
        report.update(complete=False, failure=type(error).__name__)
        write_report(args.report, report)
        print(
            f"Recovery incomplete: {type(error).__name__}; keep writers stopped and inspect the private report. No objects were deleted.",
            file=sys.stderr,
        )
        return 1


def main():
    """Installed-backend entrypoint for operator shells without repo scripts."""
    if len(sys.argv) < 2 or sys.argv[1] not in {"backup", "restore"}:
        raise SystemExit("Use: python -m app.storage.recovery_cli backup|restore [options]")
    return (backup_main if sys.argv[1] == "backup" else restore_main)(sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
