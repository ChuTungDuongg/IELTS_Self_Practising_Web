"""Offline ablation plans never authorize or disguise billable inference."""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.evaluation.task1.manifest import load_manifest
from app.evaluation.task1.report import build_report
from app.evaluation.task1.runner import configurations, run_benchmark
from app.evaluation.writing.runtime import CountedProvider, reconciled_usage
from app.providers.writing_llm.base import Completion, CompletionOptions, ProviderFailure

ROOT = Path(__file__).parents[2]


def cli():
    spec = importlib.util.spec_from_file_location(
        "task1_ablation_cli", ROOT / "scripts/benchmark_task1.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def manifest(tmp_path):
    image = tmp_path / "fictional.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfictional image fixture")
    sample = {
        "schema_version": 1,
        "id": "DEV-001",
        "split": "dev",
        "task_type": "BAR_CHART",
        "prompt": "Describe a fictional chart.",
        "essay": "PRIVATE_ESSAY_NEVER_IN_REPORT",
        "image_path": image.name,
        "human_scores": {"ta": 6, "cc": 6, "lr": 6, "gra": 6},
        "raters": 1,
        "provenance": "Fictional contract test",
        "redistributable": True,
        "visual_truth": None,
    }
    path = tmp_path / "task1.jsonl"
    path.write_text(json.dumps(sample), encoding="utf-8")
    return path


def luna():
    return Settings(
        _env_file=None, ai_writing_provider="openai", ai_writing_openai_model="gpt-6-luna"
    )


def test_cli_requires_explicit_live_opt_in_before_reading_private_data(tmp_path, capsys):
    result = cli().main(["--manifest", str(tmp_path / "missing.jsonl"), "--split", "dev"])
    assert result == 2
    assert "BENCHMARK_LIVE_OPT_IN_REQUIRED" in capsys.readouterr().err


def test_cli_ablation_plans_same_dev_samples_and_reports_no_quality_measurement(
    manifest, tmp_path, monkeypatch
):
    script = cli()
    monkeypatch.setattr(script, "Settings", lambda **_kwargs: luna())
    output = tmp_path / "plan"
    result = script.main(
        [
            "--manifest",
            str(manifest),
            "--split",
            "dev",
            "--openai-ablation",
            "--dry-run",
            "--limit",
            "1",
            "--output",
            str(output),
        ]
    )
    assert result == 0
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "DRY_RUN" and report["planned_scoring_runs"] == 4
    assert report["evaluated_run_count"] == 0
    arms = [item["configuration"]["openai_inference"] for item in report["configurations"].values()]
    assert [arm["arm"] for arm in arms] == ["A", "B", "C", "D"]
    assert all(arm["planning_only"] for arm in arms)
    assert arms[0]["reasoning"]["default"] == "none"
    assert arms[0]["image_detail"] is None
    assert arms[0]["legacy_stage_caps"] is True
    assert arms[1]["reasoning"]["task1.scoring.ta"] == "medium"
    assert arms[1]["medium_completion_tokens"] == 16384
    assert arms[1]["image_detail"] is None
    assert arms[2]["image_detail"] == "high"
    assert [arm["task1_image_assessment"] for arm in arms] == [False, False, False, True]
    assert [arm["task1_text_relevance_gate"] for arm in arms] == [True, True, True, False]
    assert [arm["stage_timeout_seconds"] for arm in arms] == [300, 300, 300, 300]
    assert {c["configuration"]["model"] for c in report["configurations"].values()} == {
        "gpt-6-luna"
    }
    assert len(report["plan"]) == 1 and report["plan"][0]["sample_id"] == "DEV-001"
    assert report["openai_ablation"]["budget"]["requested_max_usd"] == "0.50"
    assert report["openai_ablation"]["budget"]["live_enabled"] is False
    assert report["openai_ablation"]["factual_feedback_accuracy"] == "unmeasured"
    assert report["openai_ablation"]["stability"] == "unmeasured"
    assert len(report["ablations"]) == 3
    assert all(comparison["kind"] == "openai_inference" for comparison in report["ablations"])
    assert all(comparison["paired_sample_count"] == 0 for comparison in report["ablations"])
    text = json.dumps(report)
    assert "PRIVATE_ESSAY" not in text and "fictional image fixture" not in text


def test_cli_live_ablation_is_rejected_even_with_opt_in_and_small_dollar_limit(
    manifest, tmp_path, capsys
):
    result = cli().main(
        [
            "--manifest",
            str(manifest),
            "--split",
            "dev",
            "--openai-ablation",
            "--allow-live",
            "--max-cost-usd",
            "0.50",
            "--output",
            str(tmp_path / "none"),
        ]
    )
    assert result == 2
    assert "BENCHMARK_ABLATION_LIVE_DISABLED" in capsys.readouterr().err
    assert not (tmp_path / "none").exists()


def test_cli_ablation_cannot_tune_holdout(manifest, tmp_path, capsys):
    result = cli().main(
        [
            "--manifest",
            str(manifest),
            "--split",
            "holdout",
            "--openai-ablation",
            "--dry-run",
            "--output",
            str(tmp_path / "none"),
        ]
    )
    assert result == 2
    assert "BENCHMARK_ABLATION_DEV_ONLY" in capsys.readouterr().err


async def test_runner_cannot_execute_planning_arms_even_with_injected_provider(manifest, tmp_path):
    from app.evaluation.task1.openai_ablation import ablation_configurations

    configs = ablation_configurations(luna())
    with pytest.raises(ValueError, match="BENCHMARK_ABLATION_LIVE_DISABLED"):
        await run_benchmark(
            load_manifest(manifest, "dev"),
            configs,
            tmp_path / "none",
            provider_factory=lambda _config: pytest.fail(
                "planning arms must never instantiate providers"
            ),
        )


def test_openai_budget_identity_changes_without_invalidating_vllm():
    baseline = Settings(_env_file=None, ai_writing_provider="vllm")
    changed = baseline.model_copy(update={"ai_writing_openai_max_output_tokens": 16384})
    assert (
        configurations(baseline, "v12", "off")[0].key
        == configurations(changed, "v12", "off")[0].key
    )
    openai = luna()
    smaller = openai.model_copy(update={"ai_writing_openai_max_output_tokens": 16384})
    assert (
        configurations(openai, "v12", "off")[0].key != configurations(smaller, "v12", "off")[0].key
    )


async def test_benchmark_accounting_preserves_failed_usage_reasoning_and_stage_options():
    class Provider:
        task1_image_assessment = True
        run_timeout_seconds = 1800
        reasoned_inference = True

        def __init__(self):
            self.count = 0
            self.options = []

        async def complete(self, messages, schema, *, options=None):
            self.count += 1
            self.options.append(options)
            if self.count == 1:
                raise ProviderFailure(
                    "AI_PROVIDER_BAD_RESPONSE",
                    reason="PROVIDER_FINISH_LENGTH",
                    finish_reason="length",
                    usage={"prompt_tokens": 10, "completion_tokens": 100, "reasoning_tokens": 99},
                )
            return Completion(
                "{}", {"prompt_tokens": 11, "completion_tokens": 200, "reasoning_tokens": 190}
            )

    raw = Provider()
    provider = CountedProvider(raw)
    options = CompletionOptions(max_tokens=1000)
    with pytest.raises(ProviderFailure):
        await provider.complete([], {}, options=options)
    await provider.complete([], {}, options=options)
    assert raw.options == [options, options]
    assert provider.task1_image_assessment is True
    assert provider.run_timeout_seconds == 1800
    assert provider.reasoned_inference is True
    usage = reconciled_usage(provider, None)
    assert usage == {"prompt_tokens": 21, "completion_tokens": 300, "reasoning_tokens": 289}
    assert provider.truncated_call_count == 1
    # Scorer bookkeeping describes the same calls; it must not double usage.
    scorer = type("Scorer", (), {"usage": [usage]})()
    assert reconciled_usage(provider, scorer) == usage


async def test_internal_budget_repair_counts_two_billable_calls_without_double_usage():
    class Provider:
        async def complete(self, messages, schema, *, options=None):
            return Completion(
                "{}",
                {"prompt_tokens": 20, "completion_tokens": 300, "reasoning_tokens": 280},
                attempts=(
                    {"finish_reason": "length", "usage": {"completion_tokens": 100}},
                    {"finish_reason": "stop", "usage": {"completion_tokens": 200}},
                ),
            )

    counted = CountedProvider(Provider())
    await counted.complete([], {})
    assert counted.calls == 2
    assert counted.truncated_call_count == 1
    assert counted.finish_reasons == {"length": 1, "stop": 1}
    assert reconciled_usage(counted, None)["completion_tokens"] == 300


async def test_cancelled_repair_preserves_known_failed_usage_and_unknown_inflight_cost():
    class Provider:
        request_attempts = 0

        async def complete(self, messages, schema, *, options=None):
            self.request_attempts = 2
            cancellation = asyncio.CancelledError()
            cancellation.usage = {"completion_tokens": 100, "reasoning_tokens": 100}
            cancellation.attempts = ({"finish_reason": "length"},)
            raise cancellation

    counted = CountedProvider(Provider())
    with pytest.raises(asyncio.CancelledError):
        await counted.complete([], {})
    assert counted.calls == 2
    assert counted.truncated_call_count == 1
    assert reconciled_usage(counted, None) == {"completion_tokens": 100, "reasoning_tokens": 100}


@pytest.mark.parametrize("failure", ["busy", "timeout", "cancelled"])
async def test_admission_failure_before_post_does_not_invent_benchmark_call_or_finish(
    failure, monkeypatch
):
    from app.providers.writing_llm.admission import admission
    from app.providers.writing_llm.openai import OpenAIProvider

    provider = OpenAIProvider(
        Settings(
            _env_file=None,
            ai_writing_openai_stage_timeout_seconds=0.01 if failure == "timeout" else 300,
            ai_writing_openai_max_concurrent_requests=1,
            ai_writing_openai_max_queued_requests=0 if failure == "busy" else 1,
        )
    )

    async def forbidden(_body):
        pytest.fail("a queued or rejected request must not reach HTTP")

    monkeypatch.setattr(provider.transport, "send", forbidden)
    counted = CountedProvider(provider)
    gate = admission(provider.limit, provider.max_queued)
    async with gate.slot():
        if failure == "cancelled":
            pending = asyncio.create_task(counted.complete([], {}))
            await asyncio.sleep(0)
            assert gate.waiting == 1
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            with pytest.raises(ProviderFailure) as error:
                await counted.complete([], {})
            assert error.value.code == (
                "AI_PROVIDER_BUSY" if failure == "busy" else "AI_PROVIDER_TIMEOUT"
            )
    assert provider.request_attempts == 0
    assert counted.calls == 0
    assert counted.finish_reasons == {}
    assert counted.truncated_call_count == 0
    assert reconciled_usage(counted, None) == {}


def test_empty_report_does_not_invent_cost_factual_truth_or_stability():
    report = build_report([], configurations(Settings(_env_file=None), "v12", "off"))
    assert (
        report["measurements"]["factual_feedback_accuracy"]
        == "unmeasured_missing_adjudicated_feedback_labels"
    )
    assert report["measurements"]["repeat_stability"] == "unmeasured_no_repeat_protocol"
    assert report["operational"]["cost_usd"] is None
    assert report["operational"]["truncation_rate_per_call"] is None


async def test_runner_rejects_changed_openai_policy_before_instantiating_provider(
    manifest, tmp_path, monkeypatch
):
    settings = luna()
    configs = configurations(settings, "v12", "off")
    changed = settings.model_copy(update={"ai_writing_openai_max_output_tokens": 16384})
    monkeypatch.setattr(
        "app.evaluation.task1.runner.create_provider",
        lambda _settings: pytest.fail(
            "incompatible runtime identity must be rejected before inference"
        ),
    )
    with pytest.raises(ValueError, match="BENCHMARK_RUNTIME_IDENTITY_MISMATCH"):
        await run_benchmark(
            load_manifest(manifest, "dev"), configs, tmp_path / "none", settings=changed
        )


async def test_benchmark_keeps_primary_perception_error_after_successful_ta_reconciliation():
    from test_openai_task1_assessment import SourceImageProvider, envelope
    from test_task1_visual import chart, request

    from app.evaluation.task1.manifest import LoadedSample
    from app.evaluation.task1.models import BenchmarkSample
    from app.evaluation.task1.runner import evaluate

    req = request()
    sample = BenchmarkSample(
        schema_version=1,
        id="DEV-RECONCILE",
        split="dev",
        task_type=req.task_type,
        prompt=req.prompt,
        image_path="unused-fictional.png",
        essay=req.response,
        human_scores={"ta": 7, "cc": 7, "lr": 7, "gra": 7},
        provenance="Synthetic reconciliation fixture",
        redistributable=True,
        visual_truth=chart(),
    )
    provider = SourceImageProvider(
        [envelope("CONFLICT"), envelope()], [chart(values=(20, 40)), chart()]
    )
    record = await evaluate(
        LoadedSample(sample, req.image),
        configurations(luna(), "v12", "off")[0],
        lambda _config: provider,
        lambda _config: pytest.fail("DePlot must remain off"),
    )
    assert record.status == "COMPLETED"
    assert record.perception["primary"]["exact_labelled_numeric_agreement"] == 0.75
    assert record.perception["primary"]["perception_ok"] is False
    assert record.perception["reconciled"]["exact_labelled_numeric_agreement"] == 1
    assert record.perception["reconciled"]["perception_ok"] is True
    assert record.ta_assessment["status"] == "READY"
    assert record.ta_assessment["reconciliations"] == 1
