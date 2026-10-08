"""Offline orchestration comparison: fixed fake completions, identical current prompts.

Sequential references reproduce the old dependency graph; production never selects them.
This is not an LLM quality or GPU throughput benchmark.
"""

import asyncio
import base64
import json
import platform
from pathlib import Path
from statistics import median
from uuid import uuid4

from app.domains.scoring.deplot_parser import parse_deplot
from app.domains.scoring.essay_sources import segment_essay
from app.domains.scoring.mts_prompts import (
    AI_WRITING_PROMPT_VERSION,
    TRAIT_NAMES,
    evidence_messages,
    scoring_messages,
)
from app.domains.scoring.writing import WritingScoringRequest
from app.domains.writing.task_types import WritingTaskType
from app.providers.writing_llm.base import Completion, ImagePart
from app.schemas.chart_cross_check import ChartSpecialistIdentity
from app.schemas.task1_claims import Task1Analysis
from app.schemas.writing_ai import TRAITS
from app.services.mts_writing import MTSWritingScoringService
from app.services.task1_chart_cross_check import (
    apply_chart_cross_check,
    extract_chart,
    specialist_eligible,
)
from app.services.task1_input import (
    TASK1_SCORING_PROMPT_VERSION,
    TASK1_VISUAL_CONTRACT_VERSION,
    Task1ScoringRequest,
)
from app.services.task1_writing import Task1WritingScoringService
from app.services.writing_execution import WritingLatencyMetrics

ROOT = Path(__file__).resolve().parents[3]


def load_fixture():
    return json.loads(
        (ROOT / "benchmarks/writing_latency/synthetic.json").read_text(encoding="utf-8")
    )


def call_identity(messages, schema):
    properties = schema["properties"]
    if "reference" in properties:
        return "visual_grounding", "ta"
    if "claims" in properties:
        return "claim_extraction", "ta"
    if "items" in properties:
        return "claim_verification", "ta"
    system = messages[0]["content"]
    trait = next(
        trait
        for trait in TRAITS
        if (
            "Task Achievement"
            if trait == "ta" and "Academic Writing Task 1" in system
            else TRAIT_NAMES[trait]
        )
        in system
    )
    return ("evidence" if "evidence" in properties else "scoring"), trait


class FakeLatencyProvider:
    def __init__(self, fixture, delay_seconds=0.1):
        self.fixture, self.delay_seconds = fixture, delay_seconds
        self.calls = []
        self.active = self.peak_active = 0

    async def ensure_ready(self):
        await asyncio.sleep(self.delay_seconds)

    async def complete(self, messages, schema, *, options=None):
        stage, trait = call_identity(messages, schema)
        self.calls.append((stage, trait, messages, schema, options))
        self.active += 1
        self.peak_active = max(self.active, self.peak_active)
        try:
            await asyncio.sleep(self.delay_seconds)
            key = {
                "visual_grounding": "grounding",
                "claim_extraction": "claims",
                "claim_verification": "verification",
                "scoring": "score",
            }.get(stage, stage)
            return Completion(
                json.dumps(self.fixture[key], ensure_ascii=False),
                dict(self.fixture["usage_per_call"]),
            )
        finally:
            self.active -= 1


class FakeLatencySpecialist:
    def __init__(self, fixture, delay_seconds=0.1):
        self.fixture, self.delay_seconds, self.calls = fixture, delay_seconds, 0

    async def extract(self, image):
        self.calls += 1
        await asyncio.sleep(self.delay_seconds)
        return parse_deplot(self.fixture["deplot"])


class SequentialTask2Reference(MTSWritingScoringService):
    async def assess(self, request, trace):
        self._start_assessment()
        trace = self.protected_trace(trace)
        segments = segment_essay(request.response)
        for trait in TRAITS:
            await self._run_criterion(
                request,
                trait,
                trace,
                evidence_messages(request.prompt, request.response, trait, segments),
                lambda evidence, trait=trait: scoring_messages(
                    request.prompt, request.response, trait, evidence, segments
                ),
            )
        return self._task2_result()


class SequentialTask1Reference(Task1WritingScoringService):
    async def assess(self, request, trace):
        self._start_assessment()
        trace = self.protected_trace(trace)
        analysis = Task1Analysis(visual_family="chart_table")
        grounding, claims = self._analysis_services()
        await self._ground(request, analysis, grounding, trace)
        if analysis.confidence != "UNUSABLE":
            if specialist_eligible(request):
                extracted = await extract_chart(
                    request, self.chart_derenderer, trace, self.chart_timeout, self.latency
                )
                await apply_chart_cross_check(request, analysis, extracted, trace, self.latency)
            await self._derive_facts(analysis, trace)
            extracted = await self._extract_claims(request, claims, trace, analysis)
            if extracted is not None:
                await self._verify_claims(request, extracted, analysis, claims, trace)
        for trait in TRAITS:
            await self._task1_criterion(request, trait, analysis, trace)
        return self._task1_result(analysis)


def synthetic_request(task_number, fixture, specialist_enabled=False):
    values = {**fixture[f"task{task_number}"], "attempt_id": uuid4(), "writing_task_id": uuid4()}
    if task_number == 2:
        return WritingScoringRequest(**values)
    return Task1ScoringRequest(
        **values,
        task_type=WritingTaskType.LINE_GRAPH,
        image=ImagePart("image/png", base64.b64decode(fixture["image_base64"])),
        chart_specialist=ChartSpecialistIdentity(enabled=specialist_enabled),
    )


async def fake_comparison(repeats=3, delay_ms=100):
    fixture = load_fixture()
    rows = []
    for task_number, enabled in ((2, False), (1, False), (1, True)):
        reference_result, reference_calls = None, None
        for mode, limit in (
            ("sequential", 1),
            ("concurrent", 1),
            ("concurrent", 2),
            ("concurrent", 4),
        ):
            samples, first, total_tokens, prompt_tokens, completion_tokens = [], [], [], [], []
            readiness, stages = [], {}
            for _ in range(repeats):
                metrics = WritingLatencyMetrics()
                provider = FakeLatencyProvider(fixture, delay_ms / 1000)
                specialist = FakeLatencySpecialist(fixture, delay_ms / 1000)
                service_type = (
                    (SequentialTask2Reference if mode == "sequential" else MTSWritingScoringService)
                    if task_number == 2
                    else (
                        SequentialTask1Reference
                        if mode == "sequential"
                        else Task1WritingScoringService
                    )
                )
                kwargs = {"max_concurrent_requests": limit, "latency": metrics}
                if task_number == 1:
                    kwargs["chart_derenderer"] = specialist if enabled else None
                service = service_type(provider, **kwargs)
                with metrics.stage("provider_ready"):
                    await service.provider.ensure_ready()

                async def trace(event, payload):
                    pass

                result = await service.assess(
                    synthetic_request(task_number, fixture, enabled), trace
                )
                metrics.finish()
                serialized = result.model_dump(mode="json")
                calls = sorted(provider.calls, key=lambda call: (call[0], call[1]))
                if reference_result is None:
                    reference_result, reference_calls = serialized, calls
                if serialized != reference_result or calls != reference_calls:
                    raise AssertionError(
                        "Orchestration changed fixed outputs or prompt/schema/budget requests"
                    )
                summary = service.latency_summary()
                samples.append(summary["run_total_ms"])
                first.append(summary["time_to_first_criterion_ms"])
                readiness.append(summary["provider_ready_ms"])
                for stage, value in summary["stages"].items():
                    stages.setdefault(stage, []).append(value["duration_ms"])
                total_tokens.append(sum(call["total_tokens"] for call in service.usage))
                prompt_tokens.append(sum(call["prompt_tokens"] for call in service.usage))
                completion_tokens.append(sum(call["completion_tokens"] for call in service.usage))
            rows.append(
                {
                    "task_number": task_number,
                    "specialist_enabled": enabled,
                    "mode": mode,
                    "limit": limit,
                    "median_total_ms": round(median(samples), 3),
                    "median_first_criterion_ms": round(median(first), 3),
                    "median_provider_ready_ms": round(median(readiness), 3),
                    "median_stage_ms": {
                        stage: round(median(values), 3) for stage, values in stages.items()
                    },
                    "llm_calls": len(provider.calls),
                    "specialist_calls": specialist.calls,
                    "prompt_tokens": median(prompt_tokens),
                    "completion_tokens": median(completion_tokens),
                    "total_tokens": median(total_tokens),
                    "peak_active_llm_requests": provider.peak_active,
                    "equivalent_outputs_and_requests": True,
                    "samples_ms": samples,
                    "first_criterion_samples_ms": first,
                }
            )
    return {
        "mode": "synthetic-fake",
        "network_calls": False,
        "repeats": repeats,
        "delay_ms": delay_ms,
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "prompt_versions": {
            "task1_scoring": TASK1_SCORING_PROMPT_VERSION,
            "task1_visual": TASK1_VISUAL_CONTRACT_VERSION,
            "task2": AI_WRITING_PROMPT_VERSION,
        },
        "rows": rows,
    }
