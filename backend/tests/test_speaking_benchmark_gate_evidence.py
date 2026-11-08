"""Gate evidence includes failed attempts and exact linked P2 lexical stages."""

from types import SimpleNamespace
from uuid import uuid4

from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingCheckpoint as Checkpoint
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.schemas.speaking_benchmark_quality import PersistedSelection, SuiteCreate
from app.schemas.speech_analysis import (
    SpeechAnalysisResult,
    SpeechAnalysisSource,
    SpeechCapabilities,
    SpeechCoverage,
    SpeechUsage,
    SpeechUtterance,
)
from app.services.speaking_benchmark import SpeakingBenchmarkService
from app.services.speaking_benchmark_gate_evidence import (
    collect_persisted_evidence,
    lexical_metrics,
)
from app.services.speaking_benchmark_quality import create_suite


def test_retry_authorization_does_not_erase_unknown_physical_billing():
    from app.services.speaking_benchmark_gate_evidence import request_metrics

    request = SimpleNamespace(
        provider="azure_stt",
        status="INTERRUPTED_BILLING_UNKNOWN",
        reused_from=None,
        reconciliation={"reason": "one replacement authorized"},
        usage=None,
    )
    assert request_metrics([request])["unknown_billing_attempts"] == 1


async def test_bounded_cer_unavailability_is_not_zero_error():
    from app.core.config import Settings
    from app.providers.speaking_asr.lexical import lexical_identity

    identity = lexical_identity(Settings(_env_file=None), "azure_stt").model_dump(mode="json")
    sample_id, ref_id = uuid4(), uuid4()
    reference = SimpleNamespace(
        status="VERIFIED",
        uncertainty=[],
        segment_id="one",
        sample_id=sample_id,
        source_sha256="a" * 64,
        review_revision=1,
        manifest_fingerprint="b" * 64,
        start_ms=0,
        end_ms=1000,
        revision=1,
        text="x" * 2500,
        annotations=[],
    )

    class Session:
        async def get(self, *args):
            return reference

    sample = dict(
        sample_id=str(sample_id),
        source_sha256="a" * 64,
        review_revision=1,
        manifest_fingerprint="b" * 64,
        windows=[{"id": "one", "start_ms": 0, "end_ms": 1000}],
        references=[{"id": str(ref_id), "segment_id": "one", "eligible": True, "revision": 1}],
    )
    result = SpeechAnalysisResult(
        provider=identity,
        source=SpeechAnalysisSource(
            audio_fingerprint="a" * 64, normalized_audio_fingerprint="c" * 64, duration_ms=1000
        ),
        status="COMPLETE",
        capabilities=SpeechCapabilities(),
        lexical_transcript=reference.text,
        coverage=SpeechCoverage(audio_duration_ms=1000, stream_completed=True),
        usage=SpeechUsage(
            attempted_calls=1, submitted_audio_ms=1000, successful_calls=1, outcome="COMPLETED"
        ),
    )
    metrics, errors = await lexical_metrics(
        Session(),
        sample,
        {"one": SimpleNamespace(status="COMPLETED", result=result.model_dump(mode="json"))},
        identity,
    )
    assert not errors and metrics["wer"] == 0
    assert metrics["cer"] is None


async def test_failed_run_retains_unknown_attempts_and_consumed_identity(grading_lab):
    factory, settings, storage, owner, sample, run_id = grading_lab
    async with factory() as session, session.begin():
        run = await session.get(Run, run_id)
        run.status = "FAILED"
        config_fp = run.config_fingerprint
        request = Checkpoint(
            run_id=run_id,
            stage="azure:missing",
            provider="azure_pa",
            identity="a" * 64,
            attempt=1,
            status="INTERRUPTED_BILLING_UNKNOWN",
            billing_state="UNKNOWN",
        )
        session.add(request)
        await session.flush()
        request_id = request.id
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        suite = await create_suite(
            service,
            SuiteCreate(
                name="Synthetic evidence", cohort=[{"sample_id": sample, "review_revision": 1}]
            ),
        )
        async with session.begin():
            evidence = await collect_persisted_evidence(
                service,
                suite,
                PersistedSelection(kind="GRADING", configuration_fingerprint=config_fp),
            )
        row = evidence["rows"][0]
        assert row["available"] is False
        assert row["metrics"]["unknown_billing_attempts"] == 1
        assert str(request_id) in row["request_ids"]
        assert row["run_id"] == str(run_id)
        assert (
            evidence["configuration"]["rubric_version"]
            == run.configuration["scorer"]["rubric_version"]
        )


async def test_window_at_zero_keeps_actual_duration_and_requires_all_windows():
    from app.core.config import Settings
    from app.providers.speaking_asr.lexical import lexical_identity

    identity = lexical_identity(Settings(_env_file=None), "azure_stt").model_dump(mode="json")
    sample = dict(
        sample_id=str(uuid4()),
        source_sha256="a" * 64,
        review_revision=1,
        manifest_fingerprint="b" * 64,
        windows=[
            {"id": "first", "start_ms": 0, "end_ms": 5000},
            {"id": "second", "start_ms": 5000, "end_ms": 10000},
        ],
        references=[],
    )
    result = SpeechAnalysisResult(
        provider=identity,
        source=SpeechAnalysisSource(
            audio_fingerprint="a" * 64, normalized_audio_fingerprint="c" * 64, duration_ms=5000
        ),
        status="COMPLETE",
        capabilities=SpeechCapabilities(),
        lexical_transcript="fictional response",
        utterances=[
            SpeechUtterance(
                evidence_id="u", lexical_text="fictional response", start_ms=0, end_ms=5000
            )
        ],
        coverage=SpeechCoverage(audio_duration_ms=5000, stream_completed=True),
        usage=SpeechUsage(
            attempted_calls=1, submitted_audio_ms=5000, successful_calls=1, outcome="COMPLETED"
        ),
        latency_ms=100,
    )
    request = SimpleNamespace(status="COMPLETED", result=result.model_dump(mode="json"))
    metrics, errors = await lexical_metrics(None, sample, {"first": request}, identity)
    assert not errors
    assert metrics["failure_rate"] == 0.5
    assert metrics["recognition_coverage"] == 0.5
    assert metrics["wer"] is None and metrics["real_time_factor"] is None
    _, errors = await lexical_metrics(None, sample, {"first": request}, {"provider": "wrong"})
    assert errors == ["PROVIDER_RESULT_BINDING_MISMATCH"]


async def test_paired_gate_reads_linked_p2_stages_without_p3_observations(grading_lab):
    from sqlalchemy import select
    from test_admin_speaking_benchmark_research import draft_experiment

    from app.models.speaking_benchmark_research import SpeakingBenchmarkExperimentVariant as Variant

    factory, settings, storage, owner, sample, run_id = grading_lab
    experiment = await draft_experiment(grading_lab, providers=("azure_pa",), mode="PAIRED_GRADING")
    async with factory() as session:
        svc = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        suite = await create_suite(
            svc,
            SuiteCreate(name="Paired source", cohort=[{"sample_id": sample, "review_revision": 1}]),
        )
    async with factory() as session, session.begin():
        run = await session.get(Run, run_id)
        variant = await session.scalar(
            select(Variant).where(Variant.experiment_id == experiment.id)
        )
        run.status, run.prediction = "COMPLETED", {"bands": {"fc": 6, "overall": None}}
        variant.status, variant.grading_run_id = "COMPLETED", run.id
        for window in suite.configuration["samples"][0]["windows"]:
            duration = window["end_ms"] - window["start_ms"]
            result = SpeechAnalysisResult(
                provider=run.configuration["lexical"],
                source=SpeechAnalysisSource(
                    audio_fingerprint=run.source_sha256,
                    normalized_audio_fingerprint="d" * 64,
                    duration_ms=duration,
                ),
                status="COMPLETE",
                capabilities=SpeechCapabilities(),
                lexical_transcript="fictional answer",
                coverage=SpeechCoverage(audio_duration_ms=duration, stream_completed=True),
                usage=SpeechUsage(
                    attempted_calls=1,
                    submitted_audio_ms=duration,
                    successful_calls=1,
                    outcome="COMPLETED",
                ),
                latency_ms=10,
            )
            session.add(
                Checkpoint(
                    run_id=run.id,
                    stage="azure:" + window["id"],
                    provider="azure_pa",
                    identity="e" * 64,
                    attempt=1,
                    status="COMPLETED",
                    billing_state="OBSERVED",
                    result=result.model_dump(mode="json"),
                    usage=result.usage.model_dump(mode="json"),
                )
            )
    async with factory() as session, session.begin():
        evidence = await collect_persisted_evidence(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            suite,
            PersistedSelection(kind="EXPERIMENT", id=experiment.id, variant_key="azure_pa"),
        )
        row = evidence["rows"][0]
        assert row["available"] and row["metrics"]["failure_rate"] == 0
        assert row["metrics"]["latency_ms"] == 30
        assert row["ai"]["fc"] == 6 and row["ai"]["overall"] is None
        assert len(row["request_ids"]) == 3 and not evidence["invalid_reasons"]
