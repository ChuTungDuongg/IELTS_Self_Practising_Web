"""Post-inference Human vs AI comparison; reuses the production metric protocol."""

import csv
import io
from collections import defaultdict

from sqlalchemy import select

from app.evaluation.speaking.metrics import score_metrics
from app.models.speaking_benchmark import SpeakingBenchmarkHumanLabel as Label
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingCheckpoint as Checkpoint
from app.repositories.speaking_benchmark_grading import owned_run
from app.repositories.speaking_benchmark_reports import FIELDS, report_inputs
from app.services.speaking_benchmark import failure

VERSION = "admin-speaking-report-v1"


def bands(label):
    return {
        f: float(getattr(label, f)) if label and getattr(label, f) is not None else None
        for f in FIELDS
    }


async def selected_label(session, sample_id, revision=None):
    query = select(Label).where(Label.sample_id == sample_id)
    if revision:
        query = query.where(Label.revision == revision)
    else:
        from sqlalchemy import or_

        query = query.where(or_(*(getattr(Label, f).is_not(None) for f in FIELDS)))
    return await session.scalar(
        query.order_by(Label.verified.desc(), Label.revision.desc()).limit(1)
    )


def comparison_row(sample, run, label):
    human, ai = bands(label), (run.prediction or {}).get("bands", {}) if run else {}
    ai = {f: ai.get(f) for f in FIELDS}
    elapsed = (
        (run.finished_at - run.started_at).total_seconds() * 1000
        if run and run.finished_at and run.started_at
        else None
    )
    return {
        "sample_id": str(sample.id),
        "code": sample.code,
        "split": sample.split,
        "run_id": str(run.id) if run else None,
        "configuration": run.config_fingerprint if run else None,
        "review_revision": run.review_revision if run else None,
        "label_revision": label.revision if label else None,
        "verified": bool(label and label.verified),
        "label_status": "HUMAN_VERIFIED"
        if label and label.verified
        else "UNVERIFIED"
        if label
        else "UNLABELLED",
        "human": human,
        "ai": ai,
        "differences": {
            f: ai[f] - human[f] if ai[f] is not None and human[f] is not None else None
            for f in FIELDS
        },
        "status": run.status if run else "NO_RUN",
        "candidate_ms": run.candidate_ms if run else None,
        "latency_ms": elapsed,
        "model": run.configuration.get("scorer", {}).get("model") if run else None,
        "rubric_version": run.configuration.get("scorer", {}).get("rubric_version")
        if run
        else None,
        "prompt_version": run.configuration.get("scorer", {}).get("prompt_version")
        if run
        else None,
        "limitations": (run.prediction or {}).get("limitations", [])
        if run
        else ["PREDICTION_MISSING"],
    }


async def comparison(service, sample_id, run_id, label_revision=None):
    async with service.session.begin():
        sample = await service.owned(sample_id)
        run = await owned_run(service.session, service.owner_id, sample_id, run_id)
        label = await selected_label(service.session, sample_id, label_revision)
        if label_revision and label is None:
            raise failure("SPEAKING_BENCHMARK_LABEL_REVISION_NOT_FOUND", 404)
        return comparison_row(sample, run, label)


def summarize(rows):
    verified = [r for r in rows if r["verified"]]
    metrics = {}
    for field in FIELDS:
        eligible = [r for r in verified if r["human"].get(field) is not None]
        metrics[field] = score_metrics(
            [r["human"][field] for r in eligible], [r["ai"].get(field) for r in eligible]
        )
    return {"eligible_samples": len(verified), "displayed_samples": len(rows), "criteria": metrics}


async def report(service, filters):
    async with service.session.begin():
        samples, labels, runs, configs, selected, candidates = await report_inputs(
            service.session,
            service.owner_id,
            filters,
            service.settings.speaking_benchmark_report_max_rows,
        )
        rows = []
        for sample in samples:
            label = labels.get(sample.id)
            if label is None:
                continue
            run = runs.get(sample.id)
            config = run.configuration.get("scorer", {}) if run else {}
            if (filters.status and (not run or run.status != filters.status)) or any(
                value and config.get(key) != value
                for key, value in (
                    ("model", filters.model),
                    ("rubric_version", filters.rubric_version),
                    ("prompt_version", filters.prompt_version),
                )
            ):
                run = None  # Keep eligible denominator; missing selected prediction.
            rows.append(comparison_row(sample, run, label))
        splits = defaultdict(set)
        for candidate, split in candidates:
            splits[candidate].add(split)
        leakage = sum(len(values) > 1 for values in splits.values())
        summary = summarize(rows)
        summary.update(
            {
                "schema_version": VERSION,
                "selection_policy": "latest-finalized-per-sample-single-configuration-v1",
                "date_filter": "sample_uploaded_at",
                "configuration": selected,
                "configurations": configs,
                "requires_configuration": len(configs) > 1 and selected is None,
                "uploaded_samples": len(samples),
                "unlabelled_or_ineligible": len(samples) - len(rows),
                "split_metrics": {
                    split: summarize([r for r in rows if r["split"] == split])
                    for split in ("DEV", "HOLDOUT")
                },
                "warnings": (["DEV_HOLDOUT_SPEAKER_LEAKAGE"] if leakage else [])
                + ["HUMAN_REFERENCE_REQUIRED", "SMALL_SAMPLES_ARE_NOT_CALIBRATION"],
                "leaking_speaker_count": leakage,
            }
        )
        # Usage is observed only; never convert tokens/audio into invented dollars.
        by_run = {r["run_id"]: r for r in rows if r["run_id"]}
        attempts = (
            await service.session.scalars(
                select(Checkpoint).where(Checkpoint.run_id.in_(list(by_run)))
            )
            if by_run
            else []
        )
        for row in rows:
            row["observed_usage"], row["provider_requests"] = {}, 0
        for attempt in attempts:
            if attempt.provider == "cpu" or attempt.reused_from is not None:
                continue
            row = by_run[str(attempt.run_id)]
            row["provider_requests"] += 1
            usage = row["observed_usage"].setdefault(attempt.provider, {})
            for key, value in (attempt.usage or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    usage[key] = usage.get(key, 0) + value
        return summary, rows


EXPORT_FIELDS = (
    "sample_id",
    "code",
    "split",
    "run_id",
    "configuration",
    "review_revision",
    "label_revision",
    "verified",
    "label_status",
    "status",
    "candidate_ms",
    "latency_ms",
    "model",
    "rubric_version",
    "prompt_version",
    "provider_requests",
)


def export_rows(rows):
    return [
        {
            **{f: row.get(f) for f in EXPORT_FIELDS},
            **{
                f"{kind}_{field}": row.get(kind, {}).get(field)
                for kind in ("human", "ai", "differences")
                for field in FIELDS
            },
            "observed_usage": row.get("observed_usage", {}),
            "limitations": row.get("limitations", []),
        }
        for row in rows
    ]


def csv_export(rows):
    import json

    safe = export_rows(rows)
    fields = (
        list(safe[0])
        if safe
        else list(EXPORT_FIELDS)
        + [f"{kind}_{field}" for kind in ("human", "ai", "differences") for field in FIELDS]
        + ["observed_usage", "limitations"]
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in safe:
        values = {}
        for key, value in row.items():
            text = (
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else ""
                if value is None
                else str(value)
            )
            values[key] = (
                "'" + text
                if isinstance(value, str)
                and text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
                else text
            )
        writer.writerow(values)
    return "\ufeff" + output.getvalue()
