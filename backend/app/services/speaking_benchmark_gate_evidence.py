"""Resolve frozen suites against exact persisted artifacts. No inference imports."""

from uuid import UUID

from sqlalchemy import select

from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingCheckpoint as Checkpoint
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRObservation as Observation
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRReference as Reference
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperiment as Experiment
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperimentVariant as Variant
from app.schemas.speaking_benchmark_research import METRIC_PROTOCOL
from app.services.speaking_benchmark import failure
from app.services.speaking_benchmark_research_metrics import observation_metrics


def fixed_grading(config):
    return {k: v for k, v in config.items() if k not in {"lexical", "lexical_provider"}}


def request_metrics(requests):
    external = [r for r in requests if getattr(r, "provider", None) != "cpu"]
    physical = [r for r in external if r.reused_from is None]
    return dict(
        physical_requests=len(physical),
        unknown_billing_attempts=sum(
            r.status in {"ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"}
            and not getattr(r, "reconciliation", None)
            for r in physical
        ),
        provider_audio_ms=sum((r.usage or {}).get("submitted_audio_ms", 0) for r in physical),
        cache_reuse_rate=(len(external) - len(physical)) / len(external) if external else None,
    )


async def lexical_metrics(session, sample, results, identity):
    refs = {r["segment_id"]: r for r in sample.get("references", [])}
    totals = dict(word_errors=0, reference_words=0, character_errors=0, reference_characters=0)
    events = {k: [0, 0] for k in ("filler", "repetition")}
    recognized = duration = completed = latency = latency_count = 0
    ref_count = 0
    for window in sample.get("windows", []):
        span = window["end_ms"] - window["start_ms"]
        duration += span
        request = results.get(window["id"])
        result = request.result if request and request.status == "COMPLETED" else None
        if result and (
            result.get("provider") != identity
            or result.get("source", {}).get("audio_fingerprint") != sample["source_sha256"]
        ):
            return {}, ["PROVIDER_RESULT_BINDING_MISMATCH"]
        ref_info = refs.get(window["id"], {})
        ref = (
            await session.get(Reference, UUID(ref_info["id"]))
            if ref_info.get("id") and ref_info.get("eligible")
            else None
        )
        if ref and (
            str(ref.sample_id) != sample["sample_id"]
            or ref.review_revision != sample["review_revision"]
            or ref.source_sha256 != sample["source_sha256"]
            or ref.manifest_fingerprint != sample["manifest_fingerprint"]
            or ref.start_ms != window["start_ms"]
            or ref.end_ms != window["end_ms"]
            or ref.revision != ref_info["revision"]
        ):
            return {}, ["FROZEN_REFERENCE_BINDING_MISMATCH"]
        projected = observation_metrics(result, ref, span)
        m = projected["metrics"]
        if m.get("wer") is not None:
            ref_count += 1
            for field in totals:
                totals[field] += m.get(field, 0) or 0
            for kind in events:
                e = m["preservation"][kind]
                events[kind][0] += e["preserved_events"]
                events[kind][1] += e["reference_events"]
        if result:
            completed += int(result.get("coverage", {}).get("stream_completed", False))
            recognized += (projected["coverage"] or {}).get("recognized_window_ms", 0)
            if result.get("latency_ms") is not None:
                latency += result["latency_ms"]
                latency_count += 1
    # Never hide missing windows behind a favorable completed subset.
    complete_refs = ref_count == len(sample.get("windows", [])) and ref_count > 0
    return dict(
        wer=totals["word_errors"] / totals["reference_words"]
        if complete_refs and totals["reference_words"]
        else None,
        cer=totals["character_errors"] / totals["reference_characters"]
        if complete_refs and totals["reference_characters"]
        else None,
        filler_recall=events["filler"][0] / events["filler"][1]
        if complete_refs and events["filler"][1]
        else None,
        repetition_recall=events["repetition"][0] / events["repetition"][1]
        if complete_refs and events["repetition"][1]
        else None,
        recognition_coverage=recognized / duration if duration else None,
        failure_rate=1 - completed / len(sample["windows"]) if sample.get("windows") else 1,
        latency_ms=latency
        if latency_count == len(sample.get("windows", [])) and latency_count
        else None,
        real_time_factor=latency / duration
        if duration and latency_count == len(sample.get("windows", [])) and latency_count
        else None,
    ), []


async def collect_persisted_evidence(service, suite, selection):
    samples = suite.configuration["samples"]
    variants, exp, selected_config = {}, None, None
    if selection.kind == "EXPERIMENT":
        exp = await service.session.scalar(
            select(Experiment).where(
                Experiment.id == selection.id, Experiment.owner_id == service.owner_id
            )
        )
        if exp is None:
            raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
        selected_config = next(
            (v for v in exp.configuration["variants"] if v["key"] == selection.variant_key), None
        )
        if selected_config is None:
            raise failure("SPEAKING_RESEARCH_VARIANT_NOT_FOUND", 404)
        variants = {
            str(v.sample_id): v
            for v in await service.session.scalars(
                select(Variant).where(
                    Variant.experiment_id == exp.id,
                    Variant.owner_id == service.owner_id,
                    Variant.provider_key == selection.variant_key,
                )
            )
        }
    rows, configs, invalid = [], [], []
    for sample in samples:
        run, variant, requests, results = None, variants.get(sample["sample_id"]), [], {}
        if exp is None:
            run = await service.session.scalar(
                select(Run)
                .where(
                    Run.owner_id == service.owner_id,
                    Run.sample_id == UUID(sample["sample_id"]),
                    Run.review_revision == sample["review_revision"],
                    Run.manifest_fingerprint == sample["manifest_fingerprint"],
                    Run.config_fingerprint == selection.configuration_fingerprint,
                )
                .order_by(Run.created_at.desc(), Run.id.desc())
                .limit(1)
            )
        elif variant:
            if (
                variant.review_revision != sample["review_revision"]
                or variant.manifest_fingerprint != sample["manifest_fingerprint"]
                or variant.source_sha256 != sample["source_sha256"]
            ):
                invalid.append("EXPERIMENT_SUITE_BINDING_MISMATCH")
            if exp.mode == "PAIRED_GRADING" and variant.grading_run_id:
                run = await service.session.get(Run, variant.grading_run_id)
        config = run.configuration if run else (selected_config or {}).get("grading")
        if config:
            configs.append(config)
        if run:
            if (
                run.owner_id != service.owner_id
                or str(run.sample_id) != sample["sample_id"]
                or run.source_sha256 != sample["source_sha256"]
                or run.review_revision != sample["review_revision"]
                or run.manifest_fingerprint != sample["manifest_fingerprint"]
                or selected_config
                and run.configuration != selected_config["grading"]
            ):
                invalid.append("GRADING_SUITE_BINDING_MISMATCH")
            requests = list(
                await service.session.scalars(
                    select(Checkpoint)
                    .where(Checkpoint.run_id == run.id)
                    .order_by(Checkpoint.attempt, Checkpoint.created_at, Checkpoint.id)
                )
            )
            lexical = run.configuration["lexical_provider"]
            prefix = "azure:" if lexical == "azure_pa" else "lexical:"
            results = {r.stage[len(prefix) :]: r for r in requests if r.stage.startswith(prefix)}
            identity = run.configuration["lexical"]
        elif variant and exp.mode == "ASR_ONLY":
            requests = list(
                await service.session.scalars(
                    select(Observation)
                    .where(Observation.variant_id == variant.id)
                    .order_by(Observation.attempt, Observation.created_at, Observation.id)
                )
            )
            results = {r.segment_id: r for r in requests}
            identity = selected_config["identity"]
        else:
            identity = None
        metrics, errors = await lexical_metrics(service.session, sample, results, identity)
        invalid.extend(errors)
        metrics.update(request_metrics(requests))
        available = (
            bool(run and run.status in {"COMPLETED", "PARTIAL"} and run.prediction is not None)
            if exp is None or exp.mode == "PAIRED_GRADING"
            else bool(
                variant
                and variant.status in {"COMPLETED", "PARTIAL"}
                and all(
                    w["id"] in results and results[w["id"]].status == "COMPLETED"
                    for w in sample["windows"]
                )
            )
        )
        metrics["missing_artifact_count"] = int(not available)
        rows.append(
            {
                k: sample.get(k)
                for k in (
                    "sample_id",
                    "candidate_id",
                    "review_revision",
                    "source_sha256",
                    "manifest_fingerprint",
                    "label_fingerprint",
                    "reference_fingerprint",
                )
            }
            | dict(
                available=available,
                ai=(run.prediction or {}).get("bands", {}) if run else {},
                metrics=metrics,
                run_id=str(run.id) if run else None,
                variant_id=str(variant.id) if variant else None,
                request_ids=[str(r.id) for r in requests],
                reference_ids=[r["id"] for r in sample.get("references", []) if r.get("id")],
            )
        )
    if configs and any(c != configs[0] for c in configs):
        invalid.append("MIXED_GRADING_CONFIGURATIONS")
    config = configs[0] if configs else None
    return dict(
        rows=rows,
        invalid_reasons=sorted(set(invalid)),
        selection=selection.model_dump(mode="json"),
        configuration=dict(
            metric_protocol=METRIC_PROTOCOL,
            rubric_version=config["scorer"]["rubric_version"] if config else None,
            fixed_grading=fixed_grading(config) if config else None,
            grading=config,
            lexical_identity=selected_config["identity"]
            if selected_config
            else (config or {}).get("lexical"),
        ),
    )
