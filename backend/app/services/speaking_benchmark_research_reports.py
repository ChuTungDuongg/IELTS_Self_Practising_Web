"""Read-only research projections. Human data is joined only here, after inference."""

import csv
import io
import json
from collections import defaultdict
from itertools import combinations
from uuid import UUID

from sqlalchemy import select

from app.evaluation.speaking.hybrid import _edit_distance, _tokens
from app.evaluation.speaking.metrics import score_metrics
from app.models.speaking_benchmark import SpeakingBenchmarkHumanLabel as Label
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingCheckpoint as Checkpoint
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRObservation as Observation
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRReference as Reference
from app.schemas.speaking_benchmark_research import METRIC_PROTOCOL, NORMALIZATION
from app.services.speaking_benchmark import failure
from app.services.speaking_benchmark_reports import bands, selected_label
from app.services.speaking_benchmark_research import owned_experiment, variants_for
from app.services.speaking_benchmark_research_metrics import (
    normalized_text,
    observation_metrics,
    paired_difference,
    summarize_asr,
    transcript_diff,
)

FIELDS = ("fc", "lr", "gra", "pr", "overall")


async def research_report(
    service,
    experiment_id,
    *,
    latest_references=False,
    label_selection=None,
    split=None,
    part=None,
    provider_key=None,
    min_duration_ms=None,
    max_duration_ms=None,
    accent=None,
    speaking_speed=None,
    response_length=None,
    human_overall=None,
    sample_id_filter=None,
    segment_id=None,
):
    async with service.session.begin():
        experiment = await owned_experiment(service, experiment_id)
        variants = await variants_for(service.session, experiment_id)
        variant_map = {(str(v.sample_id), v.provider_key): v for v in variants}
        observations = (
            list(
                await service.session.scalars(
                    select(Observation)
                    .where(Observation.variant_id.in_([v.id for v in variants]))
                    .order_by(Observation.attempt)
                )
            )
            if variants
            else []
        )
        observed = {(o.variant_id, o.segment_id): o for o in observations}
        p2_requests = []
        seen_runs = set()
        for variant in variants:
            if not variant.grading_run_id or variant.grading_run_id in seen_runs:
                continue
            seen_runs.add(variant.grading_run_id)
            run = await service.session.get(Run, variant.grading_run_id)
            if not run or run.owner_id != service.owner_id:
                continue
            reused = run.submission_key != variant.id and run.consent.get(
                "research_experiment"
            ) != str(experiment.id)
            for checkpoint in await service.session.scalars(
                select(Checkpoint)
                .where(Checkpoint.run_id == run.id, Checkpoint.provider != "cpu")
                .order_by(Checkpoint.created_at, Checkpoint.id)
            ):
                p2_requests.append(
                    {
                        "id": str(checkpoint.id),
                        "variant_id": str(variant.id),
                        "segment_id": checkpoint.stage,
                        "status": checkpoint.status,
                        "billing_state": checkpoint.billing_state,
                        "provider": checkpoint.provider,
                        "usage": checkpoint.usage or {},
                        "error_code": checkpoint.error_code,
                        "run_id": str(run.id),
                        "reused_artifact": reused,
                        "cache_reused": checkpoint.reused_from is not None,
                        "reused_from": str(checkpoint.reused_from)
                        if checkpoint.reused_from
                        else None,
                        "usage_available": checkpoint.usage is not None,
                    }
                )
        selected, rows, band_rows = experiment.evaluation_selection, [], []
        for sample in experiment.configuration["cohort"]:
            if sample_id_filter and str(sample_id_filter) != sample["sample_id"]:
                continue
            if split and sample["split"] != split:
                continue
            sample_id = UUID(sample["sample_id"])
            if label_selection:
                from app.services.speaking_benchmark_human import resolve_human_label

                resolved = await resolve_human_label(
                    service.session,
                    service.owner_id,
                    sample_id,
                    sample["review_revision"],
                    label_selection,
                )
                human = resolved.get("bands") if resolved.get("eligible") else dict.fromkeys(FIELDS)
                label_rev = resolved.get("revision") if resolved.get("eligible") else None
            else:
                label_revision = selected["labels"].get(sample["sample_id"])
                label = (
                    await selected_label(service.session, sample_id)
                    if latest_references
                    else await service.session.get(Label, (sample_id, label_revision))
                    if label_revision
                    else None
                )
                human = bands(label if label and label.verified else None)
                label_rev = label.revision if label else None
            if human_overall is not None and human["overall"] != human_overall:
                continue
            for config in experiment.configuration["variants"]:
                variant_key = config["key"]
                if provider_key and variant_key != provider_key:
                    continue
                variant = variant_map.get((sample["sample_id"], variant_key))
                run = (
                    await service.session.get(Run, variant.grading_run_id)
                    if variant and variant.grading_run_id
                    else None
                )
                ai = {
                    f: (run.prediction or {}).get("bands", {}).get(f) if run else None
                    for f in FIELDS
                }
                comparable_config = (
                    not run
                    or run.configuration == config["grading"]
                    and run.manifest_fingerprint == sample["manifest_fingerprint"]
                    and run.review_revision == sample["review_revision"]
                )
                if not comparable_config:
                    ai = dict.fromkeys(FIELDS)
                band_rows.append(
                    {
                        "sample_id": sample["sample_id"],
                        "candidate_id": sample["candidate_id"],
                        "provider": variant_key,
                        "label_revision": label_rev,
                        **({"human_label_selection": resolved} if label_selection else {}),
                        "human": human,
                        "ai": ai,
                        "run_id": str(run.id) if run else None,
                        "status": run.status if run else "MISSING",
                        "isolated_asr_configuration": comparable_config,
                        "signed_error": {
                            f: ai[f] - human[f]
                            if ai[f] is not None and human[f] is not None
                            else None
                            for f in FIELDS
                        },
                        "absolute_error": {
                            f: abs(ai[f] - human[f])
                            if ai[f] is not None and human[f] is not None
                            else None
                            for f in FIELDS
                        },
                    }
                )
                checkpoints = (
                    list(
                        await service.session.scalars(
                            select(Checkpoint)
                            .join(Run)
                            .where(
                                Run.owner_id == service.owner_id,
                                Run.sample_id == sample_id,
                                Run.manifest_fingerprint == sample["manifest_fingerprint"],
                                Run.review_revision == sample["review_revision"],
                                Checkpoint.run_id == run.id,
                            )
                            .order_by(Checkpoint.created_at.desc(), Checkpoint.id)
                        )
                    )
                    if experiment.mode == "PAIRED_GRADING" and run and comparable_config
                    else []
                )
                for window in sample["windows"]:
                    if segment_id and window["id"] != segment_id:
                        continue
                    duration = window["end_ms"] - window["start_ms"]
                    if (
                        part
                        and window["part_number"] != part
                        or min_duration_ms is not None
                        and duration < min_duration_ms
                        or max_duration_ms is not None
                        and duration > max_duration_ms
                    ):
                        continue
                    ref_id = selected["references"].get(f"{sample_id}:{window['id']}")
                    reference = (
                        await service.session.scalar(
                            select(Reference)
                            .where(
                                Reference.owner_id == service.owner_id,
                                Reference.sample_id == sample_id,
                                Reference.review_revision == sample["review_revision"],
                                Reference.segment_id == window["id"],
                                Reference.status == "VERIFIED",
                            )
                            .order_by(Reference.revision.desc())
                            .limit(1)
                        )
                        if latest_references
                        else await service.session.get(Reference, UUID(ref_id))
                        if ref_id
                        else None
                    )
                    if reference and (
                        reference.source_sha256 != sample["source_sha256"]
                        or reference.manifest_fingerprint != sample["manifest_fingerprint"]
                        or reference.start_ms != window["start_ms"]
                        or reference.end_ms != window["end_ms"]
                    ):
                        reference = None
                    metadata = reference.metadata_labels if reference else {}
                    if any(
                        value and metadata.get(key) != value
                        for key, value in (
                            ("accent", accent),
                            ("speaking_speed", speaking_speed),
                            ("response_length", response_length),
                        )
                    ):
                        continue
                    observation = observed.get((variant.id, window["id"])) if variant else None
                    result = observation.result if observation else None
                    p2_checkpoint = None
                    if experiment.mode == "PAIRED_GRADING":
                        stage = (
                            f"azure:{window['id']}"
                            if config["provider"] == "azure_pa"
                            else f"lexical:{window['id']}"
                        )
                        p2_checkpoint = next(
                            (c for c in checkpoints if c.stage == stage),
                            None,
                        )
                        result = (
                            p2_checkpoint.result
                            if p2_checkpoint and p2_checkpoint.status == "COMPLETED"
                            else None
                        )
                        if result and (
                            result.get("provider") != config["identity"]
                            or result.get("source", {}).get("audio_fingerprint")
                            != sample["source_sha256"]
                        ):
                            result = None
                    request = p2_checkpoint if experiment.mode == "PAIRED_GRADING" else observation
                    cached = bool(
                        p2_checkpoint.reused_from
                        if p2_checkpoint
                        else observation and observation.billing_state == "CACHE_REUSED"
                    )
                    row = {
                        "experiment_id": str(experiment.id),
                        "variant_id": str(variant.id) if variant else None,
                        "sample_id": str(sample_id),
                        "code": sample["code"],
                        "candidate_id": sample["candidate_id"],
                        "split": sample["split"],
                        "review_revision": sample["review_revision"],
                        "source_sha256": sample["source_sha256"],
                        "manifest_fingerprint": sample["manifest_fingerprint"],
                        "segment_id": window["id"],
                        "part": window["part_number"],
                        "start_ms": window["start_ms"],
                        "end_ms": window["end_ms"],
                        "provider": variant_key,
                        "model_identity": config["identity"],
                        "status": "UNKNOWN"
                        if request
                        and request.status in {"ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"}
                        else result["status"]
                        if result
                        else "UNAVAILABLE"
                        if request and request.status == "COMPLETED"
                        else request.status
                        if request
                        else "NOT_ATTEMPTED",
                        "reference_id": str(reference.id) if reference else None,
                        "reference_revision": reference.revision if reference else None,
                        "reference_status": reference.status if reference else "UNAVAILABLE",
                        "reference_uncertainty": reference.uncertainty if reference else [],
                        "reference_text": reference.text if reference else None,
                        "text": result["lexical_transcript"] if result else None,
                        "metadata_labels": metadata,
                        "latency_ms": result.get("latency_ms") if result else None,
                        "new_requests": 0 if not request or cached else 1,
                        "cache_reused": cached,
                        "usage": [result["usage"]] if request and not cached and result else [],
                        "observation_id": str(observation.id) if observation else None,
                        "billing_state": request.billing_state if request else None,
                        "p2_checkpoint_id": str(p2_checkpoint.id) if p2_checkpoint else None,
                        "words": result.get("words", []) if result else [],
                        "diff": transcript_diff(reference.text, result["lexical_transcript"])
                        if reference and result
                        else [],
                        **observation_metrics(result, reference, duration),
                    }
                    rows.append(row)
        if len(rows) > service.settings.speaking_benchmark_report_max_rows:
            raise failure("SPEAKING_RESEARCH_REPORT_TOO_LARGE", 422)
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["provider"]].append(row)
        summary = {key: summarize_asr(values) for key, values in grouped.items()}
        # Count every physical attempt, including unsuccessful older attempts.
        # A latest-response projection must not erase timeout/reconciliation usage.
        variant_keys = {v.id: v.provider_key for v in variants}
        for provider, values in summary.items():
            attempts = [o for o in observations if variant_keys.get(o.variant_id) == provider]
            physical = [o for o in attempts if o.billing_state != "CACHE_REUSED"]
            values["new_requests"] = len(physical)
            values["cache_hits"] = sum(o.billing_state == "CACHE_REUSED" for o in attempts)
            values["unknown_billing_attempts"] = sum(
                o.status in {"ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"} for o in physical
            )
            values["unknown_usage_requests"] = sum(o.usage is None for o in physical)
            values["observed_usage"] = {
                field: sum((o.usage or {}).get(field, 0) or 0 for o in physical)
                for field in (
                    "attempted_calls",
                    "submitted_audio_ms",
                    "successful_calls",
                    "failed_calls",
                    "host_process_cpu_seconds",
                )
            }
            if experiment.mode == "PAIRED_GRADING":
                requests = [
                    r for r in p2_requests if variant_keys.get(UUID(r["variant_id"])) == provider
                ]
                physical = [r for r in requests if not r["cache_reused"]]
                values["new_requests"] = sum(not r["reused_artifact"] for r in physical)
                values["cache_hits"] = sum(r["cache_reused"] for r in requests)
                values["unknown_billing_attempts"] = sum(
                    r["status"] in {"ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"} for r in physical
                )
                values["unknown_usage_requests"] = sum(not r["usage_available"] for r in physical)
                values["observed_usage"] = {
                    "p2_physical_requests": len(physical),
                    "by_service": {
                        p: {
                            "requests": sum(r["provider"] == p for r in physical),
                            "units": [r["usage"] for r in physical if r["provider"] == p],
                        }
                        for p in {r["provider"] for r in physical}
                    },
                }
        eligible_samples = {r["sample_id"] for r in rows}
        band_rows = [r for r in band_rows if r["sample_id"] in eligible_samples]
        paired_asr, paired_bands, disagreement = [], [], []
        provider_keys = sorted(grouped)
        for left, right in combinations(provider_keys, 2):
            left_rows = {(r["sample_id"], r["segment_id"]): r for r in grouped[left]}
            right_rows = {(r["sample_id"], r["segment_id"]): r for r in grouped[right]}
            sample_deltas = defaultdict(list)
            for key in sorted(left_rows.keys() & right_rows.keys()):
                a, b = left_rows[key], right_rows[key]
                if a["text"] is not None and b["text"] is not None:
                    at, bt = (
                        _tokens(normalized_text(a["text"])),
                        _tokens(normalized_text(b["text"])),
                    )
                    disagreement.append(
                        {
                            "sample_id": a["sample_id"],
                            "segment_id": a["segment_id"],
                            "left": left,
                            "right": right,
                            "word_edit_distance": _edit_distance(at, bt)
                            if len(at) * len(bt) <= 4_000_000
                            else None,
                            "is_accuracy": False,
                        }
                    )
                if (
                    a["metrics"].get("wer") is not None
                    and b["metrics"].get("wer") is not None
                    and a["reference_id"] == b["reference_id"]
                ):
                    sample_deltas[(a["sample_id"], a["candidate_id"])].append(
                        a["metrics"]["wer"] - b["metrics"]["wer"]
                    )
            paired_asr.append(
                {
                    "left": left,
                    "right": right,
                    "metric": "sample_macro_wer_difference",
                    **paired_difference(
                        [
                            (candidate, sum(v) / len(v))
                            for (_, candidate), v in sample_deltas.items()
                        ]
                    ),
                }
            )
            a_bands = {r["sample_id"]: r for r in band_rows if r["provider"] == left}
            b_bands = {r["sample_id"]: r for r in band_rows if r["provider"] == right}
            for field in FIELDS:
                values = [
                    (
                        a_bands[k]["candidate_id"],
                        a_bands[k]["absolute_error"][field] - b_bands[k]["absolute_error"][field],
                    )
                    for k in a_bands.keys() & b_bands.keys()
                    if a_bands[k]["label_revision"] == b_bands[k]["label_revision"]
                    and a_bands[k]["absolute_error"][field] is not None
                    and b_bands[k]["absolute_error"][field] is not None
                ]
                paired_bands.append(
                    {"left": left, "right": right, "criterion": field, **paired_difference(values)}
                )
        band_summary = {}
        for provider in provider_keys:
            selected_bands = [r for r in band_rows if r["provider"] == provider]
            band_summary[provider] = {
                f: score_metrics(
                    [r["human"][f] for r in selected_bands if r["human"][f] is not None],
                    [r["ai"][f] for r in selected_bands if r["human"][f] is not None],
                )
                | {
                    "human_label_unavailable_count": sum(
                        r["human"][f] is None for r in selected_bands
                    ),
                    "selected_samples": len(selected_bands),
                }
                for f in FIELDS
            }
        band_lookup = {(r["sample_id"], r["provider"]): r for r in band_rows}
        for row in rows:
            band = (
                band_lookup.get((row["sample_id"], row["provider"]))
                if experiment.mode == "PAIRED_GRADING"
                else None
            )
            row["band_comparison"] = band
            row["band_aggregate"] = (
                band_summary.get(row["provider"]) if experiment.mode == "PAIRED_GRADING" else None
            )
        return {
            "schema_version": METRIC_PROTOCOL,
            "normalization": NORMALIZATION,
            "experiment_id": str(experiment.id),
            "status": experiment.status,
            "mode": experiment.mode,
            "fingerprint": experiment.fingerprint,
            "configuration": experiment.configuration,
            "reference_policy": "latest-verified" if latest_references else "frozen",
            "selected_evaluation_revisions": selected,
            "summary": summary,
            "paired_asr": paired_asr,
            "band_summary": band_summary if experiment.mode == "PAIRED_GRADING" else {},
            "band_rows": band_rows if experiment.mode == "PAIRED_GRADING" else [],
            "paired_bands": paired_bands if experiment.mode == "PAIRED_GRADING" else [],
            "disagreement": disagreement,
            "rows": rows,
            "outliers": sorted(
                [r for r in rows if r["metrics"].get("wer") is not None],
                key=lambda r: r["metrics"]["wer"],
                reverse=True,
            )[:10],
            "limitations": experiment.configuration.get("dataset_warnings", [])
            + [
                "LIVE_ACCURACY_UNVERIFIED",
                "ASR_IS_NOT_GROUND_TRUTH",
                "INSERTIONS_ARE_HALLUCINATION_PROXIES",
                "RECOGNIZED_WINDOWS_ARE_NOT_VAD_COVERAGE",
                "LLM_OUTPUT_VARIABILITY",
                "FIXED_PA_PR_IS_NOT_AN_ASR_IMPROVEMENT",
                "SMALL_SUBSETS_DO_NOT_IDENTIFY_A_WINNER",
                "REFERENCE_UNCERTAINTY_EXCLUDES_WHOLE_WINDOW",
                "REMOTE_RESOURCE_USAGE_UNAVAILABLE",
                "CACHED_LATENCY_IS_ORIGINAL_OBSERVATION",
            ],
            "estimates_usd": (experiment.consent or {}).get("estimates_usd", {}),
            "admission_authorizations": {
                "current": {
                    k: v
                    for k, v in (experiment.consent or {}).items()
                    if k != "previous_authorizations"
                },
                "history": (experiment.consent or {}).get("previous_authorizations", []),
            },
            "physical_requests": p2_requests
            + [
                {
                    "id": str(o.id),
                    "variant_id": str(o.variant_id),
                    "segment_id": o.segment_id,
                    "status": o.status,
                    "billing_state": o.billing_state,
                    "usage": o.usage or {},
                    "reconciliation": o.reconciliation,
                    "error_code": o.error_code,
                }
                for o in observations
            ],
        }


def research_export(report, format):
    # Normalized text hypotheses are a separately authenticated comparison view;
    # default exports contain metrics/provenance, never full speech/provider payloads.
    output = {k: v for k, v in report.items() if k not in {"rows", "outliers", "physical_requests"}}
    output["rows"] = [
        {k: v for k, v in row.items() if k not in {"reference_text", "text", "words", "diff"}}
        for row in report["rows"]
    ]
    if format == "json":
        return json.dumps(output, ensure_ascii=False, allow_nan=False)
    buffer = io.StringIO(newline="")
    fields = [
        "schema_version",
        "experiment_id",
        "variant_id",
        "sample_id",
        "code",
        "split",
        "review_revision",
        "source_sha256",
        "manifest_fingerprint",
        "segment_id",
        "provider",
        "model_identity",
        "reference_revision",
        "reference_status",
        "status",
        "metrics",
        "coverage",
        "latency_ms",
        "real_time_factor",
        "usage",
        "billing_state",
        "band_comparison",
        "band_aggregate",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in output["rows"]:
        values = {}
        for key in fields:
            value = METRIC_PROTOCOL if key == "schema_version" else row.get(key)
            text = (
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else ""
                if value is None
                else str(value)
            )
            values[key] = (
                "'" + text
                if text.startswith(("\t", "\r", "\n"))
                or text.lstrip().startswith(("=", "+", "-", "@"))
                else text
            )
        writer.writerow(values)
    return "\ufeff" + buffer.getvalue()
