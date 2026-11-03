"""Deterministic score-only reports with explicit missing-prediction denominators."""

import csv
import io
import json
from collections import Counter
from math import ceil
from pathlib import Path

from app.evaluation.speaking.manifest import BenchmarkInputError, validate_speaker_splits
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


def _telemetry(predictions):
    rows = [row.telemetry for row in predictions.predictions if row.telemetry is not None]
    latencies = sorted(row.latency_ms for row in rows if row.latency_ms is not None)
    calls = sum(row.provider_calls for row in rows)
    errors = sum(row.provider_errors for row in rows)
    return {
        "sample_count": len(rows),
        "latency_p50_ms": latencies[ceil(len(latencies) * 0.5) - 1] if latencies else None,
        "latency_p95_ms": latencies[ceil(len(latencies) * 0.95) - 1] if latencies else None,
        "logical_calls": calls if rows else None,
        "transport_attempts": sum(row.provider_attempts for row in rows) if rows else None,
        "failed_logical_calls": errors if rows else None,
        "error_rate": errors / calls if calls else None,
        "usage": {
            key: sum(row.usage.get(key, 0) for row in rows)
            for key in sorted({key for row in rows for key in row.usage})
        },
    }


def _speech_telemetry(predictions):
    rows = [
        row.telemetry.speech
        for row in predictions.predictions
        if row.telemetry and row.telemetry.speech
    ]
    calls = sum(row.attempted_calls for row in rows)
    failures = sum(row.failed_calls for row in rows)
    return {
        "sample_count": len(rows),
        "attempted_calls": calls if rows else None,
        "failed_calls": failures if rows else None,
        "error_rate": failures / calls if calls else None,
        "submitted_audio_ms": sum(row.submitted_audio_ms for row in rows) if rows else None,
        "billing_uncertain": True,
    }


def build_report(samples, predictions, *, minimum_subgroup_samples=20):
    validate_speaker_splits(samples)
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
    splits = {}
    for split in ("DEV", "HOLDOUT"):
        ids = {s.id for s in samples if s.split == split}
        criteria = _metrics([r for r in rows if r["sample_id"] in ids])
        eligible = all(criteria[t]["count"] > 0 for t in ("fc", "pr"))
        gate = (
            all(
                criteria[t]["mae"] <= 0.5 and abs(criteria[t]["signed_bias"]) <= 0.5
                for t in ("fc", "pr")
            )
            if eligible
            else None
        )
        splits[split] = {
            "sample_count": len(ids),
            "speaker_count": len({s.speaker_id for s in samples if s.id in ids}),
            "criteria": criteria,
            "fc_pr_half_band_gate": "pass" if gate else "fail" if gate is False else "unavailable",
        }
    return {
        "schema_version": 1,
        "advisory": True,
        "metric_protocol_version": METRICS_PROTOCOL_VERSION,
        "sample_count": len(samples),
        "cohort_hash": fingerprint(
            [
                {
                    "id": s.id,
                    "human": s.human.model_dump(),
                    "subgroups": s.subgroups,
                    "speaker_id": s.speaker_id,
                    "split": s.split,
                }
                for s in sorted(samples, key=lambda s: s.id)
            ]
        ),
        "provenance": predictions.provenance.model_dump(mode="json"),
        "criteria": _metrics(rows),
        "llm_telemetry": _telemetry(predictions),
        "speech_telemetry": _speech_telemetry(predictions),
        "splits": splits,
        "speaker_split_status": "validated" if all(s.split for s in samples) else "unverified",
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
        "| Criterion | Valid / total | Failure rate | MAE | Signed bias | RMSE | Pearson | Spearman | QWK | ±0.5 | ±1.0 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for trait, values in report["criteria"].items():
        cells = [trait.upper(), f"{values['count']} / {values['total_count']}"] + [
            str(values.get(key)) if values.get(key) is not None else "unavailable"
            for key in (
                "failure_rate",
                "mae",
                "signed_bias",
                "rmse",
                "pearson",
                "spearman",
                "quadratic_weighted_kappa",
                "within_0_5",
                "within_1_0",
            )
        ]
        text.append("| " + " | ".join(cells) + " |")
    text += ["", f"Speaker splits: {report['speaker_split_status']}."]
    for split, values in report["splits"].items():
        text.append(
            f"{split}: {values['sample_count']} samples; descriptive FC/PR half-band gate: {values['fc_pr_half_band_gate']}."
        )
    if "speech_analysis" in report:
        analysis = report["speech_analysis"]
        text += [
            "",
            f"Lexical WER: {analysis['lexical_fidelity']['wer']}; token boundary MAE (ms): {analysis['timing']['boundary_mae_ms']}; feedback false-positive rate: {analysis['feedback']['false_positive_rate']}.",
        ]
    text += [
        "",
        "Recorded call/usage telemetry, missing values unknown:",
        "```json",
        dump({key: report[key] for key in ("llm_telemetry", "speech_telemetry")}).rstrip(),
        "```",
    ]
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
