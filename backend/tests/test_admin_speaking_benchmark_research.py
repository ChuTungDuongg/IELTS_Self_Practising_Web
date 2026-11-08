"""Disposable PostgreSQL + synthetic audio. No paid providers, real model or network."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import AppError
from app.models.speaking_benchmark import SpeakingBenchmarkReview as Review
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRObservation as Observation
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRReference as Reference
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperiment as Experiment
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperimentVariant as Variant
from app.providers.speaking_asr.lexical import lexical_identity
from app.schemas.speaking_benchmark_research import (
    ExperimentCreate,
    ExperimentStart,
    ReconcileRequest,
    ReferenceVerify,
    ReferenceWrite,
    ResearchConsent,
)
from app.schemas.speech_analysis import (
    SpeechAnalysisResult,
    SpeechAnalysisSource,
    SpeechCapabilities,
    SpeechCoverage,
    SpeechUsage,
    SpeechUtterance,
)
from app.services.speaking_benchmark import SpeakingBenchmarkService
from app.services.speaking_benchmark_references import (
    reference_history,
    verify_reference,
    write_reference,
)
from app.services.speaking_benchmark_research import (
    cancel_experiment,
    create_experiment,
    experiment_preflight,
    reconcile_experiment,
    start_experiment,
)
from app.services.speaking_benchmark_research_ledger import ResearchLedger
from app.services.speaking_benchmark_research_metrics import (
    normalized_text,
    paired_difference,
    reference_metrics,
)
from app.services.speaking_benchmark_research_reports import research_export, research_report
from app.services.speaking_benchmark_research_worker import ResearchJobRunner


@pytest_asyncio.fixture
async def research_lab(grading_lab, monkeypatch):
    factory, settings, storage, owner, sample, run_id = grading_lab
    settings.speaking_benchmark_research_enabled = True
    settings.speaking_benchmark_research_allow_live = True
    settings.speaking_asr_enabled = True
    monkeypatch.setattr("app.services.speaking_benchmark_research.static_blockers", lambda *a: [])
    monkeypatch.setattr(
        "app.services.speaking_benchmark_research_worker.static_blockers", lambda *a: []
    )
    async with factory() as session, session.begin():
        (await session.get(Run, run_id)).status = "CANCELLED"
    try:
        yield grading_lab
    finally:
        async with factory() as session, session.begin():
            await session.execute(delete(Experiment).where(Experiment.owner_id == owner))


async def draft_experiment(lab, *, providers=("azure_pa", "azure_stt"), mode="ASR_ONLY"):
    factory, settings, storage, owner, sample, _ = lab
    async with factory() as session:
        async with session.begin():
            review = await session.get(Review, (sample, 1))
            windows = review.manifest["segments"]
        body = ExperimentCreate(
            submission_key=uuid4(),
            name="Synthetic research",
            mode=mode,
            cohort=[
                {
                    "sample_id": sample,
                    "review_revision": 1,
                    "segment_ids": [s["id"] for s in windows],
                }
            ],
            variants=[{"key": p, "provider": p} for p in providers],
            max_provider_audio_seconds=600,
            max_physical_requests=100,
        )
        experiment = await create_experiment(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage), body
        )
    return experiment


async def authorize(lab, experiment):
    factory, settings, storage, owner, _, _ = lab
    consent = ResearchConsent(
        provider_audio=True,
        llm_text=experiment.mode == "PAIRED_GRADING",
        estimates_usd={p: 0.1 for p in experiment.configuration["requests"]},
        max_estimated_cost_usd=2,
    )
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        ready = await experiment_preflight(service, experiment.id)
        assert ready["can_start"], ready
        return await start_experiment(
            service,
            experiment.id,
            ExperimentStart(preflight_fingerprint=ready["preflight_fingerprint"], consent=consent),
        )


async def add_reference(lab, *, text="um I I think yesterday I go", uncertainty=None):
    factory, settings, storage, owner, sample, _ = lab
    async with factory() as session:
        async with session.begin():
            review = await session.get(Review, (sample, 1))
            window = review.manifest["segments"][0]
            from app.models.speaking_benchmark import SpeakingBenchmarkSample

            sha = (await session.get(SpeakingBenchmarkSample, sample)).source_sha256
        body = ReferenceWrite(
            review_revision=1,
            expected_revision=0,
            source_sha256=sha,
            segment_id=window["id"],
            start_ms=window["start_ms"],
            end_ms=window["end_ms"],
            text=text,
            provenance="independent_human_transcriber",
            source_reference="Independent fictional transcription",
            annotations=[{"kind": "incorrect_grammar", "start_token": 4, "end_token": 7}]
            if len(text.split()) >= 7
            else [],
            uncertainty=uncertainty or [],
        )
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        draft = await write_reference(service, sample, body)
        verified = await verify_reference(
            service,
            sample,
            draft.id,
            ReferenceVerify(expected_revision=1, independently_reviewed=True),
        )
        return body, verified


def fake_factory(lab, calls, *, fail=False):
    factory, _, _, _, _, _ = lab

    class Fake:
        def __init__(self, settings, provider):
            self.identity = lexical_identity(settings, provider)
            self.provider = provider

        async def analyze(self, audio, **kwargs):
            async with factory() as session:
                active = list(
                    await session.scalars(
                        select(Observation).where(Observation.status == "ATTEMPTED")
                    )
                )
                assert len(active) == 1, "Physical submission requires committed ATTEMPTED"
            calls.append((self.provider, kwargs))
            assert "human" not in str(kwargs).lower() and "GROUND_TRUTH" not in str(kwargs)
            if fail:
                raise TimeoutError("never expose private provider message")
            from app.evaluation.speaking.replay_audio import pcm_digest

            text = (
                "um I I think yesterday I go"
                if self.provider == "azure_pa"
                else "I think yesterday I went"
            )
            return SpeechAnalysisResult(
                provider=self.identity,
                source=SpeechAnalysisSource(
                    audio_fingerprint=audio.source_audio_fingerprint,
                    normalized_audio_fingerprint=pcm_digest(audio),
                    duration_ms=audio.duration_ms,
                    **kwargs,
                ),
                status="COMPLETE",
                capabilities=SpeechCapabilities(),
                lexical_transcript=text,
                utterances=[
                    SpeechUtterance(
                        evidence_id="u", lexical_text=text, start_ms=0, end_ms=audio.duration_ms
                    )
                ],
                coverage=SpeechCoverage(audio_duration_ms=audio.duration_ms, stream_completed=True),
                usage=SpeechUsage(
                    attempted_calls=1,
                    submitted_audio_ms=audio.duration_ms,
                    successful_calls=1,
                    outcome="COMPLETED",
                ),
                latency_ms=100,
            )

    return Fake


async def test_references_append_only_binding_provenance_ownership(research_lab):
    factory, settings, storage, owner, sample, _ = research_lab
    body, verified = await add_reference(research_lab)
    assert verified.revision == 2 and verified.text == body.text
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        assert len(await reference_history(service, sample, 1)) == 2
        with pytest.raises(AppError, match="benchmark"):
            await write_reference(service, sample, body)
        with pytest.raises(AppError):
            await reference_history(
                SpeakingBenchmarkService(session, uuid4(), settings=settings, storage=storage),
                sample,
                1,
            )
        with pytest.raises(DBAPIError):
            async with session.begin():
                (await session.get(Reference, verified.id)).text = "overwrite"
                await session.flush()
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        changed = body.model_copy(update={"expected_revision": 2, "start_ms": body.start_ms + 1})
        with pytest.raises(AppError):
            await write_reference(service, sample, changed)
        ai = await write_reference(
            service,
            sample,
            body.model_copy(update={"expected_revision": 2, "provenance": "ai_draft"}),
        )
        with pytest.raises(AppError):
            await verify_reference(
                service,
                sample,
                ai.id,
                ReferenceVerify(expected_revision=3, independently_reviewed=True),
            )


async def test_offline_asr_vertical_cache_reference_refresh_and_exports(research_lab):
    factory, settings, storage, owner, sample, _ = research_lab
    body, verified = await add_reference(research_lab)
    experiment = await draft_experiment(research_lab)
    await authorize(research_lab, experiment)
    # No Luna configuration is required in ASR-only mode.
    settings.speaking_ai_enabled = False
    calls = []
    runner = ResearchJobRunner(
        factory, settings, storage=storage, analyzer_factory=fake_factory(research_lab, calls)
    )
    for _ in range(2):
        identifier, token = await runner.claim()
        await runner.execute(identifier, token)
    assert len(calls) == 6
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        report = await research_report(service, experiment.id)
        assert report["status"] == "COMPLETED"
        assert report["summary"]["azure_pa"]["wer"] == 0
        assert report["summary"]["azure_stt"]["wer"] > 0
        assert report["summary"]["azure_pa"]["human_labelled_samples"] == 1
        assert report["summary"]["azure_pa"]["unavailable_accuracy_responses"] == 2
        assert report["band_summary"] == {}
        assert '"text"' not in research_export(report, "json")
        draft = await write_reference(
            service,
            sample,
            body.model_copy(
                update={"expected_revision": 2, "text": "um I I think yesterday I went"}
            ),
        )
        await verify_reference(
            service,
            sample,
            draft.id,
            ReferenceVerify(expected_revision=3, independently_reviewed=True),
        )
        frozen = await research_report(service, experiment.id)
        latest = await research_report(service, experiment.id, latest_references=True)
        assert frozen["summary"]["azure_pa"]["wer"] == 0
        assert latest["summary"]["azure_pa"]["wer"] > 0
    second = await draft_experiment(research_lab)
    await authorize(research_lab, second)
    for _ in range(2):
        await runner.run_once()
    assert len(calls) == 6, "Exact source/config reuse has no physical request"
    async with factory() as session:
        report = await research_report(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage), second.id
        )
        assert sum(v["cache_hits"] for v in report["summary"].values()) == 6


async def test_uncertain_attempt_never_auto_retries_and_exact_reconciliation(research_lab):
    factory, settings, storage, owner, _, _ = research_lab
    experiment = await draft_experiment(research_lab, providers=("azure_pa",))
    await authorize(research_lab, experiment)
    calls = []
    runner = ResearchJobRunner(
        factory,
        settings,
        storage=storage,
        analyzer_factory=fake_factory(research_lab, calls, fail=True),
    )
    await runner.run_once()
    assert not await runner.run_once() and len(calls) == 1
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        report = await research_report(service, experiment.id)
        assert report["status"] == "INTERRUPTED"
        request = report["physical_requests"][0]
        assert request["status"] == "INTERRUPTED_BILLING_UNKNOWN"
        assert "private provider" not in str(report)
        consent = ResearchConsent(
            provider_audio=True, estimates_usd={"azure_pa": 0.2}, max_estimated_cost_usd=1
        )
        await reconcile_experiment(
            service,
            experiment.id,
            ReconcileRequest(
                preflight_fingerprint=experiment.fingerprint,
                observation_id=request["id"],
                reason="Operator reconciled test timeout",
                consent=consent,
            ),
        )
    runner.analyzer_factory = fake_factory(research_lab, calls)
    await runner.run_once()
    assert len(calls) == 4


async def test_atomic_claim_cancel_and_stale_lease_fencing(research_lab):
    factory, settings, storage, owner, _, _ = research_lab
    experiment = await draft_experiment(research_lab, providers=("azure_pa",))
    await authorize(research_lab, experiment)
    runner = ResearchJobRunner(factory, settings, storage=storage)
    claims = await asyncio.gather(runner.claim(), runner.claim())
    assert sum(c is not None for c in claims) == 1
    identifier, token = next(c for c in claims if c)
    ledger = ResearchLedger(factory, identifier, token)
    async with factory() as session, session.begin():
        row = await session.get(Variant, identifier)
        segment = row.windows[0]["id"]
    request_id, _ = await ledger.begin_or_reuse(segment, "f" * 64)
    async with factory() as session, session.begin():
        (await session.get(Variant, identifier)).lease_expires_at = datetime.now(UTC) - timedelta(
            seconds=2
        )
    assert await runner.claim() is None
    with pytest.raises(AppError):
        await ledger.begin_or_reuse(segment, "e" * 64)
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        await cancel_experiment(service, experiment.id)
    await runner.finish(identifier, token, "COMPLETED")
    async with factory() as session:
        assert (await session.get(Variant, identifier)).status == "CANCELLED"
        assert (await session.get(Observation, request_id)).status == "INTERRUPTED_BILLING_UNKNOWN"


async def test_paired_variants_wait_for_p2_without_weakening_uniqueness(research_lab):
    factory, settings, storage, owner, sample, _ = research_lab
    experiment = await draft_experiment(research_lab, mode="PAIRED_GRADING")
    await authorize(research_lab, experiment)
    runner = ResearchJobRunner(factory, settings, storage=storage)
    for _ in range(3):
        await runner.run_once()
    async with factory() as session:
        active = list(
            await session.scalars(
                select(Run).where(Run.sample_id == sample, Run.status == "PENDING")
            )
        )
        assert len(active) == 1
        assert (
            active[0].configuration["scorer"]
            == experiment.configuration["variants"][0]["grading"]["scorer"]
        )
        assert "references" not in str(active[0].configuration)
        assert not list(await session.scalars(select(Observation)))


@pytest.mark.parametrize("field,value", [("start_token", -1), ("end_token", 1000)])
def test_annotation_bounds_reject_invalid(field, value):
    with pytest.raises(ValueError):
        ReferenceWrite(
            review_revision=1,
            expected_revision=0,
            segment_id="s",
            source_sha256="a" * 64,
            start_ms=0,
            end_ms=100,
            text="I go",
            provenance="unverified",
            source_reference="",
            annotations=[
                {"kind": "incorrect_grammar", "start_token": 0, "end_token": 2} | {field: value}
            ],
        )


def test_metric_normalization_preservation_missing_and_cluster_threshold():
    reference = SimpleNamespace(
        status="VERIFIED",
        uncertainty=[],
        segment_id="s",
        source_sha256="a" * 64,
        start_ms=0,
        end_ms=100,
        text="Um, I I yesterday go",
        annotations=[{"kind": "incorrect_grammar", "start_token": 3, "end_token": 5}],
    )
    assert normalized_text("  YESTERDAY, I go. ") == "yesterday i go"
    values = reference_metrics("I yesterday went indeed", reference)
    assert values["missing_words"] > 0 and values["hallucinated_words"] >= 0
    assert values["preservation"]["filler"]["recall"] == 0
    assert values["preservation"]["repetition"]["recall"] == 0
    assert reference_metrics("anything", None)["wer"] is None
    reference.uncertainty = [{"kind": "unintelligible"}]
    assert reference_metrics("anything", reference)["wer"] is None
    assert paired_difference([("same", 0.5)] * 20)["ci95"] is None
    assert paired_difference([(f"speaker-{i}", 0.5) for i in range(10)])["ci95"] == [0.5, 0.5]


async def test_cross_owner_and_database_configuration_freeze(research_lab):
    factory, settings, storage, _, _, _ = research_lab
    experiment = await draft_experiment(research_lab)
    async with factory() as session:
        with pytest.raises(AppError):
            await research_report(
                SpeakingBenchmarkService(session, uuid4(), settings=settings, storage=storage),
                experiment.id,
            )
        with pytest.raises(DBAPIError):
            async with session.begin():
                (await session.get(Experiment, experiment.id)).configuration = {"forged": True}
                await session.flush()


async def test_full_paired_pipeline_reuses_pa_vad_and_keeps_human_data_out(
    research_lab, monkeypatch
):
    import json

    from test_speaking_ai import FEEDBACK, feature_bundle
    from test_speaking_hybrid_worker import Analyzer

    from app.models.speaking_benchmark import SpeakingBenchmarkHumanLabel as Label
    from app.models.speaking_benchmark_grading import (
        SpeakingBenchmarkGradingCheckpoint as Checkpoint,
    )
    from app.providers.writing_llm.base import Completion
    from app.providers.writing_llm.openai import OpenAIProvider
    from app.schemas.speaking_ai import AudioQualityResult
    from app.services.speaking_benchmark_grading_worker import GradingJobRunner
    from app.services.speaking_vad import VadResult

    factory, settings, storage, owner, sample, _ = research_lab
    await add_reference(research_lab, text="GROUND_TRUTH_SECRET um I I yesterday go")
    async with factory() as session, session.begin():
        session.add(
            Label(
                sample_id=sample,
                revision=1,
                overall=7,
                provenance="human_examiner",
                reference="independent human",
                verified=True,
                examiner="GROUND_TRUTH_SECRET",
                notes="GROUND_TRUTH_SECRET",
            )
        )
    experiment = await draft_experiment(research_lab, mode="PAIRED_GRADING")
    await authorize(research_lab, experiment)
    calls, vad_calls, llm_calls = [], [], []
    speech = Analyzer(settings)

    class Independent(Analyzer):
        def __init__(self, chosen):
            super().__init__(chosen)
            self.identity = lexical_identity(chosen, "azure_stt")

        async def analyze(self, audio, **kwargs):
            value = await super().analyze(audio, **kwargs)
            calls.append(kwargs)
            return value.model_copy(update={"lexical_transcript": "yesterday I go"})

    async def fake_vad(audio, chosen):
        vad_calls.append(audio.cache_key)
        return VadResult(available=True, spans=[(0, audio.duration_ms)])

    monkeypatch.setattr("app.services.speaking_vad.measure_vad_async", fake_vad)
    quality = AudioQualityResult.model_validate(feature_bundle()["quality"])
    monkeypatch.setattr(
        "app.services.speaking_features.assess_audio_quality",
        lambda audio, *a, **k: quality.model_copy(
            update={"source_audio_fingerprint": audio.source_audio_fingerprint}
        ),
    )
    monkeypatch.setattr(
        "app.services.speaking_benchmark_grading_worker.grading_availability",
        lambda _: {
            "can_queue": True,
            "providers": [{"provider": p, "available": True} for p in ("azure_pa", "azure_stt")],
        },
    )

    class FakeHTTP:
        async def send(self, body):
            async with factory() as session:
                attempts = list(
                    await session.scalars(
                        select(Checkpoint).where(
                            Checkpoint.provider == "openai", Checkpoint.status == "ATTEMPTED"
                        )
                    )
                )
                assert len(attempts) == 1
            assert "GROUND_TRUTH_SECRET" not in json.dumps(body)
            llm_calls.append(body)
            return Completion(
                json.dumps(
                    FEEDBACK
                    if "persisted_score" in body["messages"][-1]["content"]
                    else {"score": 6}
                ),
                {"total_tokens": 10},
                "stop",
            )

    def llm_factory(chosen):
        provider = OpenAIProvider(chosen)
        provider.transport = FakeHTTP()
        return provider

    researcher = ResearchJobRunner(factory, settings, storage=storage)
    grader = GradingJobRunner(
        factory,
        settings,
        storage=storage,
        pa_factory=lambda _: speech,
        lexical_factory=Independent,
        llm_factory=llm_factory,
    )
    for _ in range(10):
        async with factory() as session, session.begin():
            for row in await session.scalars(
                select(Variant).where(
                    Variant.experiment_id == experiment.id, Variant.status == "WAITING"
                )
            ):
                row.updated_at = datetime.now(UTC) - timedelta(seconds=10)
        await researcher.run_once()
        claim = await grader.claim()
        if claim:
            await grader.execute(*claim)
        async with factory() as session:
            if (await session.get(Experiment, experiment.id)).status in {"COMPLETED", "PARTIAL"}:
                break
    assert len(speech.calls) == 3, "PA stays reusable across lexical choices"
    assert len(vad_calls) == 3, "VAD timing is independent of lexical transcript"
    assert len(calls) == 3 and llm_calls
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        report = await research_report(service, experiment.id)
        assert report["status"] == "PARTIAL", "Missing PR/Overall remain unavailable"
        assert len({r["run_id"] for r in report["band_rows"]}) == 2
        assert report["band_summary"]["azure_pa"]["overall"]["failure_rate"] == 1
        assert report["physical_requests"] and all(
            r["provider"] != "cpu" for r in report["physical_requests"]
        )
        assert report["paired_bands"][0]["matched_samples"] == 0
        assert (await session.get(Experiment, experiment.id)).configuration["cohort"][0][
            "split"
        ] == "DEV"


async def test_deletion_fences_research_calls_and_preserves_private_cleanup(research_lab):
    from app.models.speaking import SpeakingMediaCleanup
    from app.models.speaking_benchmark import SpeakingBenchmarkSample

    factory, settings, storage, owner, sample, _ = research_lab
    experiment = await draft_experiment(research_lab, providers=("azure_pa",))
    await authorize(research_lab, experiment)
    runner = ResearchJobRunner(factory, settings, storage=storage)
    identifier, token = await runner.claim()
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        async with session.begin():
            revision = (await session.get(SpeakingBenchmarkSample, sample)).revision
        await service.delete(sample, revision)
    with pytest.raises(AppError):
        await runner.heartbeat(identifier, token)
    async with factory() as session:
        row = await session.get(SpeakingBenchmarkSample, sample)
        assert (
            row.deletion_pending_at
            and (await session.get(Variant, identifier)).status == "CANCELLED"
        )
        assert await session.scalar(
            select(SpeakingMediaCleanup.id).where(SpeakingMediaCleanup.storage_key == row.audio_key)
        )


async def test_research_routes_admin_owner_scope_and_no_inference(research_lab, monkeypatch):
    from teacher_helpers import api_client

    from app.models import User
    from app.models.enums import UserRole

    factory, settings, storage, owner, sample, _ = research_lab
    experiment = await draft_experiment(research_lab)

    def forbidden(*a, **k):
        raise AssertionError("HTTP/report paths cannot construct inference providers")

    monkeypatch.setattr(
        "app.providers.speech_analysis.azure.AzureSpeechAnalyzer.__init__", forbidden
    )
    root = "/api/v1/admin/speaking-benchmark"
    for role, actor_id in (
        (UserRole.USER, owner),
        (UserRole.ADMIN, uuid4()),
        (UserRole.ADMIN, owner),
    ):
        actor = User(
            id=actor_id,
            role=role,
            email="fictional@example.com",
            display_name="Synthetic",
            is_active=True,
            email_verified=True,
        )
        async with factory() as session, api_client(session, actor) as client:
            for endpoint in (
                f"/research/experiments/{experiment.id}",
                f"/research/experiments/{experiment.id}/results",
                f"/research/experiments/{experiment.id}/export.csv",
                f"/research/experiments/{experiment.id}/export.json",
                f"/samples/{sample}/asr-references?review_revision=1",
                f"/research/cohort?sample_id={sample}",
            ):
                response = await client.get(root + endpoint)
                expected = 403 if role == UserRole.USER else 404 if actor_id != owner else 200
                assert response.status_code == expected, (endpoint, response.text)


async def test_incomplete_stream_retains_text_but_not_reliable_accuracy(research_lab):
    factory, settings, storage, owner, _, _ = research_lab
    await add_reference(research_lab)
    experiment = await draft_experiment(research_lab, providers=("azure_pa",))
    await authorize(research_lab, experiment)
    calls = []
    base = fake_factory(research_lab, calls)

    class Partial(base):
        async def analyze(self, audio, **kwargs):
            result = await super().analyze(audio, **kwargs)
            return result.model_copy(
                update={
                    "status": "PARTIAL",
                    "coverage": result.coverage.model_copy(update={"stream_completed": False}),
                }
            )

    runner = ResearchJobRunner(factory, settings, storage=storage, analyzer_factory=Partial)
    await runner.run_once()
    assert not await runner.run_once() and len(calls) == 1
    async with factory() as session:
        report = await research_report(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            experiment.id,
        )
        row = next(r for r in report["rows"] if r["text"] is not None)
        assert row["status"] == "UNKNOWN" and row["metrics"]["wer"] is None
        assert row["coverage"]["stream_completed"] is False
        assert report["summary"]["azure_pa"]["unknown_billing_attempts"] == 1


async def test_concurrent_creation_is_idempotent_and_changed_configuration_is_rejected(
    research_lab,
):
    from app.schemas.speaking_benchmark_research import ProviderVariant
    from app.services.speaking_benchmark_research import provider_configuration

    factory, settings, storage, owner, sample, _ = research_lab
    async with factory() as session, session.begin():
        review = await session.get(Review, (sample, 1))
        ids = [s["id"] for s in review.manifest["segments"]]
    body = ExperimentCreate(
        submission_key=uuid4(),
        name="Idempotent research",
        mode="ASR_ONLY",
        cohort=[{"sample_id": sample, "review_revision": 1, "segment_ids": ids}],
        variants=[{"key": "azure_pa", "provider": "azure_pa"}],
        max_provider_audio_seconds=120,
        max_physical_requests=5,
    )

    async def create():
        async with factory() as session:
            return await create_experiment(
                SpeakingBenchmarkService(session, owner, settings=settings, storage=storage), body
            )

    first, second = await asyncio.gather(create(), create())
    assert first.id == second.id and first.status == "DRAFT"
    original = provider_configuration(
        settings, ProviderVariant(key="azure_pa", provider="azure_pa"), "ASR_ONLY"
    )
    settings.speaking_ai_prompt_version += "-new"
    assert (
        provider_configuration(
            settings, ProviderVariant(key="azure_pa", provider="azure_pa"), "ASR_ONLY"
        )
        == original
    )
    settings.speaking_azure_segmentation_silence_timeout_ms = 1500
    async with factory() as session:
        ready = await experiment_preflight(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage), first.id
        )
        assert (
            not ready["can_start"]
            and "SPEAKING_RESEARCH_CONFIGURATION_CHANGED" in ready["blockers"]
        )


async def test_cancelled_late_response_settles_accounting_only_and_completed_result_is_frozen(
    research_lab,
):
    factory, settings, storage, owner, _, _ = research_lab
    experiment = await draft_experiment(research_lab, providers=("azure_pa",))
    await authorize(research_lab, experiment)
    runner = ResearchJobRunner(factory, settings, storage=storage)
    identifier, token = await runner.claim()
    segment = experiment.variants[0].windows[0]["id"]
    ledger = ResearchLedger(factory, identifier, token)
    request, _ = await ledger.begin_or_reuse(segment, "f" * 64)
    async with factory() as session:
        await cancel_experiment(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            experiment.id,
        )
    await ledger.complete(request, {"safe_accounting_receipt": True}, {"submitted_audio_ms": 1})
    async with factory() as session:
        assert (await session.get(Observation, request)).status == "COMPLETED"
        assert (await session.get(Variant, identifier)).status == "CANCELLED"
        await session.rollback()
        with pytest.raises(DBAPIError):
            async with session.begin():
                (await session.get(Observation, request)).result = {"forged": True}
                await session.flush()


async def test_asr_and_p2_consumers_do_not_claim_the_same_sample(research_lab):
    from app.services.speaking_audio import fingerprint
    from app.services.speaking_benchmark_grading_worker import GradingJobRunner
    from app.services.speaking_benchmark_preflight import configuration

    factory, settings, storage, owner, sample, original_id = research_lab
    experiment = await draft_experiment(research_lab, providers=("azure_pa",))
    await authorize(research_lab, experiment)
    researcher = ResearchJobRunner(factory, settings, storage=storage)
    grader = GradingJobRunner(factory, settings, storage=storage)
    identifier, token = await researcher.claim()
    async with factory() as session, session.begin():
        original = await session.get(Run, original_id)
        config = configuration(settings, "azure_pa")
        session.add(
            Run(
                sample_id=sample,
                owner_id=owner,
                review_revision=1,
                source_sha256=original.source_sha256,
                manifest_fingerprint=original.manifest_fingerprint,
                config_fingerprint=fingerprint(config),
                submission_key=uuid4(),
                configuration=config,
                consent=original.consent,
                candidate_ms=original.candidate_ms,
                window_count=3,
            )
        )
    assert await grader.claim() is None
    await researcher.finish(identifier, token, "COMPLETED")
    assert await grader.claim() is not None


async def test_asr_waits_for_pending_p2_and_old_worker_cannot_finish_new_claim(research_lab):
    factory, settings, storage, owner, sample, original_id = research_lab
    from app.services.speaking_audio import fingerprint
    from app.services.speaking_benchmark_preflight import configuration

    async with factory() as session, session.begin():
        original = await session.get(Run, original_id)
        config = configuration(settings, "azure_pa")
        pending = Run(
            sample_id=sample,
            owner_id=owner,
            review_revision=1,
            source_sha256=original.source_sha256,
            manifest_fingerprint=original.manifest_fingerprint,
            config_fingerprint=fingerprint(config),
            submission_key=uuid4(),
            configuration=config,
            consent=original.consent,
            candidate_ms=original.candidate_ms,
            window_count=3,
        )
        session.add(pending)
        await session.flush()
        pending_id = pending.id
    experiment = await draft_experiment(research_lab, providers=("azure_pa",))
    await authorize(research_lab, experiment)
    researcher = ResearchJobRunner(factory, settings, storage=storage)
    assert await researcher.claim() is None
    async with factory() as session, session.begin():
        (await session.get(Run, pending_id)).status = "CANCELLED"
    first, old_token = await researcher.claim()
    async with factory() as session, session.begin():
        (await session.get(Variant, first)).lease_expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
    second, new_token = await researcher.claim()
    assert first == second and old_token != new_token
    await researcher.finish(first, old_token, "COMPLETED")
    async with factory() as session:
        row = await session.get(Variant, second)
        assert row.status == "RUNNING" and row.lease_token == new_token


async def test_process_shutdown_preserves_unknown_request_without_replay(research_lab):
    factory, settings, storage, owner, _, _ = research_lab
    experiment = await draft_experiment(research_lab, providers=("azure_pa",))
    await authorize(research_lab, experiment)
    submitted = asyncio.Event()

    class BlockedProvider:
        def __init__(self, *_):
            pass

        async def analyze(self, audio, **kwargs):
            async with factory() as session:
                assert await session.scalar(
                    select(Observation.id).where(Observation.status == "ATTEMPTED")
                )
            submitted.set()
            await asyncio.Future()

    worker = ResearchJobRunner(factory, settings, storage=storage, analyzer_factory=BlockedProvider)
    task = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(submitted.wait(), timeout=30)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with factory() as session:
        report = await research_report(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            experiment.id,
        )
        assert report["status"] == "INTERRUPTED"
        assert report["physical_requests"][0]["status"] == "INTERRUPTED_BILLING_UNKNOWN"
    assert not await worker.run_once()


async def test_unlinked_paired_variant_cannot_report_historical_provider_output(research_lab):
    from app.models.speaking_benchmark_grading import (
        SpeakingBenchmarkGradingCheckpoint as Checkpoint,
    )

    factory, settings, storage, owner, _, old_run_id = research_lab
    experiment = await draft_experiment(
        research_lab, providers=("azure_pa",), mode="PAIRED_GRADING"
    )
    variant = experiment.variants[0]
    window = variant.windows[0]
    result = SpeechAnalysisResult(
        provider=lexical_identity(settings, "azure_pa"),
        source=SpeechAnalysisSource(
            audio_fingerprint=experiment.configuration["cohort"][0]["source_sha256"],
            normalized_audio_fingerprint="b" * 64,
            duration_ms=window["end_ms"] - window["start_ms"],
        ),
        status="COMPLETE",
        capabilities=SpeechCapabilities(),
        lexical_transcript="unrelated historical hypothesis",
        coverage=SpeechCoverage(
            audio_duration_ms=window["end_ms"] - window["start_ms"], stream_completed=True
        ),
    )
    async with factory() as session, session.begin():
        session.add(
            Checkpoint(
                run_id=old_run_id,
                stage=f"azure:{window['id']}",
                provider="azure-speech",
                identity="e" * 64,
                attempt=1,
                status="COMPLETED",
                billing_state="OBSERVED",
                result=result.model_dump(mode="json"),
            )
        )
    async with factory() as session:
        report = await research_report(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            experiment.id,
        )
    assert all(row["text"] is None for row in report["rows"])
    assert report["summary"]["azure_pa"]["missing_or_failed_results"] == 3


async def test_paired_unknown_billing_is_visible_in_provider_summary(research_lab):
    from app.models.speaking_benchmark_grading import (
        SpeakingBenchmarkGradingCheckpoint as Checkpoint,
    )

    factory, settings, storage, owner, _, _ = research_lab
    experiment = await draft_experiment(
        research_lab, providers=("azure_pa",), mode="PAIRED_GRADING"
    )
    await authorize(research_lab, experiment)
    await ResearchJobRunner(factory, settings, storage=storage).run_once()
    async with factory() as session, session.begin():
        variant = await session.get(Variant, experiment.variants[0].id)
        session.add(
            Checkpoint(
                run_id=variant.grading_run_id,
                stage="azure:uncertain",
                provider="azure-speech",
                identity="e" * 64,
                attempt=1,
                status="INTERRUPTED_BILLING_UNKNOWN",
                billing_state="UNKNOWN",
            )
        )
    async with factory() as session:
        report = await research_report(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            experiment.id,
        )
    assert report["summary"]["azure_pa"]["unknown_billing_attempts"] == 1
    assert report["summary"]["azure_pa"]["unknown_usage_requests"] == 1


async def test_paired_cancellation_survives_crash_after_first_commit(research_lab):
    from sqlalchemy import event

    from app.services.speaking_benchmark_grading_worker import GradingJobRunner
    from app.services.speaking_benchmark_ledger import RequestLedger

    factory, settings, storage, owner, _, _ = research_lab
    experiment = await draft_experiment(
        research_lab, providers=("azure_pa",), mode="PAIRED_GRADING"
    )
    await authorize(research_lab, experiment)
    await ResearchJobRunner(factory, settings, storage=storage).run_once()
    run_id, token = await GradingJobRunner(factory, settings, storage=storage).claim()
    ledger = RequestLedger(factory, run_id, token)
    attempt = await ledger.begin("azure:one", "azure-speech", "a" * 64)

    def crash_after_commit(_):
        raise RuntimeError("simulated crash after commit")

    async with factory() as session:
        event.listen(session.sync_session, "after_commit", crash_after_commit, once=True)
        with pytest.raises(RuntimeError, match="simulated crash"):
            await cancel_experiment(
                SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
                experiment.id,
            )
    async with factory() as session:
        assert (await session.get(Experiment, experiment.id)).status == "CANCELLED"
        assert (await session.get(Run, run_id)).status == "CANCELLED"
        from app.models.speaking_benchmark_grading import (
            SpeakingBenchmarkGradingCheckpoint as Checkpoint,
        )

        assert (await session.get(Checkpoint, attempt)).status == "INTERRUPTED_BILLING_UNKNOWN"
    with pytest.raises(AppError, match="LEASE_LOST"):
        await ledger.begin("azure:two", "azure-speech", "b" * 64)


async def test_paired_recovery_preserves_physical_request_attribution(research_lab):
    from app.schemas.speaking_benchmark_grading import RetryRequest
    from app.services.speaking_benchmark_grading import retry_interrupted
    from app.services.speaking_benchmark_grading_worker import GradingJobRunner
    from app.services.speaking_benchmark_ledger import RequestLedger

    factory, settings, storage, owner, sample_id, _ = research_lab
    experiment = await draft_experiment(
        research_lab, providers=("azure_pa",), mode="PAIRED_GRADING"
    )
    await authorize(research_lab, experiment)
    await ResearchJobRunner(factory, settings, storage=storage).run_once()
    grader = GradingJobRunner(factory, settings, storage=storage)
    run_id, token = await grader.claim()
    ledger = RequestLedger(factory, run_id, token)
    attempt = await ledger.begin("azure:one", "azure-speech", "a" * 64)
    await ledger.interrupt(attempt, "TIMEOUT")
    await grader.finish(run_id, token)
    body = RetryRequest(
        checkpoint_id=attempt,
        reconciliation="Operator checked the synthetic uncertain request",
        consent={
            "azure_audio": True,
            "llm_text": True,
            "estimates_usd": {"azure_pa": 0.1, "openai": 0.1},
            "max_estimated_cost_usd": 1,
        },
    )
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        await retry_interrupted(service, sample_id, run_id, body)
        report = await research_report(service, experiment.id)
    assert report["summary"]["azure_pa"]["new_requests"] == 1
    assert report["physical_requests"][0]["reused_artifact"] is False
    async with factory() as session:
        assert (await session.get(Run, run_id)).consent["research_experiment"] == str(experiment.id)


async def test_provider_disagreement_uses_declared_unicode_normalization(research_lab):
    factory, settings, storage, owner, _, _ = research_lab
    experiment = await draft_experiment(research_lab)
    await authorize(research_lab, experiment)
    base = fake_factory(research_lab, [])

    class UnicodeProvider(base):
        async def analyze(self, audio, **kwargs):
            result = await super().analyze(audio, **kwargs)
            return result.model_copy(
                update={
                    "lexical_transcript": "CAFÉ" if self.provider == "azure_pa" else "cafe\u0301"
                }
            )

    runner = ResearchJobRunner(factory, settings, storage=storage, analyzer_factory=UnicodeProvider)
    while await runner.run_once():
        pass
    async with factory() as session:
        report = await research_report(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            experiment.id,
        )
    assert len(report["disagreement"]) == 3
    assert all(row["word_edit_distance"] == 0 for row in report["disagreement"])
