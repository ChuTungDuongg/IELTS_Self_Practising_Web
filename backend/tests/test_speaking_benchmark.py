"""Offline evaluation contract and existing scorer integration, synthetic inputs only."""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.evaluation.speaking.manifest import BenchmarkInputError, load_manifest, load_predictions
from app.evaluation.speaking.models import BenchmarkSample, PredictionSet, provenance
from app.evaluation.speaking.report import build_report, write_reports
from app.evaluation.speaking.runner import evaluate_samples


def sample(identifier="synthetic-1", *, group="quiet"):
    return {
        "schema_version": 1,
        "id": identifier,
        "responses": [
            {
                "fixture_id": "synthetic-tone",
                "part_number": 1,
                "prompt_type": "SHORT_ANSWER",
                "prompt_text": "Describe a fictional garden.",
            }
        ],
        "human": {"fc": 6, "lr": 6.5, "gra": 7, "pr": 6.5, "overall": 6.5},
        "subgroups": {"recording_environment": group},
        "assessor_version": "fictional-rater-v1",
    }


def predictions(*rows):
    return PredictionSet.model_validate(
        {
            "schema_version": 1,
            "provenance": provenance(Settings()).model_dump(mode="json"),
            "predictions": list(rows),
        }
    )


def test_manifest_roundtrip_and_local_references(tmp_path):
    path = tmp_path / "manifest.jsonl"
    value = sample()
    value["responses"][0].pop("fixture_id")
    value["responses"][0]["audio_path"] = "private/fictional.wav"
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    loaded = load_manifest(path)
    assert loaded[0].id == "synthetic-1" and loaded[0].human.fc == 6
    assert loaded[0].responses[0].audio_path == "private/fictional.wav"


@pytest.mark.parametrize("band", [6.3, -0.5, 9.5, True, "6.5", float("nan"), float("inf")])
def test_invalid_human_or_advisory_band_rejected(band):
    raw = sample()
    raw["human"]["pr"] = band
    with pytest.raises(ValueError):
        BenchmarkSample.model_validate(raw)
    with pytest.raises(ValueError):
        predictions({"id": "synthetic-1", "scores": {"fc": band}})


def test_missing_human_labels_duplicate_ids_and_sensitive_subgroups_fail_safely(tmp_path):
    path = tmp_path / "manifest.jsonl"
    invalid = sample()
    del invalid["human"]["overall"]
    invalid["responses"][0]["prompt_text"] = "PRIVATE_NOTE_DO_NOT_ECHO"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(BenchmarkInputError) as error:
        load_manifest(path)
    assert str(error.value) == "BENCHMARK_SAMPLE_INVALID:line=1"
    assert "PRIVATE" not in str(error.value)
    path.write_text((json.dumps(sample()) + "\n") * 2, encoding="utf-8")
    with pytest.raises(BenchmarkInputError, match="DUPLICATE_ID"):
        load_manifest(path)
    invalid = sample()
    invalid["subgroups"] = {"race": "sensitive"}
    with pytest.raises(ValueError):
        BenchmarkSample.model_validate(invalid)


def test_report_counts_missing_predictions_and_suppresses_small_groups(tmp_path):
    samples = [BenchmarkSample.model_validate(sample(f"synthetic-{i}")) for i in range(2)]
    scored = predictions({"id": "synthetic-0", "scores": {"fc": 6, "lr": 6.5, "gra": 7, "pr": 6.5}})
    report = build_report(samples, scored, minimum_subgroup_samples=20)
    assert report["criteria"]["fc"]["total_count"] == 2
    assert report["criteria"]["fc"]["failure_rate"] == 0.5
    assert report["criteria"]["overall"]["failure_rate"] == 0.5
    assert report["subgroups"]["recording_environment"]["quiet"] == {
        "status": "insufficient_samples",
        "sample_count": 2,
        "minimum_samples": 20,
    }
    write_reports(tmp_path, samples, scored, report)
    first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    write_reports(
        tmp_path, list(reversed(samples)), scored, build_report(list(reversed(samples)), scored)
    )
    assert first == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert "PRIVATE" not in json.dumps(report) and "prompt_text" not in json.dumps(report)
    assert "fixture_id" not in json.dumps(report) and "audio_path" not in json.dumps(report)
    assert "MISSING_PREDICTION" in (tmp_path / "samples.jsonl").read_text()


def test_provenance_is_current_versioned_secret_free_and_labels_are_not_averaged():
    settings = Settings(
        ai_writing_vllm_api_key="PRIVATE_KEY", speaking_asr_model_directory="PRIVATE_DIRECTORY"
    )
    identity = provenance(settings)
    assert (
        identity.scorer == "SpeakingScorer"
        and identity.prompt_version == settings.speaking_ai_prompt_version
    )
    assert identity.rubric_version == settings.speaking_ai_rubric_version
    assert identity.asr_version == settings.speaking_asr_version
    assert (
        identity.normalizer_version
        and identity.quality_version
        and identity.fluency_version
        and identity.pronunciation_version
    )
    assert "PRIVATE" not in identity.model_dump_json()
    scores = predictions({"id": "synthetic-1", "scores": {"fc": 5, "lr": 6, "gra": 7, "pr": 8}})
    assert scores.predictions[0].overall == 6.5
    raw = sample()
    raw["human"]["overall"] = 7
    assert BenchmarkSample.model_validate(raw).human.overall == 7


def test_imported_results_reject_bodies_unknown_scores_duplicates_and_foreign_ids(tmp_path):
    path = tmp_path / "predictions.json"
    payload = predictions().model_dump(mode="json")
    payload["transcript"] = "PRIVATE_TRANSCRIPT"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BenchmarkInputError, match="PREDICTIONS_INVALID"):
        load_predictions(path)
    for raw in (
        {"id": "synthetic-1", "scores": {"overall": 7}},
        {"id": "synthetic-1", "scores": {"fc": 7}, "reason": "PRIVATE_EXCEPTION"},
    ):
        with pytest.raises(ValueError):
            predictions(raw)
    with pytest.raises(ValueError):
        predictions({"id": "duplicate"}, {"id": "duplicate"})
    with pytest.raises(BenchmarkInputError, match="PREDICTION_ID_UNKNOWN"):
        build_report([BenchmarkSample.model_validate(sample())], predictions({"id": "foreign"}))


async def test_synthetic_provider_flow_uses_existing_score_first_scorer_and_resume(
    tmp_path, monkeypatch
):
    from test_speaking_ai import evidence, feature_bundle
    from test_speaking_ai_runs import FakeLLM

    from app.services.speaking_scorer import SpeakingScorer

    items = [BenchmarkSample.model_validate(sample())]
    provider = FakeLLM(fail_feedback=True)
    scorer = SpeakingScorer(provider)
    identity = provenance(Settings()).model_copy(
        update={
            "provider": "fake",
            "model": "synthetic-v1",
            "asr_provider": "fixture",
            "asr_model": "synthetic-v1",
        }
    )
    called = []

    async def synthetic_input(item, *_):
        called.append(item.id)
        return evidence(features=feature_bundle())

    result = await evaluate_samples(
        items,
        tmp_path,
        tmp_path,
        Settings(),
        scorer=scorer,
        evidence_loader=synthetic_input,
        run_provenance=identity,
    )
    assert result.predictions[0].overall == 6.5
    assert len(provider.calls) == 8 and called == [items[0].id]
    assert (
        json.loads((tmp_path / "predictions.json").read_text())["predictions"][0]["scores"]["fc"]
        == 6.5
    )
    cached = await evaluate_samples(
        items,
        tmp_path,
        tmp_path,
        Settings(),
        scorer=scorer,
        evidence_loader=synthetic_input,
        resume=True,
        run_provenance=identity,
    )
    assert cached == result and len(provider.calls) == 8
    serialized = "".join(
        p.read_text() for p in tmp_path.iterdir() if p.suffix in {".json", ".jsonl", ".csv", ".md"}
    )
    assert "He go" not in serialized and "PRIVATE" not in serialized


def test_subgroup_large_enough_reports_failures_and_metric_statuses():
    items = [BenchmarkSample.model_validate(sample(f"synthetic-{i}")) for i in range(5)]
    report = build_report(
        items, predictions({"id": "synthetic-0", "scores": {"fc": 6}}), minimum_subgroup_samples=5
    )
    group = report["subgroups"]["recording_environment"]["quiet"]
    assert group["status"] == "ok"
    assert group["criteria"]["fc"]["failure_rate"] == 0.8
    assert group["criteria"]["fc"]["pearson"] is None
    assert group["criteria"]["fc"]["pearson_status"] == "insufficient_samples"
    assert report["nonscorable_reasons"]["pr"] == {"MISSING_PREDICTION": 5}


def test_manifest_validates_unselected_rows_and_duplicate_json_keys(tmp_path):
    path = tmp_path / "manifest.jsonl"
    path.write_text(json.dumps(sample()) + '\n{"id":"a","id":"b"}', encoding="utf-8")
    with pytest.raises(BenchmarkInputError, match="SAMPLE_INVALID:line=2"):
        load_manifest(path, max_samples=1)


async def test_provider_failure_is_counted_and_private_exception_is_not_saved(tmp_path):
    from test_speaking_ai import evidence, feature_bundle
    from test_speaking_ai_runs import FakeLLM

    from app.services.speaking_scorer import SpeakingScorer

    class FailedProvider(FakeLLM):
        async def complete(self, *args, **kwargs):
            raise RuntimeError("PRIVATE_PROVIDER_BODY_PATH")

    async def synthetic_input(*args):
        return evidence(features=feature_bundle())

    items = [BenchmarkSample.model_validate(sample())]
    scored = await evaluate_samples(
        items,
        tmp_path,
        tmp_path,
        Settings(),
        scorer=SpeakingScorer(FailedProvider()),
        evidence_loader=synthetic_input,
    )
    assert scored.predictions[0].overall is None
    assert build_report(items, scored)["criteria"]["overall"]["failure_rate"] == 1
    assert set(scored.predictions[0].reasons.values()) == {"SPEAKING_AI_PROVIDER_FAILED"}
    assert "PRIVATE" not in (tmp_path / "predictions.json").read_text()


async def test_benchmark_quality_gate_rejects_silent_wav_without_asr_or_llm(tmp_path, monkeypatch):
    import wave

    from app.evaluation.speaking.runner import load_evidence

    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\0" * 320000)
    raw = sample()
    raw["responses"][0].pop("fixture_id")
    raw["responses"][0]["audio_path"] = path.name

    def forbidden(*args):
        pytest.fail("silent audio must never construct ASR")

    monkeypatch.setattr("app.providers.speaking_asr.create_provider", forbidden)
    items = [BenchmarkSample.model_validate(raw)]
    result = await evaluate_samples(
        items, tmp_path, tmp_path / "output", Settings(), evidence_loader=load_evidence
    )
    assert set(result.predictions[0].reasons.values()) == {"SPEAKING_AUDIO_UNASSESSABLE"}


async def test_score_is_checkpointed_before_feedback_and_cache_changes_with_input(tmp_path):
    from test_speaking_ai import evidence, feature_bundle
    from test_speaking_ai_runs import FakeLLM

    from app.services.speaking_scorer import SpeakingScorer

    class CheckedProvider(FakeLLM):
        async def complete(self, messages, schema, *, options=None):
            if "score" not in schema["properties"]:
                checkpoint = json.loads((tmp_path / "predictions.json").read_text())
                supplied = json.loads(messages[-1]["content"])
                trait = supplied["evidence"]["criterion"]
                assert checkpoint["predictions"][0]["scores"][trait] == supplied["persisted_score"]
            return await super().complete(messages, schema, options=options)

    async def synthetic_input(*args):
        return evidence(features=feature_bundle())

    items = [BenchmarkSample.model_validate(sample())]
    provider = CheckedProvider()
    scorer = SpeakingScorer(provider)
    original = await evaluate_samples(
        items, tmp_path, tmp_path, Settings(), scorer=scorer, evidence_loader=synthetic_input
    )
    items[0].responses[0].prompt_text = "Different fictional prompt."
    changed = await evaluate_samples(
        items,
        tmp_path,
        tmp_path,
        Settings(),
        scorer=scorer,
        evidence_loader=synthetic_input,
        resume=True,
    )
    assert len(provider.calls) == 16
    assert original.predictions[0].cache_key != changed.predictions[0].cache_key


def test_cli_offline_default_and_validation_never_construct_providers(
    tmp_path, monkeypatch, capsys
):
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts/evaluate_speaking.py"
    spec = importlib.util.spec_from_file_location("speaking_benchmark_cli", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps(sample()) + "\n", encoding="utf-8")
    results = tmp_path / "existing.json"
    results.write_text(
        predictions(
            {"id": "synthetic-1", "scores": {"fc": 6, "lr": 6, "gra": 6, "pr": 6}}
        ).model_dump_json(),
        encoding="utf-8",
    )
    assert cli.main(["--manifest", str(manifest), "--validate-manifest"]) == 0
    assert (
        cli.main(
            [
                "--manifest",
                str(manifest),
                "--predictions",
                str(results),
                "--output",
                str(tmp_path / "report"),
            ]
        )
        == 0
    )
    assert (tmp_path / "report/summary.json").exists()
    assert cli.main(["--manifest", str(manifest), "--output", str(tmp_path / "unused")]) == 2
    assert "LIVE_SCORING_REQUIRES_EXPLICIT_FLAG" in capsys.readouterr().err
