"""Sequential offline evaluation through current production Task 2 orchestration."""

import hashlib
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.core.config import Settings
from app.domains.scoring.mts_prompts import effective_prompt_version
from app.domains.scoring.writing import WritingScoringRequest
from app.evaluation.task2.models import TRAITS, BenchmarkConfig, EvaluationRecord, digest
from app.evaluation.writing import checkpoints
from app.evaluation.writing.metrics import overall_score
from app.evaluation.writing.runtime import CountedProvider, reconciled_usage
from app.providers.writing_llm import create_provider, provider_identity
from app.services.mts_writing import MTSWritingScoringService


def implementation_hash():
    root = Path(__file__).resolve().parents[2]
    patterns = (
        "domains/scoring/*.py",
        "domains/writing/*.py",
        "services/mts_writing.py",
        "services/writing_execution.py",
        "services/writing_relevance.py",
        "providers/writing_llm/*.py",
        "schemas/writing_ai.py",
        "evaluation/task2/*.py",
        "evaluation/writing/*.py",
        "core/config.py",
    )
    files = {path for pattern in patterns for path in root.glob(pattern)}
    return digest(
        {
            path.relative_to(root).as_posix(): hashlib.sha256(
                path.read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            for path in sorted(files)
        }
    )


def configuration(settings: Settings, max_concurrent_llm_requests=None):
    provider, model = provider_identity(settings)
    endpoint = (
        settings.ai_writing_vllm_base_url
        if provider == "vllm"
        else settings.ai_writing_openai_base_url
    )
    return BenchmarkConfig(
        label="task2-current",
        provider=provider,
        model=model,
        endpoint_hash=digest(endpoint),
        prompt_version=effective_prompt_version(settings.ai_writing_prompt_version),
        max_concurrent_llm_requests=max_concurrent_llm_requests
        if max_concurrent_llm_requests is not None
        else settings.ai_writing_max_concurrent_llm_requests,
        request_timeout_seconds=settings.ai_writing_request_timeout_seconds,
        startup_timeout_seconds=settings.ai_writing_startup_timeout_seconds,
        implementation_hash=implementation_hash(),
    )


def fingerprint(item, config):
    sample_hash = digest(item.sample.model_dump(mode="json"))
    return sample_hash, digest({"sample": sample_hash, "config": config.key})


async def evaluate(item, config, provider_factory):
    started = time.perf_counter()
    input_hash, cache_key = fingerprint(item, config)
    sample = item.sample
    predicted, failures = {}, {}
    provider = scorer = None

    async def trace(event, payload):
        trait = "tr" if payload.criterion == "ta" else payload.criterion
        if event == "criterion.completed":
            predicted[trait] = payload.result.score
        elif event == "criterion.failed":
            failures[trait] = "CRITERION_FAILED"

    try:
        provider = CountedProvider(provider_factory(config))
        scorer = MTSWritingScoringService(
            provider,
            max_concurrent_requests=config.max_concurrent_llm_requests,
            relevance_enabled=config.relevance_enabled,
        )
        await provider.ensure_ready()
        request = WritingScoringRequest(
            attempt_id=uuid5(NAMESPACE_URL, f"benchmark:{sample.id}"),
            writing_task_id=uuid5(NAMESPACE_URL, f"benchmark-task:{sample.id}"),
            prompt=sample.prompt,
            response=sample.essay,
            paragraph_mode=config.paragraph_mode,
        )
        result = await scorer.assess(request, trace)
        status = (
            "COMPLETED"
            if result is not None and set(predicted) == set(TRAITS) and not failures
            else "FAILED"
        )
        if status == "FAILED" and not failures:
            failures["run"] = "BENCHMARK_SAMPLE_FAILED"
    except Exception:
        status = "FAILED"
        failures["run"] = "BENCHMARK_SAMPLE_FAILED"
    target = sample.human_scores.scores()
    return EvaluationRecord(
        sample_id=sample.id,
        split=sample.split,
        config_key=config.key,
        input_hash=input_hash,
        cache_key=cache_key,
        status=status,
        target=target,
        predicted=predicted,
        target_overall=overall_score(target, traits=TRAITS),
        predicted_overall=overall_score(predicted, traits=TRAITS),
        wall_clock_seconds=time.perf_counter() - started,
        provider_calls=provider.calls if provider else 0,
        token_usage=reconciled_usage(provider, scorer) if provider else {},
        failures=failures,
    )


async def run_benchmark(
    items,
    config,
    output: Path,
    *,
    resume=False,
    dry_run=False,
    provider_factory=None,
    settings=None,
):
    from app.evaluation.task2.report import build_report, write_report

    if not items:
        raise ValueError("BENCHMARK_CONFIGURATION_INVALID")
    if not dry_run and provider_factory is None and settings is None:
        raise ValueError("BENCHMARK_RUNTIME_SETTINGS_REQUIRED")
    if settings is not None and provider_factory is None and not dry_run:
        expected = configuration(settings, config.max_concurrent_llm_requests)
        if any(
            getattr(expected, field) != getattr(config, field)
            for field in ("provider", "model", "endpoint_hash", "prompt_version")
        ):
            raise ValueError("BENCHMARK_RUNTIME_IDENTITY_MISMATCH")

    def runtime(cfg):
        return settings.model_copy(
            update={
                "ai_writing_provider": cfg.provider,
                "ai_writing_vllm_model": cfg.model,
                "ai_writing_openai_model": cfg.model,
                "ai_writing_request_timeout_seconds": cfg.request_timeout_seconds,
                "ai_writing_startup_timeout_seconds": cfg.startup_timeout_seconds,
            }
        )

    factory = provider_factory or (lambda cfg: create_provider(runtime(cfg)))
    if dry_run:
        report = build_report([], config, status="DRY_RUN")
        report.update(
            sample_count=len(items),
            planned_scoring_runs=len(items),
            plan=[{"sample_id": item.sample.id, "split": item.sample.split} for item in items],
        )
        write_report(output, report)
        return report
    records = []
    try:
        for item in items:
            _, key = fingerprint(item, config)
            path = output / "cache" / f"{key}.json"
            record = (
                checkpoints.cached_record(
                    path, key, config.key, item.sample.id, record_type=EvaluationRecord
                )
                if resume
                else None
            )
            if record is None:
                record = await evaluate(item, config, factory)
                checkpoints.save_attempt(output, record)
                checkpoints.atomic_write(path, record.model_dump_json(indent=2))
            records.append(record)
    finally:
        report = build_report(
            records,
            config,
            attempts=checkpoints.attempt_history(output, records, record_type=EvaluationRecord),
            status="COMPLETED" if len(records) == len(items) else "INTERRUPTED",
        )
        write_report(output, report)
    return report
