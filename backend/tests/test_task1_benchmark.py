"""Fictional samples and fake providers exercise evaluation, never real inference."""

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from test_chart_cross_check import FakeSpecialist
from test_task1_grounding_regression import PieProvider

from app.core.config import Settings
from app.evaluation.task1.manifest import BenchmarkInputError, load_manifest
from app.evaluation.task1.models import EvaluationRecord
from app.evaluation.task1.report import build_report
from app.evaluation.task1.runner import configurations, implementation_hash, run_benchmark
from app.schemas.chart_cross_check import ChartSpecialistIdentity

MATRIX = Path(__file__).parent / "fixtures" / "synthetic_six_region_pie_matrix.json"


@pytest.fixture
def benchmark_files(tmp_path):
    (tmp_path / "visual.png").write_bytes(b"\x89PNG\r\n\x1a\nfictional-test-image")
    sample = {
        "schema_version": 1,
        "id": "fictional-001",
        "split": "dev",
        "task_type": "PIE_CHART",
        "prompt": "Compare fictional water use in six imaginary regions.",
        "image_path": "visual.png",
        "essay": "PRIVATE SYNTHETIC ESSAY. The six regions use water differently.",
        "human_scores": {"ta": 5.5, "cc": 5.5, "lr": 5.5, "gra": 5.5},
        "raters": 1,
        "provenance": "Synthetic test labels only; not measured human calibration.",
        "redistributable": False,
        "visual_truth": json.loads(MATRIX.read_text(encoding="utf-8"))["reference"],
    }
    path = tmp_path / "manifest.jsonl"
    path.write_text(json.dumps(sample) + "\n", encoding="utf-8")
    return path, sample


def test_manifest_filters_splits_and_supports_external_nonredistributable_paths(benchmark_files):
    path, sample = benchmark_files
    holdout = {**sample, "id": "fictional-holdout", "split": "holdout"}
    path.write_text(json.dumps(sample) + "\n" + json.dumps(holdout) + "\n", encoding="utf-8")
    assert [item.sample.id for item in load_manifest(path, "dev")] == ["fictional-001"]
    assert [item.sample.id for item in load_manifest(path, "holdout")] == ["fictional-holdout"]
    assert load_manifest(path, "dev", limit=1)[0].image.data.startswith(b"\x89PNG")
    assert not load_manifest(path, "dev")[0].sample.redistributable


@pytest.mark.parametrize(
    "failure", ["targets", "halfband", "task_type", "image_url", "duplicate", "truth_family"]
)
def test_invalid_manifest_has_safe_diagnostics(benchmark_files, failure):
    path, sample = benchmark_files
    if failure == "targets":
        del sample["human_scores"]
    elif failure == "halfband":
        sample["human_scores"]["gra"] = 5.2
    elif failure == "task_type":
        sample["task_type"] = "OPINION"
    elif failure == "image_url":
        sample["image_path"] = "https://private.example/image.png?token=SECRET"
    elif failure == "truth_family":
        sample["task_type"] = "PROCESS"
    path.write_text(
        json.dumps(sample) + "\n" * 1 + (json.dumps(sample) if failure == "duplicate" else ""),
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkInputError) as error:
        load_manifest(path, "dev")
    assert "PRIVATE" not in str(error.value) and "SECRET" not in str(error.value)


def test_configuration_identity_separates_prompt_and_specialist_versions():
    configs = configurations(Settings(_env_file=None), "both", "both")
    assert len(configs) == 4 and len({config.key for config in configs}) == 4
    assert {config.scoring_version for config in configs} == {"v3", "v4"}
    assert all(config.visual_contract_version == "mts-task1-visual-v3" for config in configs)
    assert all("SECRET" not in config.model_dump_json() for config in configs)


async def test_dry_run_does_not_create_providers_or_upload_content(benchmark_files, tmp_path):
    path, sample = benchmark_files

    def forbidden(_config):
        pytest.fail("dry-run attempted a provider")

    report = await run_benchmark(
        load_manifest(path, "dev"),
        configurations(Settings(_env_file=None), "v4", "off"),
        tmp_path / "report",
        dry_run=True,
        provider_factory=forbidden,
    )
    assert report["status"] == "DRY_RUN" and report["sample_count"] == 1
    assert sample["essay"] not in json.dumps(report)
    assert "PRIVATE SYNTHETIC" not in (tmp_path / "report" / "report.json").read_text()


async def test_four_real_service_ablations_are_independent_and_targets_never_reach_provider(
    benchmark_files, tmp_path, caplog
):
    path, sample = benchmark_files
    providers = []

    def factory(config):
        provider = PieProvider(json.loads(MATRIX.read_text(encoding="utf-8")))
        providers.append(provider)
        return provider

    report = await run_benchmark(
        load_manifest(path, "dev"),
        configurations(Settings(_env_file=None), "both", "both"),
        tmp_path / "report",
        provider_factory=factory,
        specialist_factory=lambda _config: FakeSpecialist(
            "Region | Agriculture (%) | Industry (%) | Domestic (%)\nRegion A | 55 | 30 | 15\nRegion B | 45 | 35 | 20\nRegion C | 70 | 20 | 10\nRegion D | 40 | 45 | 15\nRegion E | 60 | 25 | 15\nRegion F | 50 | 20 | 30"
        ),
    )
    assert len(report["configurations"]) == 4 and len(report["records"]) == 4
    assert len(providers) == 4 and all(provider.image_calls == 1 for provider in providers)
    assert all(record["status"] == "COMPLETED" for record in report["records"])
    assert all(record["perception"]["primary"]["perception_ok"] for record in report["records"])
    assert all(
        record["decomposition"] == "PERCEPTION_OK_SCORE_HIGH" for record in report["records"]
    )
    assert len(report["ablations"]) == 4
    assert "PRIVATE SYNTHETIC" not in json.dumps(report) + caplog.text
    for provider in providers:
        for messages in provider.calls:
            assert "human_scores" not in str(messages) and sample["provenance"] not in str(messages)
    assert (tmp_path / "report" / "report.md").is_file()
    assert (tmp_path / "report" / "disagreements.csv").is_file()


async def test_resume_reuses_success_but_invalidates_content_and_config(benchmark_files, tmp_path):
    path, sample = benchmark_files
    calls = []

    def factory(config):
        calls.append(config.key)
        return PieProvider(json.loads(MATRIX.read_text(encoding="utf-8")))

    configs = configurations(Settings(_env_file=None), "v4", "off")
    output = tmp_path / "report"
    await run_benchmark(load_manifest(path, "dev"), configs, output, provider_factory=factory)
    report = await run_benchmark(
        load_manifest(path, "dev"), configs, output, resume=True, provider_factory=factory
    )
    assert len(calls) == 1 and report["records"][0]["cache_hit"]
    sample["essay"] += " An original extra sentence."
    path.write_text(json.dumps(sample), encoding="utf-8")
    await run_benchmark(
        load_manifest(path, "dev"), configs, output, resume=True, provider_factory=factory
    )
    assert len(calls) == 2
    changed = configs[0].model_copy(
        update={"specialist": ChartSpecialistIdentity(enabled=True, revision="other-revision")}
    )
    await run_benchmark(
        load_manifest(path, "dev"), [changed], output, resume=True, provider_factory=factory
    )
    assert len(calls) == 3


async def test_resume_invalidates_image_provider_model_and_recovers_corrupt_cache(
    benchmark_files, tmp_path
):
    path, _sample = benchmark_files
    calls = []

    def factory(config):
        calls.append(config.key)
        return PieProvider(json.loads(MATRIX.read_text(encoding="utf-8")))

    config = configurations(Settings(_env_file=None), "v4", "off")[0]
    output = tmp_path / "report"
    first = await run_benchmark(
        load_manifest(path, "dev"), [config], output, provider_factory=factory
    )
    cache = output / "cache" / (first["records"][0]["cache_key"] + ".json")
    cache.write_text("corrupt private data", encoding="utf-8")
    await run_benchmark(
        load_manifest(path, "dev"), [config], output, resume=True, provider_factory=factory
    )
    assert len(calls) == 1
    (path.parent / "visual.png").write_bytes(b"\x89PNG\r\n\x1a\ndifferent-test-image")
    await run_benchmark(
        load_manifest(path, "dev"), [config], output, resume=True, provider_factory=factory
    )
    assert len(calls) == 2
    changed = config.model_copy(update={"model": "fictional-other-model"})
    await run_benchmark(
        load_manifest(path, "dev"), [changed], output, resume=True, provider_factory=factory
    )
    assert len(calls) == 3


async def test_interruption_keeps_completed_checkpoints_and_resume_retries_failures(
    benchmark_files, tmp_path
):
    path, _sample = benchmark_files
    items = load_manifest(path, "dev")
    configs = configurations(Settings(_env_file=None), "v4", "both")
    calls = []

    def interrupted(config):
        calls.append(config.key)
        if len(calls) == 2:
            raise KeyboardInterrupt()
        return PieProvider(json.loads(MATRIX.read_text(encoding="utf-8")))

    output = tmp_path / "report"
    with pytest.raises(KeyboardInterrupt):
        await run_benchmark(items, configs, output, provider_factory=interrupted)
    assert json.loads((output / "report.json").read_text())["status"] == "INTERRUPTED"
    report = await run_benchmark(items, configs, output, resume=True, provider_factory=interrupted)
    assert len(calls) == 3 and report["records"][0]["cache_hit"]
    # Missing specialist fails open and does not invalidate the primary run.
    assert report["records"][1]["status"] == "COMPLETED"


def test_cli_dry_run_and_rejected_input_are_content_safe(benchmark_files, tmp_path):
    path, sample = benchmark_files
    script = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_task1.py"
    command = [
        sys.executable,
        str(script),
        "--manifest",
        str(path),
        "--split",
        "dev",
        "--dry-run",
        "--output",
        str(tmp_path / "cli"),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0 and "DRY_RUN: samples=1 runs=0 failed=0" in result.stdout
    assert sample["essay"] not in result.stdout + result.stderr
    del sample["human_scores"]
    path.write_text(json.dumps(sample), encoding="utf-8")
    invalid = subprocess.run(command, capture_output=True, text=True, check=False)
    assert invalid.returncode == 2 and "BENCHMARK_SAMPLE_INVALID:line=1" in invalid.stderr
    assert "PRIVATE" not in invalid.stdout + invalid.stderr


async def test_partial_scores_remain_evaluable_after_primary_failure(benchmark_files, tmp_path):
    path, _sample = benchmark_files
    provider = PieProvider({"invalid": "PRIVATE RAW PAYLOAD"})
    report = await run_benchmark(
        load_manifest(path, "dev"),
        configurations(Settings(_env_file=None), "v4", "off"),
        tmp_path / "report",
        provider_factory=lambda _config: provider,
    )
    record = report["records"][0]
    assert record["status"] == "FAILED" and record["decomposition"] == "UNUSABLE"
    assert set(record["predicted"]) == {"cc", "lr", "gra"}
    metrics = next(iter(report["configurations"].values()))["metrics"]
    assert metrics["ta"]["count"] == 0 and metrics["gra"]["count"] == 1
    assert "PRIVATE RAW PAYLOAD" not in json.dumps(report)


async def test_resume_preserves_failed_attempt_history_and_total_cost(benchmark_files, tmp_path):
    path, _sample = benchmark_files
    configs = configurations(Settings(_env_file=None), "v4", "off")
    output = tmp_path / "report"
    first = await run_benchmark(
        load_manifest(path, "dev"),
        configs,
        output,
        provider_factory=lambda _config: PieProvider({"invalid": "PRIVATE PAYLOAD"}),
    )
    retried = await run_benchmark(
        load_manifest(path, "dev"),
        configs,
        output,
        resume=True,
        provider_factory=lambda _config: PieProvider(
            json.loads(MATRIX.read_text(encoding="utf-8"))
        ),
    )
    history = retried["operational"]
    assert history["attempt_count"] == 2 and history["failed_attempt_count"] == 1
    assert history["attempt_failure_rate"] == 0.5 and history["initial_failure_rate"] == 1
    assert (
        history["provider_calls"]
        == first["records"][0]["provider_calls"] + retried["records"][0]["provider_calls"]
    )
    assert retried["records"][0]["status"] == "COMPLETED"
    assert [attempt["status"] for attempt in retried["attempt_history"]] == ["FAILED", "COMPLETED"]
    assert "PRIVATE PAYLOAD" not in json.dumps(retried)


@pytest.mark.parametrize(
    "corruption", ["missing_gra", "wrong_overall", "missing_target", "wrong_target_overall"]
)
async def test_inconsistent_completed_cache_is_rejected(benchmark_files, tmp_path, corruption):
    path, _sample = benchmark_files
    configs = configurations(Settings(_env_file=None), "v4", "off")
    calls = []

    def factory(_config):
        calls.append(True)
        return PieProvider(json.loads(MATRIX.read_text(encoding="utf-8")))

    output = tmp_path / "report"
    first = await run_benchmark(
        load_manifest(path, "dev"), configs, output, provider_factory=factory
    )
    entry = first["records"][0]
    if corruption == "missing_gra":
        del entry["predicted"]["gra"]
    elif corruption == "missing_target":
        del entry["target"]["ta"]
    elif corruption == "wrong_target_overall":
        entry["target_overall"] = 9
    else:
        entry["predicted_overall"] = 9
    attempt_path = output / "attempts" / entry["cache_key"] / "000001.json"
    attempt_path.write_text(json.dumps(entry), encoding="utf-8")
    result = await run_benchmark(
        load_manifest(path, "dev"), configs, output, resume=True, provider_factory=factory
    )
    assert len(calls) == 2 and not result["records"][0]["cache_hit"]


async def test_runtime_timeouts_match_configuration_and_endpoint_mismatch_is_rejected(
    benchmark_files, tmp_path, monkeypatch
):
    path, _sample = benchmark_files
    settings = Settings(
        _env_file=None,
        ai_writing_vllm_base_url="http://localhost:8001",
        ai_writing_request_timeout_seconds=10,
        ai_writing_startup_timeout_seconds=11,
    )
    configs = configurations(settings, "v4", "off")
    actual = []

    def factory(runtime):
        actual.append(runtime)
        return PieProvider(json.loads(MATRIX.read_text(encoding="utf-8")))

    monkeypatch.setattr("app.evaluation.task1.runner.create_provider", factory)
    changed_timeouts = settings.model_copy(
        update={"ai_writing_request_timeout_seconds": 20, "ai_writing_startup_timeout_seconds": 21}
    )
    await run_benchmark(
        load_manifest(path, "dev"), configs, tmp_path / "runtime", settings=changed_timeouts
    )
    assert actual[0].ai_writing_request_timeout_seconds == 10
    assert actual[0].ai_writing_startup_timeout_seconds == 11
    mismatch = settings.model_copy(update={"ai_writing_vllm_base_url": "http://localhost:8002"})
    with pytest.raises(ValueError, match="BENCHMARK_RUNTIME_IDENTITY_MISMATCH"):
        await run_benchmark(
            load_manifest(path, "dev"), configs, tmp_path / "mismatch", settings=mismatch
        )
    assert len(actual) == 1


@pytest.mark.parametrize(
    "dependency",
    [
        "task1_claims.py",
        "task1_chart_cross_check.py",
        "mts_prompts.py",
        "vllm.py",
        "deplot_parser.py",
        "writing_ai.py",
    ],
)
def test_resume_identity_covers_shared_scoring_dependencies(monkeypatch, dependency):
    original = Path.read_text
    before = implementation_hash()

    def changed(path, *args, **kwargs):
        content = original(path, *args, **kwargs)
        return content + "\n# changed implementation\n" if path.name == dependency else content

    monkeypatch.setattr(Path, "read_text", changed)
    assert implementation_hash() != before


async def test_ablation_deltas_use_paired_valid_criterion_cohorts(benchmark_files, tmp_path):
    path, _sample = benchmark_files
    configs = configurations(Settings(_env_file=None), "v4", "both")
    report = await run_benchmark(
        load_manifest(path, "dev"),
        configs,
        tmp_path / "report",
        provider_factory=lambda _config: PieProvider(
            json.loads(MATRIX.read_text(encoding="utf-8"))
        ),
        specialist_factory=lambda _config: FakeSpecialist(
            "Region | Agriculture (%) | Industry (%) | Domestic (%)\nRegion A | 55 | 30 | 15"
        ),
    )
    before, after = [EvaluationRecord.model_validate(record) for record in report["records"]]
    missing_gra = {trait: score for trait, score in after.predicted.items() if trait != "gra"}
    a = before.model_copy(update={"sample_id": "A", "input_hash": "A"})
    b = after.model_copy(
        update={
            "sample_id": "A",
            "input_hash": "A",
            "status": "FAILED",
            "predicted": missing_gra,
            "predicted_overall": None,
        }
    )
    low = {**before.predicted, "gra": before.target["gra"] + Decimal("0.5")}
    c = before.model_copy(update={"sample_id": "B", "input_hash": "B", "predicted": low})
    d = after.model_copy(update={"sample_id": "B", "input_hash": "B", "predicted": low})
    comparison = build_report([a, b, c, d], configs)["ablations"][0]
    assert comparison["paired_sample_count"] == 2
    assert comparison["paired_criterion_counts"]["gra"] == 1
    assert comparison["criterion_deltas"]["gra"]["mae"] == 0
    assert comparison["failure_rate_delta"] == 0.5
