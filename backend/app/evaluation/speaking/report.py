"""Deterministic score-only reports with explicit missing-prediction denominators."""

import csv
import io
import json
from collections import Counter
from pathlib import Path

from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.metrics import METRICS_PROTOCOL_VERSION, score_metrics
from app.schemas.speaking_grading import CRITERIA
from app.services.speaking_audio import fingerprint

TRAITS = (*CRITERIA, "overall")


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def sample_rows(samples, predictions):
    by_id = {row.id: row for row in predictions.predictions}
    unknown = by_id.keys() - {row.id for row in samples}
    if unknown:
        raise BenchmarkInputError("BENCHMARK_PREDICTION_ID_UNKNOWN")
    rows = []
    for sample in sorted(samples, key=lambda s: s.id):
        prediction = by_id.get(sample.id)
        for trait in TRAITS:
            value = (
                prediction.overall
                if prediction and trait == "overall"
                else prediction.scores.get(trait)
                if prediction
                else None
            )
            reason = None
            if value is None:
                reason = (
                    prediction.reasons.get(trait, "MISSING_PREDICTION")
                    if prediction and trait != "overall"
                    else "MISSING_PREDICTION"
                )
                if prediction and trait == "overall" and prediction.reasons:
                    reason = "CRITERION_UNAVAILABLE"
            target = getattr(sample.human, trait)
            rows.append(
                {
                    "sample_id": sample.id,
                    "criterion": trait,
                    "human": target,
                    "prediction": value,
                    "error": None if value is None else value - target,
                    "reason": reason,
                }
            )
    return rows


def _metrics(rows):
    return {
        trait: score_metrics(
            [r["human"] for r in rows if r["criterion"] == trait],
            [r["prediction"] for r in rows if r["criterion"] == trait],
        )
        for trait in TRAITS
    }


def build_report(samples, predictions, *, minimum_subgroup_samples=20):
    if type(minimum_subgroup_samples) is not int or not 5 <= minimum_subgroup_samples <= 10000:
        raise BenchmarkInputError("BENCHMARK_SUBGROUP_MINIMUM_INVALID")
    rows = sample_rows(samples, predictions)
    subgroups = {}
    for key in sorted({key for s in samples for key in s.subgroups}):
        slices = {}
        for value in sorted({s.subgroups[key] for s in samples if key in s.subgroups}):
            ids = {s.id for s in samples if s.subgroups.get(key) == value}
            if len(ids) < minimum_subgroup_samples:
                slices[value] = {
                    "status": "insufficient_samples",
                    "sample_count": len(ids),
                    "minimum_samples": minimum_subgroup_samples,
                }
            else:
                slices[value] = {
                    "status": "ok",
                    "sample_count": len(ids),
                    "criteria": _metrics([r for r in rows if r["sample_id"] in ids]),
                }
        subgroups[key] = slices
    disagreements = sorted(
        (r for r in rows if r["error"] is not None),
        key=lambda r: (-abs(r["error"]), r["sample_id"], r["criterion"]),
    )[:20]
    failures = {
        trait: dict(
            sorted(
                Counter(
                    r["reason"] for r in rows if r["criterion"] == trait and r["prediction"] is None
                ).items()
            )
        )
        for trait in TRAITS
    }
    return {
        "schema_version": 1,
        "advisory": True,
        "metric_protocol_version": METRICS_PROTOCOL_VERSION,
        "sample_count": len(samples),
        "cohort_hash": fingerprint(
            [
                {"id": s.id, "human": s.human.model_dump(), "subgroups": s.subgroups}
                for s in sorted(samples, key=lambda s: s.id)
            ]
        ),
        "provenance": predictions.provenance.model_dump(mode="json"),
        "criteria": _metrics(rows),
        "subgroups": subgroups,
        "nonscorable_reasons": failures,
        "largest_disagreements": disagreements,
        "limitations": [
            "Agreement metrics use valid predictions; failure/coverage rates include every labelled sample.",
            "Human labels and representativeness require independent review; no examiner equivalence is established.",
            "No calibration or production score changes are applied.",
        ],
    }


def write_reports(output: Path, samples, predictions, report):
    def dump(value):
        return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"

    atomic_write(output / "summary.json", dump(report))
    rows = sample_rows(samples, predictions)
    atomic_write(
        output / "samples.jsonl",
        "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows),
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=["sample_id", "criterion", "human", "prediction", "error", "reason"],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(output / "samples.csv", buffer.getvalue())
    text = [
        "Speaking advisory benchmark",
        "",
        f"Labelled samples: {len(samples)}. Failures are included in coverage.",
        "",
        "| Criterion | Valid / total | Failure rate | MAE | RMSE | Pearson | Spearman | QWK | ±0.5 | ±1.0 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for trait, values in report["criteria"].items():
        cells = [trait.upper(), f"{values['count']} / {values['total_count']}"] + [
            str(values.get(key)) if values.get(key) is not None else "unavailable"
            for key in (
                "failure_rate",
                "mae",
                "rmse",
                "pearson",
                "spearman",
                "quadratic_weighted_kappa",
                "within_0_5",
                "within_1_0",
            )
        ]
        text.append("| " + " | ".join(cells) + " |")
    text += [
        "",
        "Undefined statistics and subgroup suppression are explained in summary.json.",
        "",
        *report["limitations"],
        "",
        "Provenance:",
        "```json",
        dump(report["provenance"]).rstrip(),
        "```",
    ]
    atomic_write(output / "summary.md", "\n".join(text) + "\n")
