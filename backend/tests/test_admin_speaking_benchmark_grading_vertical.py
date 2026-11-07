"""A real PostgreSQL/FFmpeg/production scorer path, fake speech/HTTP/VAD only."""

import json

from sqlalchemy import select
from test_speaking_ai import FEEDBACK
from test_speaking_hybrid_worker import Analyzer

from app.models.speaking_benchmark import SpeakingBenchmarkHumanLabel as Label
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.providers.writing_llm.base import Completion
from app.providers.writing_llm.openai import OpenAIProvider
from app.schemas.speaking_benchmark_reports import ReportFilters
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark import SpeakingBenchmarkService
from app.services.speaking_benchmark_grading_worker import GradingJobRunner
from app.services.speaking_benchmark_preflight import configuration
from app.services.speaking_benchmark_reports import report
from app.services.speaking_vad import VadResult


async def test_persistent_offline_evaluation_and_label_edits_never_reinfer(
    grading_lab, monkeypatch
):
    factory, settings, storage, owner, sample, run_id = grading_lab
    settings.speaking_azure_billing_mode = "free_only"
    settings.speaking_ai_enabled = True
    settings.ai_writing_openai_api_key = "fictional-offline-key"
    settings.speaking_ai_provider = "openai"
    settings.speaking_ai_model = "gpt-6-luna"

    async def fake_vad(audio, settings):
        return VadResult(available=True, spans=[(0, audio.duration_ms)])

    monkeypatch.setattr("app.services.speaking_vad.measure_vad_async", fake_vad)
    # The fixture uses deliberately quiet constant PCM. Exercise the production
    # feature builder while supplying a deterministic accepted quality measurement.
    from test_speaking_ai import feature_bundle

    from app.schemas.speaking_ai import AudioQualityResult

    quality = AudioQualityResult.model_validate(feature_bundle()["quality"])
    monkeypatch.setattr(
        "app.services.speaking_features.assess_audio_quality",
        lambda audio, *a, **k: quality.model_copy(
            update={"source_audio_fingerprint": audio.source_audio_fingerprint}
        ),
    )
    speech = Analyzer(settings)
    sent = []

    class FakeHTTP:
        async def send(self, body):
            from app.models.speaking_benchmark_grading import (
                SpeakingBenchmarkGradingCheckpoint as Checkpoint,
            )

            async with factory() as observer:
                attempts = list(
                    await observer.scalars(
                        select(Checkpoint).where(
                            Checkpoint.run_id == run_id,
                            Checkpoint.provider == "openai",
                            Checkpoint.status == "ATTEMPTED",
                        )
                    )
                )
                assert len(attempts) == 1, (
                    "Physical POST must observe a previously committed attempt"
                )
            sent.append(body)
            assert "GROUND_TRUTH_SECRET" not in json.dumps(body)
            feedback = "persisted_score" in body["messages"][-1]["content"]
            return Completion(
                json.dumps(FEEDBACK if feedback else {"score": 6}), {"total_tokens": 10}, "stop"
            )

    def provider_factory(chosen):
        provider = OpenAIProvider(chosen)
        provider.transport = FakeHTTP()
        return provider

    config = configuration(settings, "azure_pa")
    async with factory() as session, session.begin():
        row = await session.get(Run, run_id)
        row.configuration, row.config_fingerprint = config, fingerprint(config)
        session.add(
            Label(
                sample_id=sample,
                revision=1,
                fc=None,
                lr=6,
                gra=6.5,
                pr=None,
                overall=7,
                provenance="human_examiner",
                reference="Independent fictional examiner",
                verified=True,
                examiner="GROUND_TRUTH_SECRET",
                notes="GROUND_TRUTH_SECRET",
            )
        )
    worker = GradingJobRunner(
        factory,
        settings,
        storage=storage,
        pa_factory=lambda _: speech,
        llm_factory=provider_factory,
    )
    monkeypatch.setattr(
        "app.services.speaking_benchmark_grading_worker.grading_availability",
        lambda _: {"can_queue": True, "providers": [{"provider": "azure_pa", "available": True}]},
    )
    identifier, token = await worker.claim()
    await worker.execute(identifier, token)
    async with factory() as session:
        row = await session.get(Run, run_id)
        assert row.status == "PARTIAL"
        assert row.prediction["bands"]["lr"] == 6
        assert row.prediction["bands"]["gra"] == 6
        assert row.prediction["bands"]["pr"] is None
        assert row.prediction["bands"]["overall"] is None
        frozen = row.prediction
    assert len(speech.calls) == 3
    assert sent
    count = len(sent)
    async with factory() as session:
        summary, rows = await report(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            ReportFilters(),
        )
        assert summary["criteria"]["gra"]["mae"] == 0.5
    async with factory() as session, session.begin():
        session.add(
            Label(
                sample_id=sample,
                revision=2,
                lr=7,
                gra=7,
                overall=8,
                provenance="human_examiner",
                reference="Second independently entered fictional label",
                verified=True,
                examiner="",
                notes="",
            )
        )
    async with factory() as session:
        summary, rows = await report(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            ReportFilters(),
        )
        assert summary["criteria"]["gra"]["mae"] == 1
        assert rows[0]["label_revision"] == 2
        assert (await session.get(Run, run_id)).prediction == frozen
    assert len(sent) == count
    from uuid import uuid4

    settings.speaking_ai_prompt_version += "-offline-next"
    config = configuration(settings, "azure_pa")
    async with factory() as session, session.begin():
        old = await session.get(Run, run_id)
        new = Run(
            sample_id=sample,
            owner_id=owner,
            review_revision=old.review_revision,
            source_sha256=old.source_sha256,
            manifest_fingerprint=old.manifest_fingerprint,
            config_fingerprint=fingerprint(config),
            configuration=config,
            submission_key=uuid4(),
            consent=old.consent,
            candidate_ms=old.candidate_ms,
            window_count=old.window_count,
        )
        session.add(new)
        await session.flush()
        new_id = new.id
    run_id, token = await worker.claim()
    assert run_id == new_id
    await worker.execute(run_id, token)
    assert len(speech.calls) == 3, "Prompt-only changes must not resubmit Azure"
    assert len(sent) > count
