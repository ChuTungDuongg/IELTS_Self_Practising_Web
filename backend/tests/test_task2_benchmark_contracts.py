import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.evaluation.task2.manifest import BenchmarkInputError, load_manifest
from app.evaluation.task2.models import BenchmarkConfig, BenchmarkSample, EvaluationRecord


def sample(**changes):
    return {
        "schema_version": 1,
        "id": "T2-001",
        "split": "dev",
        "prompt": " Fictional question\r\n😀 ",
        "essay": " Fictional essay\n\nParagraph two ",
        "human_scores": {"tr": 6, "cc": 6, "lr": 6.5, "gra": 6.5},
        "raters": 1,
        "provenance": "Fictional test only",
        "redistributable": False,
        **changes,
    }


def test_exact_text_numeric_round_trip_and_task_response():
    data = sample()
    value = BenchmarkSample.model_validate(data)
    assert value.prompt == data["prompt"] and value.essay == data["essay"]
    assert value.human_scores.scores() == {
        "tr": Decimal(6),
        "cc": Decimal(6),
        "lr": Decimal("6.5"),
        "gra": Decimal("6.5"),
    }
    assert BenchmarkSample.model_validate_json(value.model_dump_json()) == value
    assert value.human_overall == Decimal("6.5")


@pytest.mark.parametrize(
    "changes",
    [
        {"image_path": "test.png"},
        {"visual_truth": None},
        {"task_type": "OPINION"},
        {"schema_version": 2},
        {"raters": 2},
        {"redistributable": "false"},
        {"prompt": "\r\n \t"},
        {"essay": ""},
        {"provenance": " "},
        {"id": "../../escape"},
        {"id": "é"},
        {"prompt": "x" * 20001},
    ],
)
def test_strict_text_only_sample(changes):
    with pytest.raises(ValidationError):
        BenchmarkSample.model_validate(sample(**changes))


@pytest.mark.parametrize("label", [6.3, 6.49, -0.5, 9.5, "NaN", "Infinity", True])
def test_invalid_labels(label):
    data = sample()
    data["human_scores"]["tr"] = label
    with pytest.raises(ValidationError):
        BenchmarkSample.model_validate(data)


def test_ta_not_accepted_and_missing_criterion_rejected():
    data = sample()
    data["human_scores"]["ta"] = data["human_scores"].pop("tr")
    with pytest.raises(ValidationError):
        BenchmarkSample.model_validate(data)
    del data["human_scores"]["ta"]
    with pytest.raises(ValidationError):
        BenchmarkSample.model_validate(data)


def test_manifest_selection_and_exact_content(tmp_path):
    path = tmp_path / "task2.jsonl"
    data = [sample(), sample(id="T2-002", split="holdout"), sample(id="T2-003")]
    path.write_text("\n".join(json.dumps(row) for row in data), encoding="utf-8")
    assert [row.sample.id for row in load_manifest(path, "dev", 1)] == ["T2-001"]
    assert [row.sample.id for row in load_manifest(path, "holdout")] == ["T2-002"]
    path.write_text("\n".join(json.dumps(row) for row in [*data, data[1]]), encoding="utf-8")
    with pytest.raises(BenchmarkInputError, match="BENCHMARK_DUPLICATE_ID:line=4"):
        load_manifest(path, "dev", 1)


def test_manifest_safe_failures_limits_and_no_csv_reader(tmp_path):
    path = tmp_path / "task2.jsonl"
    path.write_text('{"essay":"PRIVATE CONTENT", "unknown":"SECRET"}', encoding="utf-8")
    with pytest.raises(BenchmarkInputError) as error:
        load_manifest(path, "dev")
    assert str(error.value) == "BENCHMARK_SAMPLE_INVALID:line=1"
    path.write_text("id,prompt,essay\n", encoding="utf-8")
    with pytest.raises(BenchmarkInputError):
        load_manifest(path, "dev")
    with path.open("wb") as file:
        file.truncate(16 * 1024 * 1024 + 1)
    with pytest.raises(BenchmarkInputError, match="BENCHMARK_MANIFEST_TOO_LARGE"):
        load_manifest(path, "dev")
    with pytest.raises(BenchmarkInputError, match="BENCHMARK_SELECTION_INVALID"):
        load_manifest(path, "dev", 0)
    with pytest.raises(BenchmarkInputError, match="BENCHMARK_MANIFEST_UNREADABLE"):
        load_manifest(tmp_path / "missing", "dev")


def record(**changes):
    return dict(
        sample_id="T2-001",
        split="dev",
        config_key="a" * 64,
        input_hash="b" * 64,
        cache_key="c" * 64,
        status="COMPLETED",
        target={"tr": 6, "cc": 6, "lr": 6, "gra": 6},
        predicted={"tr": 6, "cc": 6, "lr": 6, "gra": 6},
        target_overall=6,
        predicted_overall=6,
        wall_clock_seconds=1,
        provider_calls=8,
        token_usage={},
        failures={},
        **changes,
    )


def test_records_require_consistent_success_and_allow_visible_partial_failure():
    value = EvaluationRecord.model_validate(record())
    assert value.status == "COMPLETED"
    for edits in (
        {"predicted": {"tr": 6}},
        {"predicted_overall": 9},
        {"target_overall": 9},
        {"failures": {"tr": "AI_PROVIDER_HTTP_ERROR"}},
        {"image_hash": "forbidden"},
    ):
        with pytest.raises(ValidationError):
            EvaluationRecord.model_validate({**record(), **edits})
    partial = EvaluationRecord.model_validate(
        {
            **record(),
            "status": "FAILED",
            "predicted": {"tr": 6},
            "predicted_overall": None,
            "failures": {"cc": "AI_PROVIDER_HTTP_ERROR"},
        }
    )
    assert partial.predicted_overall is None


def test_config_technical_identity_excludes_presentation_label():
    config = BenchmarkConfig(
        label="Task 2",
        prompt_version="mts-task2-v12",
        provider="vllm",
        model="fictional",
        endpoint_hash="a" * 64,
        request_timeout_seconds=60,
        startup_timeout_seconds=120,
        implementation_hash="b" * 64,
    )
    assert config.key == config.model_copy(update={"label": "Different caption"}).key
    assert config.key != config.model_copy(update={"max_concurrent_llm_requests": 4}).key
    assert not any(
        field in BenchmarkConfig.model_fields
        for field in ("dataset_version", "image", "endpoint", "api_key")
    )
