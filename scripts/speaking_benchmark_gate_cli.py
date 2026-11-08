#!/usr/bin/env python3
"""Offline saved-JSON release gate CLI for CI inspection; never calls providers."""

import argparse
import json
import sys
from pathlib import Path


def format_table(report: dict) -> str:
    lines = []
    lines.append(f"Protocol: {report.get('protocol', 'unknown')}")
    lines.append(f"Status:   {report.get('status', 'unknown')}")
    lines.append(
        f"Samples:  {report.get('matched_samples', 0)} / {report.get('selected_samples', 0)}"
    )
    lines.append(f"Independent Candidates: {report.get('matched_independent_candidates', 0)}")
    if report.get("reasons"):
        lines.append(f"Reasons:  {', '.join(report.get('reasons', []))}")
    lines.append("")
    lines.append(
        f"{'Metric':<25} {'Direction':<14} {'Status':<12} {'Baseline':<10} {'Candidate':<10} {'Diff':<10} {'Max Regr':<10}"
    )
    lines.append("-" * 95)
    for m in report.get("metrics", []):
        name = m.get("metric", "")
        direction = m.get("direction", "")
        status = m.get("status", "")
        b = f"{m.get('baseline', 0):.4f}" if m.get("baseline") is not None else "N/A"
        c = f"{m.get('candidate', 0):.4f}" if m.get("candidate") is not None else "N/A"
        diff = f"{m.get('difference', 0):+.4f}" if m.get("difference") is not None else "N/A"
        tol = (
            f"{m.get('tolerable_regression', 0):.4f}"
            if m.get("tolerable_regression") is not None
            else "N/A"
        )
        lines.append(
            f"{name:<25} {direction:<14} {status:<12} {b:<10} {c:<10} {diff:<10} {tol:<10}"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Inspect a persisted Speaking Benchmark regression report JSON."
    )
    parser.add_argument(
        "report_file",
        type=Path,
        help="Path to the saved regression report JSON file.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    args = parser.parse_args()

    if not args.report_file.exists():
        sys.stderr.write(f"Error: file not found: {args.report_file}\n")
        sys.exit(2)

    try:
        data = json.loads(args.report_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        sys.stderr.write(f"Error parsing JSON: {e}\n")
        sys.exit(2)

    # Allow either raw report dict or RegressionReportDTO with 'report' field
    report = (
        data.get("report")
        if isinstance(data, dict) and "report" in data and isinstance(data["report"], dict)
        else data
    )
    if (
        not isinstance(report, dict)
        or report.get("protocol") != "speaking-regression-gate-v1"
        or not isinstance(report.get("metrics"), list)
        or not all(isinstance(m, dict) for m in report.get("metrics", []))
    ):
        sys.stderr.write("Invalid report protocol or structure\n")
        sys.exit(2)
    status = report.get("status", "INVALID")
    if status == "PASS" and (
        not report["metrics"]
        or report.get("reasons")
        or any(m.get("status") != "PASS" for m in report["metrics"])
    ):
        sys.stderr.write("Inconsistent PASS report\n")
        sys.exit(2)

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_table(report))

    if status == "PASS":
        sys.exit(0)
    elif status == "FAIL":
        sys.exit(1)
    else:  # INCONCLUSIVE or INVALID
        sys.exit(2)


if __name__ == "__main__":
    main()
