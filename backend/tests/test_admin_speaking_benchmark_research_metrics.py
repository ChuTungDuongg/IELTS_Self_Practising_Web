"""Known lexical edit arithmetic, coverage and experiment integrity fixtures."""

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.evaluation.speaking.asr_metrics import alignment, coverage_metrics
from app.schemas.speaking_benchmark_research import ExperimentCreate, ResearchConsent
from app.services.speaking_benchmark_research import check_consent, static_blockers
from app.services.speaking_benchmark_research_metrics import (
    reference_metrics,
    summarize_asr,
    transcript_diff,
)


def ref(text, annotations=None):
    return SimpleNamespace(
        status="VERIFIED",
        uncertainty=[],
        segment_id="s",
        source_sha256="a" * 64,
        start_ms=0,
        end_ms=100,
        text=text,
        annotations=annotations or [],
    )


def test_exact_edit_counts_and_display_script_share_alignment():
    expected, observed = "a b c d".split(), "a z d extra".split()
    s, d, i, _ = alignment(expected, observed)
    operations = transcript_diff("a b c d", "a z d extra")
    # Multiple optimal paths exist; the shared diagonal-first tie policy chooses
    # three substitutions here. Display and metric counts must agree exactly.
    assert (s, d, i) == (3, 0, 0)
    assert sum(x["kind"] == "substitution" for x in operations) == s
    assert sum(x["kind"] == "deletion" for x in operations) == d
    assert sum(x["kind"] == "insertion" for x in operations) == i
    metric = reference_metrics("a z d extra", ref("a b c d"))
    assert metric["wer"] == 0.75 and metric["reference_words"] == 4
    assert reference_metrics("CAFÉ,  I GO!", ref("cafe\u0301 I go"))["wer"] == 0
    assert reference_metrics("CAFÉ,  I GO!", ref("cafe\u0301 I go"))["cer"] == 0


def test_micro_sample_macro_and_independent_speaker_macro_are_distinct():
    a = reference_metrics(" ".join(["b"] * 2 + ["a"] * 98), ref(" ".join(["a"] * 100)))
    b = reference_metrics("no", ref("yes"))
    rows = [
        {
            "sample_id": sample,
            "candidate_id": "one-speaker",
            "status": "COMPLETE",
            "reference_status": "VERIFIED",
            "metrics": metric,
            "new_requests": 1,
            "cache_reused": False,
            "latency_ms": 100,
            "usage": [],
        }
        for sample, metric in (("a", a), ("b", b))
    ]
    summary = summarize_asr(rows)
    assert summary["micro_wer"] == 3 / 101
    assert summary["macro_sample_wer"] == 0.51
    assert summary["known_speakers"] == 1 and summary["samples"] == 2
    assert summary["reference_words"] == 101


@pytest.mark.parametrize(
    "kind,reference,hypothesis,start,end",
    [
        ("filler", "um I go", "I go", 0, 1),
        ("repetition", "I I go", "I go", 0, 2),
        ("self_correction", "I go I mean went", "I went", 1, 5),
        ("incorrect_grammar", "yesterday I go", "yesterday I went", 0, 3),
    ],
)
def test_learner_error_and_repair_preservation(kind, reference, hypothesis, start, end):
    value = ref(reference, [{"kind": kind, "start_token": start, "end_token": end}])
    assert reference_metrics(reference, value)["preservation"][kind]["recall"] == 1
    assert reference_metrics(hypothesis, value)["preservation"][kind]["recall"] == 0


def test_unverified_silence_uncertain_and_optional_untimed_coverage():
    value = ref("um")
    value.status = "DRAFT"
    assert reference_metrics("um", value)["wer"] is None
    assert reference_metrics("anything", ref(""))["wer"] is None
    assert reference_metrics("extra invented", ref("word"))["hallucinated_words"] == 1
    result = SimpleNamespace(
        words=[SimpleNamespace(start_ms=5, end_ms=4), SimpleNamespace(start_ms=None, end_ms=None)],
        utterances=[SimpleNamespace(start_ms=0, end_ms=None)],
        coverage=SimpleNamespace(stream_completed=False),
        uncertain_regions=[],
        error_code=None,
        limitations=[],
    )
    observed = coverage_metrics([result], 100)
    assert observed["word_timing_valid"] is False
    assert observed["word_timing_coverage"] == 0.5
    assert observed["recognized_window_ms"] == 0


def test_asr_static_readiness_has_no_openai_or_vad_requirement(monkeypatch):
    settings = Settings(
        _env_file=None,
        speaking_benchmark_research_enabled=True,
        speaking_benchmark_research_allow_live=True,
        speaking_asr_enabled=True,
        speaking_azure_key="fictional",
        speaking_azure_region="eastus",
        speaking_azure_billing_mode="free_only",
        speaking_ai_enabled=False,
    )
    monkeypatch.setattr("app.services.speaking_benchmark_research.find_spec", lambda _: object())
    assert not static_blockers(settings, {"provider": "azure_stt"}, "ASR_ONLY")


def test_gpu_holdout_and_every_provider_budget_require_separate_consent():
    experiment = SimpleNamespace(
        mode="ASR_ONLY",
        configuration={
            "requests": {"azure_pa": 1, "faster_whisper_modal": 1},
            "cohort": [{"split": "HOLDOUT"}],
        },
    )
    base = dict(
        provider_audio=True,
        estimates_usd={"azure_pa": 0.1, "faster_whisper_modal": 0.1},
        max_estimated_cost_usd=1,
    )
    with pytest.raises(AppError):
        check_consent(experiment, ResearchConsent(**base))
    with pytest.raises(AppError):
        check_consent(experiment, ResearchConsent(**base, modal_gpu=True))
    check_consent(experiment, ResearchConsent(**base, modal_gpu=True, holdout_evaluation=True))
    with pytest.raises(ValueError):
        ResearchConsent(**(base | {"max_estimated_cost_usd": 0.1}))
    with pytest.raises(ValueError):
        ResearchConsent(**(base | {"estimates_usd": {"azure_pa": float("nan")}}))


def test_paired_cannot_tune_pa_silence_and_scorer_simultaneously():
    from uuid import uuid4

    with pytest.raises(ValueError):
        ExperimentCreate(
            submission_key=uuid4(),
            name="Paired",
            mode="PAIRED_GRADING",
            cohort=[{"sample_id": uuid4(), "review_revision": 1, "segment_ids": ["s"]}],
            variants=[{"key": "x", "provider": "azure_pa", "silence_ms": 1000}],
            max_provider_audio_seconds=120,
            max_physical_requests=20,
        )


def test_remote_worker_and_cpu_images_do_not_assume_embedded_storage(monkeypatch):
    from pathlib import Path

    settings = Settings(
        _env_file=None,
        speaking_benchmark_execution="remote",
        speaking_benchmark_research_enabled=True,
        speaking_benchmark_research_allow_live=True,
    )
    assert "SPEAKING_BENCHMARK_REMOTE_REQUIRES_SHARED_STORAGE_AND_DATABASE" in static_blockers(
        settings, {"provider": "azure_pa"}, "ASR_ONLY"
    )
    root = Path(__file__).parents[2]
    docker = (root / "deploy/speaking-benchmark-research.Dockerfile").read_text()
    assert (
        "--extra speech" not in docker and "gpu=" not in docker and "faster-whisper>" not in docker
    )
    web = (root / "deploy/modal/app.py").read_text()
    assert '"faster-whisper"' not in web


def test_csv_export_is_formula_safe_and_omits_private_transcripts():
    from app.services.speaking_benchmark_research_reports import research_export

    report = {
        "schema_version": "v1",
        "rows": [
            {
                "code": "=SUM(A1:A2)",
                "reference_text": "PRIVATE_HUMAN",
                "text": "PRIVATE_HYPOTHESIS",
                "words": [{"text": "PRIVATE"}],
                "diff": [],
                "metrics": {"wer": 0.5},
                "band_comparison": {"human": {"overall": 6}, "ai": {"overall": 6.5}},
            }
        ],
        "outliers": [],
        "physical_requests": [],
    }
    csv = research_export(report, "csv")
    assert "'=SUM" in csv and "PRIVATE" not in csv
    assert "band_comparison" in csv
    assert "PRIVATE" not in research_export(report, "json")
