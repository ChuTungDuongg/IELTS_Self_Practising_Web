"""Run-local concurrency and bounded, content-free monotonic timings."""

import asyncio
import logging
from collections.abc import Awaitable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter

from app.providers.writing_llm.base import LLMProvider, safe_finish_reason
from app.schemas.writing_ai import (
    AssessmentStage,
    CriterionFailure,
    CriterionResult,
    OutputDiagnostic,
    Trait,
)

logger = logging.getLogger(__name__)


@dataclass
class CriterionExecutionState:
    trait: Trait
    stage: AssessmentStage = "evidence"
    usage: list[dict[str, int]] = field(default_factory=list)
    diagnostics: list[OutputDiagnostic] = field(default_factory=list)
    failure: CriterionFailure | None = None
    result: CriterionResult | None = None


class TraceFailure(Exception):
    """Persistence/stop errors are run failures, never criterion output failures."""


async def durable_checkpoint[T](work: Awaitable[T]) -> T:
    """Finish a short DB transaction before propagating cancellation to its caller."""
    task = asyncio.ensure_future(work)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise


class WritingLatencyMetrics:
    """Only fixed stage identifiers, numbers and allowlisted finish reasons are retained."""

    STAGES = frozenset(
        {
            "provider_ready",
            "evidence",
            "scoring",
            "visual_grounding",
            "chart_specialist",
            "chart_reconciliation",
            "derived_facts",
            "claim_extraction",
            "claim_verification",
        }
    )

    def __init__(self):
        self.started = perf_counter()
        self.finished: float | None = None
        self.first_completed_ms: float | None = None
        self.stages: dict[str, dict] = {}

    def key(self, stage: str, trait: Trait | None):
        if stage not in self.STAGES:
            raise ValueError("Invalid latency stage")
        return f"{trait}.{stage}" if trait and stage in {"evidence", "scoring"} else stage

    @contextmanager
    def stage(self, stage: str, trait: Trait | None = None) -> Iterator[None]:
        key = self.key(stage, trait)
        started = perf_counter()
        try:
            yield
        finally:
            duration = round((perf_counter() - started) * 1000, 3)
            self.stages.setdefault(key, {})["duration_ms"] = duration
            logger.info("AI latency: stage=%s criterion=%s duration_ms=%s", stage, trait, duration)

    @contextmanager
    def attempt(self, stage: str, trait: Trait, attempt: int) -> Iterator[dict]:
        key = self.key(stage, trait)
        started = perf_counter()
        # Callers can only supply finish_reason and usage through completion().
        record = {"attempt": attempt, "finish_reason": "missing"}
        try:
            yield record
        finally:
            record["duration_ms"] = round((perf_counter() - started) * 1000, 3)
            records = self.stages.setdefault(key, {}).setdefault("attempts", [])
            if len(records) < 2:
                records.append(record)
            logger.info(
                "AI latency: stage=%s criterion=%s duration_ms=%s attempt=%s finish_reason=%s prompt_tokens=%s completion_tokens=%s",
                stage,
                trait,
                record["duration_ms"],
                attempt,
                record["finish_reason"],
                record.get("prompt_tokens"),
                record.get("completion_tokens"),
            )

    @staticmethod
    def completion(record: dict, finish_reason: object, usage: dict):
        record["finish_reason"] = safe_finish_reason(finish_reason)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if type(value) is int and 0 <= value <= 1_000_000_000:
                record[key] = value

    def completed_criterion(self):
        if self.first_completed_ms is None:
            self.first_completed_ms = round((perf_counter() - self.started) * 1000, 3)

    def finish(self):
        if self.finished is None:
            self.finished = perf_counter()
            logger.info(
                "AI latency: stage=run_total duration_ms=%s time_to_first_criterion_ms=%s",
                self.summary()["run_total_ms"],
                self.first_completed_ms,
            )

    def summary(self) -> dict:
        # Copy nested records: queued DB checkpoints must not retain mutable metrics.
        return {
            "run_total_ms": round(((self.finished or perf_counter()) - self.started) * 1000, 3),
            "provider_ready_ms": self.stages.get("provider_ready", {}).get("duration_ms"),
            "time_to_first_criterion_ms": self.first_completed_ms,
            "stages": {
                key: {
                    **value,
                    **(
                        {"attempts": [dict(item) for item in value["attempts"]]}
                        if "attempts" in value
                        else {}
                    ),
                }
                for key, value in sorted(self.stages.items())
            },
        }


class BoundedWritingProvider:
    """One limiter per run, shared by vision, claims, evidence, scoring and repairs."""

    def __init__(self, provider: LLMProvider, limit: int):
        if type(limit) is not int or not 1 <= limit <= 4:
            raise ValueError("Writing LLM concurrency must be between 1 and 4")
        self.provider = provider
        self.limit = limit
        self.semaphore = asyncio.Semaphore(limit)
        self.active = self.peak_active = 0

    async def ensure_ready(self):
        await self.provider.ensure_ready()

    async def complete(self, messages, schema, *, options=None):
        async with self.semaphore:
            self.active += 1
            self.peak_active = max(self.peak_active, self.active)
            try:
                return await self.provider.complete(messages, schema, options=options)
            finally:
                self.active -= 1


async def gather_isolated[T](*work: Awaitable[T]) -> list[T]:
    """Wait for siblings on ordinary errors; external cancellation drains every child."""
    tasks = [asyncio.ensure_future(item) for item in work]
    try:
        pending = set(tasks)
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.cancelled():
                    raise asyncio.CancelledError
                if isinstance(task.exception(), TraceFailure):
                    raise task.exception()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return results
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
