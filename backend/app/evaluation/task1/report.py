"""Reports contain IDs, predictions and aggregates, never essays or image data."""

import csv
import io
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from app.evaluation.task1.metrics import score_metrics
from app.evaluation.task1.models import BENCHMARK_CONTRACT_VERSION
from app.schemas.writing_ai import TRAITS


def _score_metrics(records):
    metrics = {}
    for trait in (*TRAITS, "overall"):
        pairs = []
        for record in records:
            target = record.target_overall if trait == "overall" else record.target[trait]
            predicted = (
                record.predicted_overall if trait == "overall" else record.predicted.get(trait)
            )
            if predicted is not None:
                pairs.append((target, predicted))
        metrics[trait] = score_metrics(pairs)
    return metrics


def _perception(records):
    result = {}
    for stage in ("primary", "reconciled"):
        observations = [
            record.perception[stage] for record in records if record.perception[stage] is not None
        ]
        numeric = sum(item["labelled_numeric_count"] for item in observations)
        exact = sum(item["exact_labelled_numeric_count"] for item in observations)
        truth_values = sum(item["truth_values"] for item in observations)
        aligned = sum(item["aligned_values"] for item in observations)
        result[stage] = {
            "count": len(observations),
            "unannotated_count": len(records) - len(observations),
            "perception_ok_count": sum(item["perception_ok"] is True for item in observations),
            "perception_error_count": sum(item["perception_ok"] is False for item in observations),
            "perception_unknown_count": sum(item["perception_ok"] is None for item in observations),
            "labelled_numeric_count": numeric,
            "exact_labelled_numeric_count": exact,
            "exact_labelled_numeric_agreement": exact / numeric if numeric else None,
            "truth_values": truth_values,
            "aligned_values": aligned,
            "value_alignment": aligned / truth_values if truth_values else None,
            **{
                key: sum(item[key] for item in observations)
                for key in (
                    "missing_values",
                    "extra_values",
                    "unavailable_values",
                    "ambiguous_components",
                    "ambiguous_values",
                )
            },
        }
    result["reconciliation_disagreements"] = sum(
        record.specialist_disagreements for record in records
    )
    return result


def aggregate(records):
    count = len(records)
    return {
        "count": count,
        "failure_count": sum(record.status == "FAILED" for record in records),
        "failure_rate": sum(record.status == "FAILED" for record in records) / count
        if count
        else None,
        "metrics": _score_metrics(records),
        "perception": _perception(records),
        "decomposition": dict(Counter(record.decomposition for record in records)),
        "mean_wall_clock_seconds": sum(record.wall_clock_seconds for record in records) / count
        if count
        else None,
        "provider_calls": sum(record.provider_calls for record in records),
        "new_provider_calls": sum(
            record.provider_calls for record in records if not record.cache_hit
        ),
        "specialist_calls": sum(record.specialist_calls for record in records),
        "new_specialist_calls": sum(
            record.specialist_calls for record in records if not record.cache_hit
        ),
        "specialist_latency_seconds": sum(record.specialist_latency_seconds for record in records),
        "specialist_fallback_count": sum(
            record.specialist_status in {"UNAVAILABLE", "PARSE_FAILED", "RECONCILIATION_FAILED"}
            for record in records
        ),
        "cache_hit_count": sum(record.cache_hit for record in records),
    }


def _bucket(score):
    lower = int(score)
    return f"{lower}.0-{lower}.5" if lower < 9 else "9.0"


def _stratified(records):
    result = {}
    for dimension in ("task_type", "visual_family", "split"):
        groups = defaultdict(list)
        for record in records:
            groups[str(getattr(record, dimension))].append(record)
        result[dimension] = {name: aggregate(group) for name, group in sorted(groups.items())}
    # Buckets use each criterion's target, not overall as a proxy for grammar etc.
    result["target_band"] = {}
    for trait in (*TRAITS, "overall"):
        groups = defaultdict(list)
        for record in records:
            target = record.target_overall if trait == "overall" else record.target[trait]
            groups[_bucket(target)].append(record)
        result["target_band"][trait] = {
            bucket: {"count": len(group), "metrics": _score_metrics(group)[trait]}
            for bucket, group in sorted(groups.items())
        }
    return result


def _comparison_kind(left, right):
    a, b = (
        left.model_dump(mode="json", exclude={"label"}),
        right.model_dump(mode="json", exclude={"label"}),
    )
    if (
        left.scoring_version == right.scoring_version
        and left.specialist.enabled != right.specialist.enabled
    ):
        a["specialist"]["enabled"] = b["specialist"]["enabled"] = False
        return "chart_specialist" if a == b else None
    if left.scoring_version != right.scoring_version and left.specialist == right.specialist:
        for key in ("scoring_version", "prompt_version", "scoring_prompt_version"):
            a.pop(key)
            b.pop(key)
        return "scoring_prompt" if a == b else None
    return None


def _delta(before, after):
    return after - before if before is not None and after is not None else None


def _ablations(records, configs):
    result = []
    for left, right in combinations(configs, 2):
        kind = _comparison_kind(left, right)
        if kind is None:
            continue
        if (kind == "chart_specialist" and left.specialist.enabled) or (
            kind == "scoring_prompt" and left.scoring_version == "v4"
        ):
            left, right = right, left
        baseline = {
            (r.sample_id, r.split, r.input_hash, r.image_hash): r
            for r in records
            if r.config_key == left.key
        }
        candidate = {
            (r.sample_id, r.split, r.input_hash, r.image_hash): r
            for r in records
            if r.config_key == right.key
        }
        identities = sorted(baseline.keys() & candidate.keys())
        if kind == "chart_specialist":
            identities = [key for key in identities if baseline[key].visual_family == "chart_table"]
        a, b = (
            aggregate([baseline[key] for key in identities]),
            aggregate([candidate[key] for key in identities]),
        )
        paired_metrics, paired_counts = {}, {}
        for trait in (*TRAITS, "overall"):
            paired = [
                key
                for key in identities
                if (
                    baseline[key].predicted_overall is not None
                    and candidate[key].predicted_overall is not None
                    if trait == "overall"
                    else trait in baseline[key].predicted and trait in candidate[key].predicted
                )
            ]
            paired_counts[trait] = len(paired)
            paired_metrics[trait] = {
                "baseline": _score_metrics([baseline[key] for key in paired])[trait],
                "candidate": _score_metrics([candidate[key] for key in paired])[trait],
            }
        result.append(
            {
                "kind": kind,
                "baseline": left.key,
                "candidate": right.key,
                "paired_sample_count": len(identities),
                "completed_pair_count": sum(
                    baseline[key].status == candidate[key].status == "COMPLETED"
                    for key in identities
                ),
                "baseline_metrics": a,
                "candidate_metrics": b,
                "paired_criterion_counts": paired_counts,
                "paired_score_metrics": paired_metrics,
                "criterion_deltas": {
                    trait: {
                        metric: _delta(
                            paired_metrics[trait]["baseline"][metric],
                            paired_metrics[trait]["candidate"][metric],
                        )
                        for metric in (
                            "exact_agreement",
                            "within_0_5",
                            "within_1_0",
                            "signed_bias",
                            "mae",
                            "rmse",
                            "quadratic_weighted_kappa",
                        )
                    }
                    for trait in (*TRAITS, "overall")
                },
                "failure_rate_delta": _delta(a["failure_rate"], b["failure_rate"]),
                "latency_delta_seconds": _delta(
                    a["mean_wall_clock_seconds"], b["mean_wall_clock_seconds"]
                ),
                "reconciled_numeric_agreement_delta": _delta(
                    a["perception"]["reconciled"]["exact_labelled_numeric_agreement"],
                    b["perception"]["reconciled"]["exact_labelled_numeric_agreement"],
                ),
            }
        )
    return result


def _operational(attempts):
    count = len(attempts)
    first = {}
    for attempt in attempts:
        first.setdefault(attempt.cache_key, attempt)
    return {
        "attempt_count": count,
        "failed_attempt_count": sum(attempt.status == "FAILED" for attempt in attempts),
        "attempt_failure_rate": sum(attempt.status == "FAILED" for attempt in attempts) / count
        if count
        else None,
        "initial_failure_rate": sum(attempt.status == "FAILED" for attempt in first.values())
        / len(first)
        if first
        else None,
        "provider_calls": sum(attempt.provider_calls for attempt in attempts),
        "specialist_calls": sum(attempt.specialist_calls for attempt in attempts),
        "wall_clock_seconds": sum(attempt.wall_clock_seconds for attempt in attempts),
        "specialist_latency_seconds": sum(
            attempt.specialist_latency_seconds for attempt in attempts
        ),
        "token_usage": dict(sum((Counter(attempt.token_usage) for attempt in attempts), Counter())),
    }


def build_report(records, configs, *, status="COMPLETED", attempts=None):
    attempts = records if attempts is None else attempts
    configurations = {}
    for config in configs:
        selected = [record for record in records if record.config_key == config.key]
        configurations[config.key] = {
            "configuration": config.model_dump(mode="json"),
            **aggregate(selected),
            "stratified": _stratified(selected),
            "operational": _operational(
                [attempt for attempt in attempts if attempt.config_key == config.key]
            ),
        }
    disagreements = []
    for record in records:
        for trait in (*TRAITS, "overall"):
            target = record.target_overall if trait == "overall" else record.target[trait]
            predicted = (
                record.predicted_overall if trait == "overall" else record.predicted.get(trait)
            )
            if predicted is not None:
                disagreements.append(
                    {
                        "sample_id": record.sample_id,
                        "config_key": record.config_key,
                        "criterion": trait,
                        "target": float(target),
                        "predicted": float(predicted),
                        "delta": float(predicted - target),
                    }
                )
    disagreements.sort(
        key=lambda item: (
            -abs(item["delta"]),
            item["sample_id"],
            item["criterion"],
            item["config_key"],
        )
    )
    return {
        "schema_version": BENCHMARK_CONTRACT_VERSION,
        "status": status,
        "sample_count": len({record.sample_id for record in records}),
        "evaluated_run_count": len(records),
        "configurations": configurations,
        "records": [record.model_dump(mode="json") for record in records],
        "attempt_history": [attempt.model_dump(mode="json") for attempt in attempts],
        "operational": _operational(attempts),
        "ablations": _ablations(records, configs),
        "largest_disagreements": disagreements[:20],
        "interpretation": {
            "bias_sign": "prediction minus human/reference; positive means higher predictions",
            "qwk_minimum_samples": 10,
            "score_ok_tolerance": 0.5,
            "perception": "Exact annotated chart/table values and semantic labels; other families are unannotated, never assumed correct.",
            "cache_latency": "Cache hits retain the original observed latency/usage. New call counters exclude hits.",
            "holdout": "Do not use holdout outcomes for repeated prompt tuning.",
        },
    }


def _number(value, *, signed=False):
    return "n/a" if value is None else format(value, "+.3f" if signed else ".3f")


def markdown_report(report):
    lines = [
        "# Task 1 benchmark",
        "",
        f"Status: {report['status']}. Samples: {report['sample_count']}. Evaluated runs: {report['evaluated_run_count']}.",
        "",
        "Rates are fractions. Bias is prediction minus human/reference. QWK is omitted below 10 samples or when undefined. No essay or image is included.",
        "",
    ]
    if report["status"] == "DRY_RUN":
        lines.extend(
            [
                f"Dry run: {report['planned_scoring_runs']} planned scoring runs, zero provider calls.",
                "",
            ]
        )
    for aggregate in report["configurations"].values():
        cfg = aggregate["configuration"]
        lines.extend(
            [
                f"## {cfg['label']}",
                "",
                f"Provider/model: {cfg['provider']} / {cfg['model']}. Perception: {cfg['visual_contract_version']}. Scoring: {cfg['scoring_prompt_version']}. Cache/production version: {cfg['prompt_version']}.",
                "",
                "| Criterion | N | Exact | ±0.5 | ±1.0 | MAE | Bias | RMSE | QWK |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for trait, metric in aggregate["metrics"].items():
            values = [
                _number(metric[name], signed=name == "signed_bias")
                for name in (
                    "exact_agreement",
                    "within_0_5",
                    "within_1_0",
                    "mae",
                    "signed_bias",
                    "rmse",
                    "quadratic_weighted_kappa",
                )
            ]
            lines.append(f"| {trait.upper()} | {metric['count']} | " + " | ".join(values) + " |")
        lines.extend(
            [
                "",
                f"Failures: {aggregate['failure_count']}/{aggregate['count']}. Mean wall time: {_number(aggregate['mean_wall_clock_seconds'])}s. Recorded/new provider calls: {aggregate['provider_calls']}/{aggregate['new_provider_calls']}. Specialist calls: {aggregate['specialist_calls']}; fallbacks: {aggregate['specialist_fallback_count']}; specialist time: {_number(aggregate['specialist_latency_seconds'])}s.",
                "",
                "### Perception",
                "",
                "| Stage | Annotated N | Labelled values | Exact numeric agreement | Value alignment | Missing | Extra | Unknown |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for stage in ("primary", "reconciled"):
            p = aggregate["perception"][stage]
            lines.append(
                f"| {stage} | {p['count']} | {p['labelled_numeric_count']} | {_number(p['exact_labelled_numeric_agreement'])} | {_number(p['value_alignment'])} | {p['missing_values']} | {p['extra_values']} | {p['unavailable_values']} |"
            )
        operational = aggregate["operational"]
        lines.extend(
            [
                "",
                f"Recorded attempts: {operational['attempt_count']}; failed attempts: {operational['failed_attempt_count']}. "
                f"Initial/attempt failure rates: {_number(operational['initial_failure_rate'])}/{_number(operational['attempt_failure_rate'])}. "
                f"Cumulative recorded provider/specialist calls: {operational['provider_calls']}/{operational['specialist_calls']}. "
                "Score metrics use terminal outcomes; retries do not erase operational history.",
            ]
        )
        lines.extend(
            [
                "",
                f"Reconciliation disagreements: {aggregate['perception']['reconciliation_disagreements']}. Error decomposition: `{aggregate['decomposition']}`.",
                "",
                "### By task type / visual family",
                "",
                "| Group | N | Criterion | MAE | Signed bias |",
                "|---|---:|---|---:|---:|",
            ]
        )
        for dimension in ("task_type", "visual_family"):
            for group, summary in aggregate["stratified"][dimension].items():
                for trait, metric in summary["metrics"].items():
                    lines.append(
                        f"| {dimension}: {group} | {metric['count']} | {trait.upper()} | {_number(metric['mae'])} | {_number(metric['signed_bias'], signed=True)} |"
                    )
        lines.extend(
            [
                "",
                "### By target band",
                "",
                "| Criterion | Target bucket | N | MAE | Signed bias |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for trait, buckets in aggregate["stratified"]["target_band"].items():
            for bucket, summary in buckets.items():
                metric = summary["metrics"]
                lines.append(
                    f"| {trait.upper()} | {bucket} | {metric['count']} | {_number(metric['mae'])} | {_number(metric['signed_bias'], signed=True)} |"
                )
        lines.append("")
    lines.extend(
        [
            "## Paired ablations",
            "",
            "Candidate minus baseline; only identical sample content/images and controlled configuration changes are paired.",
            "",
            "| Ablation | Baseline → Candidate | Paired N | Completed pairs | ΔTA MAE | ΔGRA bias | ΔFailure rate | ΔLatency (s) | ΔNumeric agreement |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for comparison in report["ablations"]:
        left = report["configurations"][comparison["baseline"]]["configuration"]["label"]
        right = report["configurations"][comparison["candidate"]]["configuration"]["label"]
        lines.append(
            f"| {comparison['kind']} | {left} → {right} | {comparison['paired_sample_count']} | {comparison['completed_pair_count']} | {_number(comparison['criterion_deltas']['ta']['mae'], signed=True)} | {_number(comparison['criterion_deltas']['gra']['signed_bias'], signed=True)} | {_number(comparison['failure_rate_delta'], signed=True)} | {_number(comparison['latency_delta_seconds'], signed=True)} | {_number(comparison['reconciled_numeric_agreement_delta'], signed=True)} |"
        )
    lines.extend(
        [
            "",
            "## Largest disagreements",
            "",
            "| Sample ID | Configuration | Criterion | Target | Predicted | Delta |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for item in report["largest_disagreements"]:
        label = report["configurations"][item["config_key"]]["configuration"]["label"]
        lines.append(
            f"| {item['sample_id']} | {label} | {item['criterion'].upper()} | {item['target']:.1f} | {item['predicted']:.1f} | {item['delta']:+.1f} |"
        )
    lines.extend(
        [
            "",
            "Perception errors suggest perception/reconciliation work; TA disagreement with accurate perception suggests TA guidance. Persistent CC/LR/GRA bias suggests scorer calibration. Evaluate a stronger scorer/adjudicator only if labelled evidence justifies it. Holdout is for final evaluation, not repeated tuning. Benchmark statistics never adjust production scores.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(output: Path, report):
    import json

    from app.evaluation.task1.runner import atomic_write

    atomic_write(output / "report.json", json.dumps(report, ensure_ascii=False, indent=2))
    atomic_write(output / "report.md", markdown_report(report))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=["sample_id", "config_key", "criterion", "target", "predicted", "delta"]
    )
    writer.writeheader()
    writer.writerows(report["largest_disagreements"])
    atomic_write(output / "disagreements.csv", stream.getvalue())
