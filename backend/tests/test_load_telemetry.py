"""Aggregate benchmark instrumentation must not record SQL or learner content."""

from benchmarks.load.telemetry import Distribution


def test_bounded_distribution_and_nearest_rank():
    metric = Distribution()
    for value in (1, 2, 3, 4, 1000000):
        metric.add(value)
    assert metric.summary() == {
        "samples": 5,
        "p50_ms": 3,
        "p95_ms": 60000,
        "p99_ms": 60000,
        "max_ms": 60000,
    }
    assert not any(isinstance(key, str) for key in metric.values)


def test_no_samples_are_not_zero_latency():
    assert Distribution().summary()["p95_ms"] is None
