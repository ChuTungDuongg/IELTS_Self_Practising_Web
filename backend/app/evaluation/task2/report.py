"""Score metrics and operational failures without reproducing source material."""

import csv
import io
import json
from collections import Counter, defaultdict

from app.evaluation.task2.models import BENCHMARK_CONTRACT_VERSION, TRAITS
from app.evaluation.writing.checkpoints import atomic_write
from app.evaluation.writing.metrics import score_metrics


def _metrics(records):
    result = {}
    for trait in (*TRAITS, "overall"):
        pairs = []
        for row in records:
            target = row.target_overall if trait == "overall" else row.target[trait]
            predicted = row.predicted_overall if trait == "overall" else row.predicted.get(trait)
            if predicted is not None:
                pairs.append((target, predicted))
        result[trait] = score_metrics(pairs)
    return result


def aggregate(records):
    count = len(records)
    failures = sum(row.status == "FAILED" for row in records)
    return dict(
        count=count,
        failure_count=failures,
        failure_rate=failures / count if count else None,
        metrics=_metrics(records),
        mean_wall_clock_seconds=sum(row.wall_clock_seconds for row in records) / count
        if count
        else None,
        provider_calls=sum(row.provider_calls for row in records),
        new_provider_calls=sum(row.provider_calls for row in records if not row.cache_hit),
        cache_hit_count=sum(row.cache_hit for row in records),
        token_usage=dict(sum((Counter(row.token_usage) for row in records), Counter())),
    )


def _operational(attempts):
    first = {}
    for row in attempts:
        first.setdefault(row.cache_key, row)
    failures = sum(row.status == "FAILED" for row in attempts)
    return dict(
        attempt_count=len(attempts),
        failed_attempt_count=failures,
        attempt_failure_rate=failures / len(attempts) if attempts else None,
        initial_failure_rate=sum(row.status == "FAILED" for row in first.values()) / len(first)
        if first
        else None,
        provider_calls=sum(row.provider_calls for row in attempts),
        wall_clock_seconds=sum(row.wall_clock_seconds for row in attempts),
        token_usage=dict(sum((Counter(row.token_usage) for row in attempts), Counter())),
    )


def build_report(records, config, *, status="COMPLETED", attempts=None):
    attempts = records if attempts is None else attempts
    splits = defaultdict(list)
    for row in records:
        splits[row.split].append(row)
    strata = {
        "split": {split: aggregate(rows) for split, rows in sorted(splits.items())},
        "target_band": {},
    }
    for trait in (*TRAITS, "overall"):
        groups = defaultdict(list)
        for row in records:
            target = row.target_overall if trait == "overall" else row.target[trait]
            lower = int(target)
            groups[f"{lower}.0-{lower}.5" if lower < 9 else "9.0"].append(row)
        strata["target_band"][trait] = {
            key: {"count": len(rows), "metrics": _metrics(rows)[trait]}
            for key, rows in sorted(groups.items())
        }
    disagreements = []
    for row in records:
        for trait in (*TRAITS, "overall"):
            target = row.target_overall if trait == "overall" else row.target[trait]
            predicted = row.predicted_overall if trait == "overall" else row.predicted.get(trait)
            if predicted is not None:
                disagreements.append(
                    dict(
                        sample_id=row.sample_id,
                        config_key=row.config_key,
                        criterion=trait,
                        target=float(target),
                        predicted=float(predicted),
                        delta=float(predicted - target),
                    )
                )
    disagreements.sort(key=lambda row: (-abs(row["delta"]), row["sample_id"], row["criterion"]))
    return dict(
        schema_version=BENCHMARK_CONTRACT_VERSION,
        status=status,
        sample_count=len(records),
        configuration=config.model_dump(mode="json"),
        aggregate=aggregate(records),
        stratified=strata,
        operational=_operational(attempts),
        records=[row.model_dump(mode="json") for row in records],
        attempt_history=[row.model_dump(mode="json") for row in attempts],
        failures=[
            {"sample_id": row.sample_id, "failures": row.failures}
            for row in records
            if row.status == "FAILED"
        ],
        largest_disagreements=disagreements,
        interpretation={
            "bias_sign": "prediction minus human/reference",
            "qwk_minimum_samples": 10,
            "cache_latency": "Cached observations retain original latency/usage; new-call counters exclude hits.",
            "holdout": "Reserve holdout for final evaluation.",
        },
    )


def markdown_report(report):
    summary = report["aggregate"]
    lines = [
        "# Task 2 Writing benchmark",
        "",
        f"Status: {report['status']}. Samples: {report['sample_count']}.",
        f"Failures: {summary['failure_count']}. Failure rate: {summary['failure_rate']}.",
        f"New provider calls: {summary['new_provider_calls']}. Mean latency: {summary['mean_wall_clock_seconds']} seconds.",
        "",
        "Rates are fractions. Bias is prediction minus human. QWK is unavailable below 10 samples or when undefined.",
        "",
        "| Criterion | N | Exact | ±0.5 | ±1.0 | Bias | MAE | RMSE | QWK |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for trait, metrics in summary["metrics"].items():
        values = [
            "n/a" if metrics[key] is None else f"{metrics[key]:.3f}"
            for key in (
                "exact_agreement",
                "within_0_5",
                "within_1_0",
                "signed_bias",
                "mae",
                "rmse",
                "quadratic_weighted_kappa",
            )
        ]
        lines.append(f"| {trait.upper()} | {metrics['count']} | " + " | ".join(values) + " |")
    lines.extend(
        [
            "",
            "## Failed samples",
            "",
            *[
                f"- {row['sample_id']}: {', '.join(sorted(row['failures']))}"
                for row in report["failures"]
            ],
            "",
            f"Recorded attempts: {report['operational']['attempt_count']}. Failed attempts: {report['operational']['failed_attempt_count']}.",
            "Human labels never enter scoring prompts. Benchmark results never adjust production scores.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(output, report):
    atomic_write(output / "report.json", json.dumps(report, ensure_ascii=False, indent=2))
    atomic_write(output / "report.md", markdown_report(report))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=["sample_id", "config_key", "criterion", "target", "predicted", "delta"]
    )
    writer.writeheader()
    writer.writerows(report["largest_disagreements"])
    atomic_write(output / "disagreements.csv", stream.getvalue())
