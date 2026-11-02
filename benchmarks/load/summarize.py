"""Generate small comparable summaries from saved sanitized HTTP reports; no network."""

import argparse
import json
from pathlib import Path


def summarize(raw):
    window = raw.get("steady_window")
    endpoints = raw.get("steady", {})
    duration = window["duration_seconds"] if window else None
    count = sum(row["requests"] for row in endpoints.values())
    success = sum(row.get("successful_requests", 0) for row in endpoints.values())
    failures = sum(row["failures"] for row in endpoints.values())
    before, after = (raw.get("resources", {}).get(key, {}) for key in ("before", "after"))
    start = before.get("elapsed_seconds", 0)
    samples = [sample for sample in after.get("samples", []) if sample["elapsed_seconds"] >= start]

    def peak(key, *, database=False):
        values = [(row.get("database", {}) if database else row).get(key) for row in samples]
        return max((value for value in values if value is not None), default=None)

    cpu = after.get("cpu_seconds", 0) - before.get("cpu_seconds", 0)
    return {
        "source_identity": raw.get("source_identity"),
        "started_at_utc": raw.get("started_at_utc", "NOT RECORDED"),
        "target_users": raw["target_users"],
        "maximum_observed_users": max(
            (row["users"] for row in raw["load_generator"]["samples"]), default=0
        ),
        "profile": raw["profile"],
        "scenario": raw["scenario"],
        "actual_duration_seconds": raw["actual_duration_seconds"],
        "steady_window": window,
        "total_requests": sum(row["requests"] for row in raw["all"].values()),
        "steady_requests": count,
        "steady_successful_2xx": success,
        "steady_rps": count / duration if duration else None,
        "steady_successful_2xx_rps": success / duration if duration else None,
        "all_unexpected_failures": sum(row["failures"] for row in raw["all"].values()),
        "steady_unexpected_failures": failures,
        "steady_unexpected_error_rate": failures / count if count else None,
        "all_http_4xx": sum(row.get("http_4xx", 0) for row in raw["all"].values()),
        "all_http_5xx": sum(row.get("http_5xx", 0) for row in raw["all"].values()),
        "journeys_completed": raw.get("journeys_completed"),
        "journeys_failed": raw.get("journeys_failed"),
        "resources": {
            "api_cpu_seconds_delta": cpu,
            "api_mean_cpu_cores_all_window": cpu / raw["actual_duration_seconds"],
            "api_sampled_rss_peak_bytes": peak("rss_bytes"),
            "db_sampled_connections_peak_excluding_observer": peak("connections", database=True),
            "db_sampled_lock_waiters_peak": peak("lock_waiters", database=True),
            "db_sampled_oldest_transaction_seconds": peak("oldest_tx_seconds", database=True),
            "pool_sampled_checked_out_peak": peak("pool_checked_out"),
            "sql_cursor_count_delta": after.get("sql_cursor_latency", {}).get("samples", 0)
            - before.get("sql_cursor_latency", {}).get("samples", 0),
            "observation_errors_delta": after.get("observation_errors", 0)
            - before.get("observation_errors", 0),
            "generator_cpu_percent_peak": max(
                (row["cpu_percent"] for row in raw["load_generator"]["samples"]), default=None
            ),
        },
        "steady_endpoints": endpoints,
        "limits": [
            "One local sample; no confidence interval",
            "No aggregate latency percentile derived by averaging endpoints",
            "Backend resource deltas include ramp/drain; latency table uses steady window",
            "Sampled resource peaks can miss short spikes",
            "Successful RPS means 2xx; accepted 409 remains expected 4xx",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
