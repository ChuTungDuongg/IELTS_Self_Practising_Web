"""DEV wiring only: synthetic bands do not establish IELTS scoring accuracy."""

import pytest
from test_openai_task1_assessment import SourceImageProvider, envelope, images, payload
from test_task1_visual import request

from app.core.config import Settings
from app.evaluation.task1.evidence_ablation import SourceIdsOnlyTask1Scorer, evidence_configurations
from app.evaluation.task1.manifest import LoadedSample
from app.evaluation.task1.models import BenchmarkSample
from app.evaluation.task1.runner import evaluate, fingerprint, run_benchmark
from app.services.task1_writing import Task1WritingScoringService


def settings():
    return Settings(
        _env_file=None, ai_writing_provider="openai", ai_writing_openai_model="gpt-6-luna"
    )


def sample():
    req = request()
    return LoadedSample(
        BenchmarkSample(
            schema_version=1,
            id="DEV-CONTRACT",
            split="dev",
            task_type=req.task_type,
            prompt=req.prompt,
            essay=req.response,
            image_path="unused.png",
            human_scores={"ta": 8, "cc": 7, "lr": 7, "gra": 7},
            provenance="Fictional contract labels, not human calibration",
            redistributable=True,
        ),
        req.image,
    )


@pytest.mark.parametrize("band", [4, 7, 8])
async def test_evidence_arms_only_remove_ta_selector_assessments_and_keep_image_and_full_context(
    band,
):
    configs = evidence_configurations(settings())
    providers = [
        SourceImageProvider([envelope(score=band)]),
        SourceImageProvider([envelope(score=band)]),
    ]
    results = []

    async def trace(*_args):
        pass

    for scorer_type, provider in zip(
        (Task1WritingScoringService, SourceIdsOnlyTask1Scorer), providers, strict=True
    ):
        results.append(await scorer_type(provider).assess(request(), trace))
    assert all(result is not None for result in results)
    scoring = [
        next(
            messages
            for messages, _, options in provider.records
            if options.stage == "score" and options.criterion == "ta"
        )
        for provider in providers
    ]
    baseline, candidate = map(payload, scoring)
    assert baseline["evidence"] and any("assessment" in item for item in baseline["evidence"])
    assert candidate["evidence"] == [
        {"source_id": item["source_id"]} for item in baseline["evidence"]
    ]
    baseline.pop("evidence")
    candidate.pop("evidence")
    assert baseline == candidate
    assert (
        baseline["segmented_essay"] and baseline["derived_facts"] and baseline["claim_verification"]
    )
    assert images(scoring[0]) == images(scoring[1]) == [sample().image]
    assert scoring[0][0] == scoring[1][0]  # Rubric/system instructions identical.
    for stage in ("evidence", "feedback"):
        left = [messages for messages, _, options in providers[0].records if options.stage == stage]
        right = [
            messages for messages, _, options in providers[1].records if options.stage == stage
        ]
        assert left == right
    for trait in ("cc", "lr", "gra"):
        left = [
            messages for messages, _, options in providers[0].records if options.criterion == trait
        ]
        right = [
            messages for messages, _, options in providers[1].records if options.criterion == trait
        ]
        assert left == right
    for provider in providers:
        assert all(
            "human_scores" not in str(messages) and "DEV-CONTRACT" not in str(messages)
            for messages, _, _ in provider.records
        )
    assert results[0].criteria.ta.score == results[1].criteria.ta.score == band
    assert fingerprint(sample(), configs[0])[2] != fingerprint(sample(), configs[1])[2]


async def test_evidence_comparison_plans_paired_dev_metrics_but_blocks_live_and_holdout(tmp_path):
    configs = evidence_configurations(settings())
    assert configs[0].key != configs[1].key
    assert configs[0].openai_inference == configs[1].openai_inference
    report = await run_benchmark([sample()], configs, tmp_path / "plan", dry_run=True)
    assert report["evaluated_run_count"] == 0
    assert report["planned_scoring_runs"] == 2
    assert report["ablations"][0]["kind"] == "ta_evidence"
    assert report["ablations"][0]["paired_sample_count"] == 0
    with pytest.raises(ValueError, match="BENCHMARK_ABLATION_LIVE_DISABLED"):
        await run_benchmark([sample()], configs, tmp_path / "live")
    with pytest.raises(ValueError, match="BENCHMARK_ABLATION_LIVE_DISABLED"):
        await run_benchmark(
            [sample()],
            configs,
            tmp_path / "injected",
            provider_factory=lambda _: pytest.fail(
                "Must not instantiate even an injected provider"
            ),
        )
    holdout = sample()
    holdout.sample.split = "holdout"
    with pytest.raises(ValueError, match="BENCHMARK_ABLATION_DEV_ONLY"):
        await run_benchmark([holdout], configs, tmp_path / "holdout", dry_run=True)
    with pytest.raises(ValueError, match="BENCHMARK_ABLATION_DEV_ONLY"):
        await evaluate(
            holdout, configs[1], lambda _: pytest.fail("No HOLDOUT inference"), lambda _: None
        )
    with pytest.raises(ValueError, match="BENCHMARK_ABLATION_LIVE_DISABLED"):
        await evaluate(
            sample(), configs[1], lambda _: pytest.fail("No live inference"), lambda _: None
        )


def test_evidence_ablation_rejects_non_source_image_profiles():
    with pytest.raises(ValueError, match="SOURCE_IMAGE"):
        evidence_configurations(
            settings().model_copy(update={"ai_writing_openai_task1_image_assessment": False})
        )
    with pytest.raises(ValueError, match="LUNA"):
        evidence_configurations(Settings(_env_file=None, ai_writing_provider="vllm"))
