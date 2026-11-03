import json
from decimal import Decimal

import pytest
from test_task2_benchmark_contracts import sample

from app.core.config import Settings
from app.evaluation.task2.manifest import LoadedSample
from app.evaluation.task2.models import BenchmarkSample, EvaluationRecord
from app.evaluation.task2.runner import configuration, evaluate, fingerprint, run_benchmark
from app.evaluation.writing_latency import FakeLatencyProvider, call_identity, load_fixture
from app.providers.writing_llm.base import Completion, ProviderFailure


def item(**changes):
    fixture = load_fixture()
    return LoadedSample(
        BenchmarkSample.model_validate(
            sample(prompt=fixture["task2"]["prompt"], essay=fixture["task2"]["response"], **changes)
        )
    )


def config(**changes):
    return configuration(Settings(_env_file=None)).model_copy(update=changes)


class Provider(FakeLatencyProvider):
    def __init__(self, *, fail=None):
        super().__init__(load_fixture(), 0.001)
        self.fail = fail

    async def complete(self, messages, schema, *, options=None):
        stage, trait = call_identity(messages, schema)
        if (stage, trait) == self.fail:
            raise ProviderFailure("AI_PROVIDER_HTTP_ERROR", usage={"total_tokens": 5})
        output = await super().complete(messages, schema, options=options)
        return Completion(output.text, usage={"total_tokens": 10})


async def test_real_production_orchestration_maps_task_response_and_no_label_leak():
    requests = []
    first_item = item()
    different_labels = first_item.sample.model_copy(
        update={
            "human_scores": first_item.sample.human_scores.model_copy(update={"tr": Decimal(9)}),
            "provenance": "PRIVATE LABEL NOTE",
        }
    )
    for value in (first_item, LoadedSample(different_labels)):
        provider = Provider()
        result = await evaluate(value, config(), lambda _, provider=provider: provider)
        assert result.status == "COMPLETED" and set(result.predicted) == {"tr", "cc", "lr", "gra"}
        assert result.predicted["tr"] == 6.5 and result.predicted_overall == 6.5
        requests.append(
            [(messages, schema, options) for _, _, messages, schema, options in provider.calls]
        )
        assert result.provider_calls == len(provider.calls)
        assert result.token_usage == {"total_tokens": 10 * len(provider.calls)}
    assert requests[0] == requests[1]  # Exact payload comparison, not numeric substrings.
    assert fingerprint(first_item, config()) != fingerprint(
        LoadedSample(different_labels), config()
    )
    assert "PRIVATE LABEL NOTE" not in json.dumps(requests, default=str)


@pytest.mark.parametrize("limit", [1, 2, 4])
async def test_samples_sequential_and_criterion_limit_preserved(tmp_path, limit):
    providers = []

    def factory(_):
        assert not any(p.active for p in providers)
        provider = Provider()
        providers.append(provider)
        return provider

    report = await run_benchmark(
        [item(), item(id="T2-002")],
        config(max_concurrent_llm_requests=limit),
        tmp_path,
        provider_factory=factory,
    )
    assert report["sample_count"] == 2 and len(providers) == 2
    assert all(p.peak_active <= limit for p in providers)
    assert all(record["status"] == "COMPLETED" for record in report["records"])


async def test_failed_criterion_keeps_partial_scores_and_known_failed_usage(tmp_path):
    report = await run_benchmark(
        [item()], config(), tmp_path, provider_factory=lambda _: Provider(fail=("scoring", "cc"))
    )
    record = EvaluationRecord.model_validate(report["records"][0])
    assert record.status == "FAILED" and record.predicted_overall is None
    assert set(record.predicted) == {"tr", "lr", "gra"}
    assert record.failures["cc"] == "CRITERION_FAILED"
    assert record.token_usage["total_tokens"] == (record.provider_calls - 1) * 10 + 5
    assert report["aggregate"]["failure_count"] == 1


async def test_reasoning_usage_survives_partial_checkpoint_without_double_counting(tmp_path):
    class ReasoningProvider(Provider):
        async def complete(self, messages, schema, *, options=None):
            stage, trait = call_identity(messages, schema)
            if (stage, trait) == ("scoring", "cc"):
                raise ProviderFailure(
                    "AI_PROVIDER_HTTP_ERROR",
                    usage={"prompt_tokens": 3, "completion_tokens": 5, "reasoning_tokens": 5},
                )
            output = await super().complete(messages, schema, options=options)
            return Completion(
                output.text,
                usage={"prompt_tokens": 10, "completion_tokens": 20, "reasoning_tokens": 15},
            )

    report = await run_benchmark(
        [item()], config(), tmp_path, provider_factory=lambda _: ReasoningProvider()
    )
    record = EvaluationRecord.model_validate(report["records"][0])
    assert record.status == "FAILED" and set(record.predicted) == {"tr", "lr", "gra"}
    successes = record.provider_calls - 1
    assert record.token_usage == {
        "prompt_tokens": successes * 10 + 3,
        "completion_tokens": successes * 20 + 5,
        "reasoning_tokens": successes * 15 + 5,
    }
    assert report["operational"]["token_usage"] == record.token_usage
    assert len(list((tmp_path / "attempts").glob("*/*.json"))) == 1


async def test_failed_auxiliary_usage_is_counted_without_changing_fail_open_scoring():
    result = await evaluate(item(), config(), lambda _: Provider(fail=("relevance", "ta")))
    assert result.status == "COMPLETED" and result.predicted_overall == Decimal("6.5")
    assert result.token_usage == {"total_tokens": (result.provider_calls - 1) * 10 + 5}


async def test_raw_errors_never_enter_records(tmp_path):
    class SecretFailure(Provider):
        async def ensure_ready(self):
            raise RuntimeError("SECRET_URL https://private/key essay SECRET_ESSAY")

    report = await run_benchmark(
        [item()], config(), tmp_path, provider_factory=lambda _: SecretFailure()
    )
    text = json.dumps(report)
    assert "SECRET_URL" not in text and "SECRET_ESSAY" not in text
    assert report["records"][0]["failures"] == {"run": "BENCHMARK_SAMPLE_FAILED"}


async def test_dry_run_no_provider_no_database(tmp_path):
    def forbidden(_):
        raise AssertionError("Dry run must not create a provider")

    report = await run_benchmark(
        [item()], config(), tmp_path, dry_run=True, provider_factory=forbidden
    )
    assert report["status"] == "DRY_RUN" and report["planned_scoring_runs"] == 1
    assert report["aggregate"]["new_provider_calls"] == 0
    assert {"report.json", "report.md", "disagreements.csv"} <= {p.name for p in tmp_path.iterdir()}


def test_openai_inference_policy_changes_resume_identity_without_invalidating_vllm():
    settings = Settings(_env_file=None, ai_writing_provider="openai")
    changed = settings.model_copy(update={"ai_writing_openai_max_output_tokens": 16384})
    assert configuration(settings).key != configuration(changed).key
    vllm = settings.model_copy(update={"ai_writing_provider": "vllm"})
    changed_vllm = changed.model_copy(update={"ai_writing_provider": "vllm"})
    assert configuration(vllm).key == configuration(changed_vllm).key


async def test_changed_runtime_openai_policy_is_rejected_before_provider_creation(
    tmp_path, monkeypatch
):
    settings = Settings(_env_file=None, ai_writing_provider="openai")
    original = configuration(settings)
    changed = settings.model_copy(update={"ai_writing_openai_reasoning_effort": "medium"})
    monkeypatch.setattr(
        "app.evaluation.task2.runner.create_provider",
        lambda _settings: pytest.fail("mismatched runtime must not reach the provider"),
    )
    with pytest.raises(ValueError, match="BENCHMARK_RUNTIME_IDENTITY_MISMATCH"):
        await run_benchmark([item()], original, tmp_path, settings=changed)
