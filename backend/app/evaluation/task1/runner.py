"""Sequential, resumable service-level evaluation; no database or score correction."""

import hashlib
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import median, pvariance
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from app.core.config import Settings
from app.domains.writing.visual_families import visual_family
from app.evaluation.task1.anchor_sources import AnchorSource, guard_leakage
from app.evaluation.task1.legacy_prompts import (
    LEGACY_TASK1_PROMPT_VERSION,
    LEGACY_TASK1_SCORING_PROMPT_VERSION,
    LegacyTask1WritingScoringService,
)
from app.evaluation.task1.manifest import LoadedSample
from app.evaluation.task1.metrics import overall_score, perception_metrics
from app.evaluation.task1.models import BenchmarkConfig, EvaluationRecord, digest
from app.providers.chart_derendering import ChartSpecialistFailure
from app.providers.chart_derendering.deplot import DePlotChartDerenderingProvider
from app.providers.writing_llm import create_provider, provider_identity
from app.providers.writing_llm.base import Completion, CompletionOptions, Message
from app.schemas.chart_cross_check import ChartSpecialistIdentity
from app.schemas.task1_claims import Task1Analysis
from app.services.task1_direct import Task1DirectScoringService
from app.services.task1_input import (
    TASK1_PROMPT_VERSION,
    TASK1_SCORING_PROMPT_VERSION,
    TASK1_VISUAL_CONTRACT_VERSION,
    Task1ScoringRequest,
)
from app.services.task1_tacs import Task1TACSScoringService
from app.services.task1_writing import Task1WritingScoringService


def implementation_hash() -> str:
    root = Path(__file__).resolve().parents[2]
    patterns = (
        "domains/scoring/*.py",
        "domains/writing/*.py",
        "services/task1*.py",
        "services/mts_writing.py",
        "services/writing_execution.py",
        "services/writing_pairwise.py",
        "schemas/tacs.py",
        "schemas/writing_anchors.py",
        "providers/writing_llm/*.py",
        "providers/chart_derendering/*.py",
        "schemas/task1*.py",
        "schemas/writing_ai.py",
        "schemas/chart_cross_check.py",
        "schemas/visual_number.py",
        "evaluation/task1/*.py",
        "core/config.py",
    )
    files = {path for pattern in patterns for path in root.glob(pattern)}
    # Universal newline decoding makes the same checkout reproducible on Windows
    # and Linux; cover the complete scoring/perception dependency boundary.
    return digest(
        {
            str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(
                path.read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            for path in sorted(files)
        }
    )


def configurations(
    settings: Settings, scoring_version: str, chart_specialist: str
) -> list[BenchmarkConfig]:
    versions = ["v3", "v5"] if scoring_version == "both" else [scoring_version]
    specialists = [False, True] if chart_specialist == "both" else [chart_specialist == "on"]
    if not set(versions) <= {"v3", "v5"} or chart_specialist not in {"off", "on", "both"}:
        raise ValueError("BENCHMARK_CONFIGURATION_INVALID")
    provider, model = provider_identity(settings)
    endpoint = (
        settings.ai_writing_vllm_base_url
        if provider == "vllm"
        else settings.ai_writing_openai_base_url
    )
    result = []
    for version in versions:
        for enabled in specialists:
            result.append(
                BenchmarkConfig(
                    max_concurrent_llm_requests=settings.ai_writing_max_concurrent_llm_requests,
                    label=f"task1-{version}-{'current' if version == 'v5' else 'legacy'}:deplot-{'on' if enabled else 'off'}",
                    scoring_version=version,
                    prompt_version=TASK1_PROMPT_VERSION
                    if version == "v5"
                    else LEGACY_TASK1_PROMPT_VERSION,
                    scoring_prompt_version=TASK1_SCORING_PROMPT_VERSION
                    if version == "v5"
                    else LEGACY_TASK1_SCORING_PROMPT_VERSION,
                    visual_contract_version=TASK1_VISUAL_CONTRACT_VERSION,
                    provider=provider,
                    model=model,
                    endpoint_hash=digest(endpoint),
                    specialist_endpoint_hash=digest(settings.ai_writing_deplot_base_url),
                    specialist=ChartSpecialistIdentity(
                        enabled=enabled,
                        provider=settings.ai_writing_chart_specialist_provider,
                        model=settings.ai_writing_deplot_model,
                        revision=settings.ai_writing_deplot_revision,
                    ),
                    request_timeout_seconds=settings.ai_writing_request_timeout_seconds,
                    startup_timeout_seconds=settings.ai_writing_startup_timeout_seconds,
                    specialist_timeout_seconds=settings.ai_writing_chart_specialist_timeout_seconds,
                    implementation_hash=implementation_hash(),
                )
            )
    return result


def fingerprint(item: LoadedSample, config: BenchmarkConfig) -> tuple[str, str, str]:
    # Evaluation annotations are included: modifying a target/truth never returns
    # stale metrics. No original content or credential is stored in the key.
    sample_hash = digest(item.sample.model_dump(mode="json", exclude={"image_path"}))
    image_hash = hashlib.sha256(item.image.data).hexdigest()
    return (
        sample_hash,
        image_hash,
        digest({"sample": sample_hash, "image": image_hash, "config": config.key}),
    )


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def cached_record(
    path: Path, cache_key: str, config_key: str, sample_id: str
) -> EvaluationRecord | None:
    attempts = sorted((path.parent.parent / "attempts" / cache_key).glob("*.json"))
    # An attempt is written before its latest checkpoint. Recover a completed
    # attempt after interrupted/corrupt checkpoint writes without another call.
    if attempts:
        path = attempts[-1]
    try:
        record = EvaluationRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError):
        return None
    if (record.cache_key, record.config_key, record.sample_id, record.status) != (
        cache_key,
        config_key,
        sample_id,
        "COMPLETED",
    ):
        return None
    return record.model_copy(update={"cache_hit": True})


def save_attempt(output: Path, record: EvaluationRecord) -> None:
    directory = output / "attempts" / record.cache_key
    existing = [
        int(path.stem)
        for path in directory.glob("*.json")
        if path.stem.isdecimal() and len(path.stem) <= 9
    ]
    number = max(existing, default=0) + 1
    atomic_write(directory / f"{number:06d}.json", record.model_dump_json(indent=2))


def attempt_history(output: Path, records: list[EvaluationRecord]) -> list[EvaluationRecord]:
    result = []
    for record in records:
        files = sorted((output / "attempts" / record.cache_key).glob("*.json"))
        for path in files:
            try:
                attempt = EvaluationRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, ValidationError):
                continue
            if (attempt.cache_key, attempt.config_key, attempt.sample_id) == (
                record.cache_key,
                record.config_key,
                record.sample_id,
            ):
                result.append(attempt)
    return result


class CountedProvider:
    def __init__(self, provider):
        self.provider, self.calls, self.usage = provider, 0, Counter()

    async def ensure_ready(self):
        await self.provider.ensure_ready()

    async def complete(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        *,
        options: CompletionOptions | None = None,
    ) -> Completion:
        self.calls += 1
        completion = await self.provider.complete(messages, schema, options=options)
        # Only known numeric usage counters, never arbitrary provider fields.
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = completion.usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                self.usage[key] += value
        return completion


class CountedSpecialist:
    def __init__(self, provider):
        self.provider, self.calls, self.latency = provider, 0, 0.0

    async def extract(self, image):
        self.calls += 1
        start = time.perf_counter()
        try:
            return await self.provider.extract(image)
        finally:
            self.latency += time.perf_counter() - start


class UnavailableSpecialist:
    """Injected scorer tests must not accidentally fall through to real HTTP."""

    async def extract(self, _image):
        raise ChartSpecialistFailure()


def classify(status, confidence, perception, disagreements, target, predicted):
    if status != "COMPLETED" or confidence == "UNUSABLE":
        return "UNUSABLE"
    if disagreements:
        return "SPECIALIST_DISAGREEMENT"
    final = perception.get("reconciled")
    if final and final["perception_ok"] is False:
        return "PERCEPTION_ERROR"
    prefix = "PERCEPTION_OK" if final and final["perception_ok"] else "PERCEPTION_UNANNOTATED"
    errors = [predicted[trait] - target[trait] for trait in target]
    # This is an evaluation agreement window, never an adjustment to a score.
    high, low = (
        any(error > Decimal("0.5") for error in errors),
        any(error < Decimal("-0.5") for error in errors),
    )
    suffix = "MIXED" if high and low else "HIGH" if high else "LOW" if low else "OK"
    return f"{prefix}_SCORE_{suffix}"


async def evaluate(
    item: LoadedSample,
    config: BenchmarkConfig,
    provider_factory,
    specialist_factory,
    anchor_source=None,
) -> EvaluationRecord:
    if config.architecture == "direct-self-consistency":
        return await evaluate_repeats(item, config, provider_factory, specialist_factory)
    start = time.perf_counter()
    sample_hash, image_hash, cache_key = fingerprint(item, config)
    sample = item.sample
    predicted, failures = {}, {}
    analysis = Task1Analysis(visual_family=visual_family(sample.task_type).value)
    perception = {"primary": None, "reconciled": None}
    provider, specialist = None, None
    scorer = None

    async def trace(event, payload):
        nonlocal analysis
        if payload.task1_analysis is not None:
            analysis = payload.task1_analysis.model_copy(deep=True)
        if event == "visual_grounding.completed":
            perception["primary"] = perception_metrics(sample.visual_truth, analysis.reference)
            perception["reconciled"] = perception["primary"]
        elif event == "chart_reconciliation.completed":
            perception["reconciled"] = perception_metrics(sample.visual_truth, analysis.reference)
        elif event == "criterion.completed":
            predicted[payload.criterion] = payload.result.score
        elif event == "criterion.failed":
            failures[payload.criterion] = "CRITERION_FAILED"

    try:
        provider = CountedProvider(provider_factory(config))
        if config.specialist.enabled and visual_family(sample.task_type).value == "chart_table":
            try:
                specialist = CountedSpecialist(specialist_factory(config))
            except Exception:
                specialist = CountedSpecialist(UnavailableSpecialist())
        scorer_type = (
            Task1TACSScoringService
            if config.architecture == "anchor-pairwise"
            else Task1DirectScoringService
            if config.architecture == "direct"
            else LegacyTask1WritingScoringService
            if config.scoring_version == "v3"
            else Task1WritingScoringService
        )
        scorer = scorer_type(
            provider,
            specialist,
            chart_timeout=config.specialist_timeout_seconds,
            max_concurrent_requests=config.max_concurrent_llm_requests,
            **(
                {
                    "anchor_snapshot": (anchor_source or AnchorSource()).snapshot,
                    "target_fingerprint": digest(
                        {
                            "prompt": sample.prompt,
                            "essay": sample.essay,
                            "image": image_hash,
                            "task": sample.id,
                        }
                    ),
                    "max_tree_nodes": config.tree_node_budget,
                }
                if config.architecture == "anchor-pairwise"
                else {}
            ),
        )
        await provider.ensure_ready()
        # Deliberately construct only production inputs; no target/truth/provenance.
        request = Task1ScoringRequest(
            attempt_id=uuid5(NAMESPACE_URL, f"benchmark:{sample.id}"),
            writing_task_id=uuid5(NAMESPACE_URL, f"benchmark-task:{sample.id}"),
            task_type=sample.task_type,
            prompt=sample.prompt,
            response=sample.essay,
            image=item.image,
            chart_specialist=config.specialist.model_copy(deep=True),
        )
        result = await scorer.assess(request, trace)
        status = "COMPLETED" if result is not None else "FAILED"
    except Exception:
        # Exception messages may contain content or credentials. Cancellation and
        # KeyboardInterrupt (BaseException) still terminate the run.
        status = "FAILED"
        failures["run"] = "BENCHMARK_SAMPLE_FAILED"
    if perception["primary"] is None and sample.visual_truth is not None:
        perception["primary"] = perception_metrics(sample.visual_truth, None)
        perception["reconciled"] = perception["primary"]
    target = sample.human_scores.scores()
    disagreements = analysis.cross_check.disagreement_count if analysis.cross_check else 0
    return EvaluationRecord(
        architecture=config.architecture,
        scoring_diagnostics=scorer.scoring_metadata()
        if scorer and hasattr(scorer, "scoring_metadata")
        else {},
        sample_id=sample.id,
        split=sample.split,
        task_type=sample.task_type,
        visual_family=visual_family(sample.task_type).value,
        config_key=config.key,
        input_hash=sample_hash,
        image_hash=image_hash,
        cache_key=cache_key,
        status=status,
        target=target,
        predicted=predicted,
        target_overall=overall_score(target),
        predicted_overall=overall_score(predicted),
        confidence=analysis.confidence.value,
        perception=perception,
        specialist_status=analysis.cross_check.status if analysis.cross_check else None,
        specialist_disagreements=disagreements,
        decomposition=classify(
            status, analysis.confidence, perception, disagreements, target, predicted
        ),
        wall_clock_seconds=time.perf_counter() - start,
        provider_calls=provider.calls if provider else 0,
        token_usage=dict(provider.usage) if provider else {},
        specialist_calls=specialist.calls if specialist else 0,
        specialist_latency_seconds=specialist.latency if specialist else 0,
        failures=failures,
    )


async def evaluate_repeats(item, config, provider_factory, specialist_factory):
    start = time.perf_counter()
    child = config.model_copy(
        update={"architecture": "direct", "architecture_id": "A0", "self_consistency_count": 1}
    )
    records = [await evaluate(item, child, provider_factory, specialist_factory) for _ in range(3)]
    sample_hash, image_hash, key = fingerprint(item, config)
    scores = {
        t: median(r.predicted[t] for r in records)
        for t in ("ta", "cc", "lr", "gra")
        if all(t in r.predicted for r in records)
    }
    perception = {}
    for stage in ("primary", "reconciled"):
        observations = [r.perception[stage] for r in records]
        if all(o is None for o in observations):
            perception[stage] = None
        else:
            representative = next(o for o in observations if o is not None)
            perception[stage] = {
                **representative,
                "perception_ok": True
                if all(o is not None and o["perception_ok"] is True for o in observations)
                else False
                if any(o and o["perception_ok"] is False for o in observations)
                else None,
            }
    complete = all(r.status == "COMPLETED" for r in records)
    confidence = (
        "UNUSABLE"
        if any(r.confidence == "UNUSABLE" for r in records)
        else "LOW"
        if any(r.confidence == "LOW" for r in records)
        else records[0].confidence
    )
    target = records[0].target
    return EvaluationRecord(
        sample_id=item.sample.id,
        split=item.sample.split,
        task_type=item.sample.task_type,
        visual_family=records[0].visual_family,
        architecture=config.architecture,
        config_key=config.key,
        input_hash=sample_hash,
        image_hash=image_hash,
        cache_key=key,
        status="COMPLETED" if complete else "FAILED",
        target=target,
        predicted=scores,
        target_overall=overall_score(target),
        predicted_overall=overall_score(scores),
        confidence=confidence,
        perception=perception,
        specialist_status="COMPLETED"
        if all(r.specialist_status == "COMPLETED" for r in records)
        else next(
            (
                r.specialist_status
                for r in records
                if r.specialist_status not in (None, "COMPLETED")
            ),
            None,
        ),
        specialist_disagreements=sum(r.specialist_disagreements for r in records),
        decomposition=classify(
            "COMPLETED" if complete else "FAILED",
            confidence,
            perception,
            sum(r.specialist_disagreements for r in records),
            target,
            scores,
        ),
        wall_clock_seconds=time.perf_counter() - start,
        provider_calls=sum(r.provider_calls for r in records),
        token_usage=dict(sum((Counter(r.token_usage) for r in records), Counter())),
        specialist_calls=sum(r.specialist_calls for r in records),
        specialist_latency_seconds=sum(r.specialist_latency_seconds for r in records),
        failures={} if complete else {"run": "SELF_CONSISTENCY_REPEAT_FAILED"},
        repeats=[
            {
                "status": r.status,
                "predicted": {t: float(s) for t, s in r.predicted.items()},
                "perception": r.perception,
                "provider_calls": r.provider_calls,
                "token_usage": r.token_usage,
                "wall_clock_seconds": r.wall_clock_seconds,
                "confidence": r.confidence,
                "specialist_calls": r.specialist_calls,
            }
            for r in records
        ],
        repeat_spread={
            t: float(max(r.predicted[t] for r in records) - min(r.predicted[t] for r in records))
            for t in scores
        },
        repeat_variance={t: float(pvariance(r.predicted[t] for r in records)) for t in scores},
    )


async def run_benchmark(
    items,
    configs,
    output: Path,
    *,
    resume=False,
    dry_run=False,
    provider_factory=None,
    specialist_factory=None,
    settings=None,
    anchor_source=None,
):
    from app.evaluation.task1.report import build_report, write_report

    if not items or not configs or len({config.key for config in configs}) != len(configs):
        raise ValueError("BENCHMARK_CONFIGURATION_INVALID")
    anchor_source = anchor_source or AnchorSource()
    guard_leakage(items, anchor_source)
    if any(
        c.architecture == "anchor-pairwise" and c.anchor_digest != anchor_source.digest
        for c in configs
    ):
        raise ValueError("BENCHMARK_ANCHOR_IDENTITY_MISMATCH")
    explicit_settings = settings is not None
    if not dry_run and provider_factory is None and not explicit_settings:
        raise ValueError("BENCHMARK_RUNTIME_SETTINGS_REQUIRED")
    settings = settings if explicit_settings else Settings(_env_file=None)
    if not dry_run and explicit_settings:
        for config in configs:
            endpoint = (
                settings.ai_writing_vllm_base_url
                if config.provider == "vllm"
                else settings.ai_writing_openai_base_url
            )
            if provider_factory is None and digest(endpoint) != config.endpoint_hash:
                raise ValueError("BENCHMARK_RUNTIME_IDENTITY_MISMATCH")
            if (
                specialist_factory is None
                and config.specialist.enabled
                and digest(settings.ai_writing_deplot_base_url) != config.specialist_endpoint_hash
            ):
                raise ValueError("BENCHMARK_RUNTIME_IDENTITY_MISMATCH")

    def runtime_settings(config):
        return settings.model_copy(
            update={
                "ai_writing_provider": config.provider,
                "ai_writing_vllm_model": config.model,
                "ai_writing_openai_model": config.model,
                "ai_writing_chart_specialist_enabled": config.specialist.enabled,
                "ai_writing_chart_specialist_provider": config.specialist.provider,
                "ai_writing_deplot_model": config.specialist.model,
                "ai_writing_deplot_revision": config.specialist.revision,
                "ai_writing_request_timeout_seconds": config.request_timeout_seconds,
                "ai_writing_startup_timeout_seconds": config.startup_timeout_seconds,
                "ai_writing_chart_specialist_timeout_seconds": config.specialist_timeout_seconds,
            }
        )

    provider_factory = provider_factory or (
        lambda config: create_provider(runtime_settings(config))
    )
    specialist_factory = specialist_factory or (
        (lambda config: DePlotChartDerenderingProvider(runtime_settings(config)))
        if explicit_settings
        else (lambda _config: UnavailableSpecialist())
    )
    if dry_run:
        report = build_report([], configs, status="DRY_RUN")
        report["sample_count"] = len(items)
        report["plan"] = [
            {
                "sample_id": item.sample.id,
                "split": item.sample.split,
                "task_type": item.sample.task_type.value,
            }
            for item in items
        ]
        report["planned_scoring_runs"] = len(items) * len(configs)
        write_report(output, report)
        return report
    records = []
    try:
        for item in items:
            for config in configs:
                _sample_hash, _image_hash, key = fingerprint(item, config)
                path = output / "cache" / f"{key}.json"
                record = cached_record(path, key, config.key, item.sample.id) if resume else None
                if record is None:
                    record = await evaluate(
                        item, config, provider_factory, specialist_factory, anchor_source
                    )
                    save_attempt(output, record)
                    atomic_write(path, record.model_dump_json(indent=2))
                records.append(record)
    finally:
        # Completed samples survive interruption; --resume retries failures only.
        report = build_report(
            records,
            configs,
            attempts=attempt_history(output, records),
            status="COMPLETED" if len(records) == len(items) * len(configs) else "INTERRUPTED",
        )
        write_report(output, report)
    return report
