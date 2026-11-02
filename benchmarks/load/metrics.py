"""Bounded histograms retain per-second status/latency distributions, not private inputs."""

import math
from collections import Counter, defaultdict


class Metrics:
    def __init__(self):
        self.buckets = defaultdict(Counter)

    def record(self, name, status, milliseconds, elapsed, failure=None):
        # Millisecond histogram avoids retaining one Python object per request in a soak.
        self.buckets[(int(elapsed), name)][(str(status), max(0, round(milliseconds)), failure)] += 1

    def _aggregate(self, start, end):
        grouped = defaultdict(Counter)
        for (second, name), values in self.buckets.items():
            if start <= second < end:
                grouped[name].update(values)
        result = {}
        for name, values in grouped.items():
            statuses, latencies, failures = Counter(), Counter(), Counter()
            for (status, latency, failure), count in values.items():
                statuses[status] += count
                latencies[latency] += count
                if failure:
                    failures[failure] += count
            count = sum(statuses.values())
            successful = sum(
                amount
                for (status, _latency, failure), amount in values.items()
                if status.startswith("2") and failure is None
            )

            def percentile(fraction, count=count, latencies=latencies):
                target, total = math.ceil(count * fraction), 0
                for latency, amount in sorted(latencies.items()):
                    total += amount
                    if total >= target:
                        return latency
                return None

            result[name] = {
                "requests": count,
                "successful_requests": successful,
                "successful_rps": round(successful / (end - start), 3) if end > start else None,
                "http_4xx": sum(
                    amount for status, amount in statuses.items() if status.startswith("4")
                ),
                "http_5xx": sum(
                    amount for status, amount in statuses.items() if status.startswith("5")
                ),
                "p99_sample_warning": count < 1000,
                "failures": sum(failures.values()),
                "statuses": dict(statuses),
                "failure_codes": dict(failures),
                "p50_ms": percentile(0.50),
                "p95_ms": percentile(0.95),
                "p99_ms": percentile(0.99),
                "max_ms": max(latencies),
                "rps": round(count / (end - start), 3) if end > start else None,
            }
        return result

    def report(self, *, steady_start, steady_end, actual_end):
        end = min(steady_end, actual_end)
        window = (
            None
            if end <= steady_start
            else {
                "start_seconds": steady_start,
                "end_seconds": end,
                "duration_seconds": end - steady_start,
            }
        )
        return {
            "actual_duration_seconds": actual_end,
            "all": self._aggregate(0, actual_end),
            "steady_window": window,
            "steady": self._aggregate(steady_start, end) if window else {},
        }
