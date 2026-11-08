"""Durable P4 tests on disposable PostgreSQL with fictional audio and fake ASR."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import AppError
from app.models.speaking_benchmark import SpeakingBenchmarkReview as Review
from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_questions import SpeakingBenchmarkQuestionJob as Job
from app.models.speaking_benchmark_questions import SpeakingBenchmarkQuestionRequest as Request
from app.providers.speaking_asr.lexical import lexical_identity
from app.schemas.speaking_benchmark import ReviewPatch
from app.schemas.speaking_benchmark_questions import (
    QuestionConsent,
    QuestionDecisions,
    QuestionJobCreate,
    QuestionReconcile,
    QuestionStart,
)
from app.schemas.speech_analysis import (
    SpeechAnalysisResult,
    SpeechAnalysisSource,
    SpeechCapabilities,
    SpeechCoverage,
    SpeechUsage,
)
from app.services import speaking_benchmark_questions as questions
from app.services.speaking_benchmark import SpeakingBenchmarkService
from app.services.speaking_benchmark_questions_ledger import QuestionLedger
from app.services.speaking_benchmark_questions_worker import QuestionJobRunner


@pytest_asyncio.fixture
async def question_lab(grading_lab, monkeypatch):
    factory, settings, storage, owner, sample, _ = grading_lab
    settings.speaking_benchmark_questions_enabled = True
    settings.speaking_benchmark_questions_allow_live = True
    settings.speaking_asr_enabled = True
    monkeypatch.setattr(questions, "static_blockers", lambda *a: [])
    monkeypatch.setattr(
        "app.services.speaking_benchmark_questions_worker.static_blockers", lambda *a: []
    )
    # An unapproved P1 revision is the real input. No fake candidate manifest/approval.
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        review = await service.review(sample)
        draft = review.draft.model_copy(deep=True)
        for segment in draft.segments:
            segment.prompt_verified = False
            segment.prompt_text = ""
        await service.save_review(sample, ReviewPatch(expected_revision=1, draft=draft))
    yield grading_lab


async def create(lab, *, window_ids=None):
    factory, settings, storage, owner, sample, _ = lab
    async with factory() as session:
        return await questions.create_job(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            sample,
            QuestionJobCreate(
                submission_key=uuid4(),
                review_revision=2,
                examiner_speaker_id="examiner",
                examiner_confirmed=True,
                window_ids=window_ids or ["t0"],
            ),
        )


def consent():
    return QuestionConsent(
        provider_audio=True, estimates_usd={"azure_stt": 0.1}, max_estimated_cost_usd=1
    )


async def start(lab, job):
    factory, settings, storage, owner, sample, _ = lab
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        ready = await questions.preflight(service, sample, job.id)
        assert ready["can_start"]
        return await questions.start_job(
            service,
            sample,
            job.id,
            QuestionStart(preflight_fingerprint=ready["preflight_fingerprint"], consent=consent()),
        )


def analyzer(lab, calls, *, fail=False, entered=None, release=None):
    factory, *_ = lab

    class Fake:
        def __init__(self, settings, provider):
            self.identity = lexical_identity(settings, provider)

        async def analyze(self, audio, **kwargs):
            async with factory() as session:
                rows = list(
                    await session.scalars(select(Request).where(Request.status == "ATTEMPTED"))
                )
                assert len(rows) == 1, "ATTEMPTED must commit before the physical request"
                assert rows[0].identity and rows[0].window_id == "t0"
            calls.append(kwargs)
            if entered:
                entered.set()
                await release.wait()
            if fail:
                raise TimeoutError("Fictional private provider diagnostic")
            from app.evaluation.speaking.replay_audio import pcm_digest

            return SpeechAnalysisResult(
                provider=self.identity,
                source=SpeechAnalysisSource(
                    audio_fingerprint=audio.source_audio_fingerprint,
                    normalized_audio_fingerprint=pcm_digest(audio),
                    duration_ms=audio.duration_ms,
                    **kwargs,
                ),
                status="COMPLETE",
                lexical_transcript="Where is the fictional village?",
                coverage=SpeechCoverage(audio_duration_ms=audio.duration_ms, stream_completed=True),
                capabilities=SpeechCapabilities(),
                usage=SpeechUsage(
                    attempted_calls=1,
                    submitted_audio_ms=audio.duration_ms,
                    successful_calls=1,
                    outcome="COMPLETED",
                ),
            )

    return Fake


async def test_preapproval_question_lifecycle_creates_draft_preserves_approval(question_lab):
    factory, settings, storage, owner, sample, _ = question_lab
    calls = []
    job = await create(question_lab)
    assert job.status == "DRAFT" and not job.requests
    await start(question_lab, job)
    assert calls == [], "Read/create/preflight/start must not execute ASR"
    runner = QuestionJobRunner(
        factory, settings, storage=storage, analyzer_factory=analyzer(question_lab, calls)
    )
    assert await runner.run_once()
    assert len(calls) == 1
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        async with session.begin():
            row = await questions.owned_job(service, sample, job.id)
            value = await questions.dto(session, row)
            first_manifest = (await session.get(Review, (sample, 1))).manifest
        assert value.status == "COMPLETED"
        assert value.proposals[0].human_verification_status == "PENDING"
        assert value.requests[0].billing_state == "OBSERVED"
        accepted = await questions.decide(
            service,
            sample,
            job.id,
            QuestionDecisions(
                expected_review_revision=2,
                expected_decision_count=0,
                independently_reviewed=True,
                decisions=[{"proposal_id": "t0", "action": "ACCEPT"}],
            ),
        )
        assert accepted.decisions[0]["created_review_revision"] == 3
        review = await service.review(sample)
        assert review.revision == 3 and review.approved_at is None and review.manifest is None
        assert review.draft.segments[0].prompt_verified
        assert review.draft.segments[0].prompt_text == "Where is the fictional village?"
        async with session.begin():
            assert (await session.get(Review, (sample, 1))).manifest == first_manifest
            assert (await session.get(Sample, sample)).status == "REVIEW"


async def test_unknown_requires_exact_reconciliation_not_automatic_retry(question_lab):
    factory, settings, storage, owner, sample, _ = question_lab
    job = await create(question_lab)
    await start(question_lab, job)
    calls = []
    runner = QuestionJobRunner(
        factory,
        settings,
        storage=storage,
        analyzer_factory=analyzer(question_lab, calls, fail=True),
    )
    assert await runner.run_once()
    assert not await runner.run_once()
    assert len(calls) == 1
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        async with session.begin():
            row = await session.get(Job, job.id)
            request = await session.scalar(select(Request).where(Request.job_id == job.id))
            assert row.status == "INTERRUPTED" and request.status == "INTERRUPTED_BILLING_UNKNOWN"
            request_id = request.id
        with pytest.raises(AppError, match="RECONCILIATION_MISMATCH"):
            await questions.reconcile_job(
                service,
                sample,
                job.id,
                QuestionReconcile(
                    preflight_fingerprint=job.fingerprint,
                    consent=consent(),
                    request_id=uuid4(),
                    reason="Fictional explicit retry consent",
                ),
            )
        await questions.reconcile_job(
            service,
            sample,
            job.id,
            QuestionReconcile(
                preflight_fingerprint=job.fingerprint,
                consent=consent(),
                request_id=request_id,
                reason="Fictional explicit retry consent",
            ),
        )
    runner.analyzer_factory = analyzer(question_lab, calls)
    assert await runner.run_once()
    assert len(calls) == 2
    async with factory() as session:
        job_row = await session.get(Job, job.id)
        requests = list(
            await session.scalars(
                select(Request).where(Request.job_id == job.id).order_by(Request.attempt)
            )
        )
        assert job_row.status == "COMPLETED"
        assert requests[0].status == "INTERRUPTED_BILLING_UNKNOWN"
        assert requests[0].reconciliation["replacement_id"] == str(requests[1].id)
        assert requests[1].status == "COMPLETED"


async def test_lease_expiry_fences_request_and_never_auto_retries(question_lab):
    factory, settings, storage, _, _, _ = question_lab
    job = await create(question_lab)
    await start(question_lab, job)
    runner = QuestionJobRunner(factory, settings, storage=storage)
    claim, competing = await asyncio.gather(runner.claim(), runner.claim())
    identifier, token = claim or competing
    assert (claim is None) != (competing is None)
    ledger = QuestionLedger(factory, identifier, token, settings=settings, storage=storage)
    request_id, cached = await ledger.begin_or_reuse("t0", "a" * 64)
    assert cached is None
    async with factory() as session, session.begin():
        (await session.get(Job, identifier)).lease_expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
    assert await runner.claim() is None
    async with factory() as session:
        assert (await session.get(Job, identifier)).status == "INTERRUPTED"
        assert (await session.get(Request, request_id)).status == "INTERRUPTED_BILLING_UNKNOWN"
    with pytest.raises(AppError, match="LEASE_LOST"):
        await ledger.begin_or_reuse("t0", "b" * 64)


async def test_cancel_late_result_settles_request_without_proposals(question_lab):
    factory, settings, storage, owner, sample, _ = question_lab
    job = await create(question_lab)
    await start(question_lab, job)
    entered, release, calls = asyncio.Event(), asyncio.Event(), []
    runner = QuestionJobRunner(
        factory,
        settings,
        storage=storage,
        analyzer_factory=analyzer(question_lab, calls, entered=entered, release=release),
    )
    task = asyncio.create_task(runner.run_once())
    await asyncio.wait_for(entered.wait(), timeout=15)
    async with factory() as session:
        await questions.cancel_job(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            sample,
            job.id,
        )
    release.set()
    await asyncio.wait_for(task, timeout=15)
    async with factory() as session:
        row = await session.get(Job, job.id)
        request = await session.scalar(select(Request).where(Request.job_id == job.id))
        assert row.status == "CANCELLED" and row.proposals == []
        assert request.status == "COMPLETED"


async def test_owner_source_revision_and_final_results_are_fenced(question_lab):
    factory, settings, storage, owner, sample, _ = question_lab
    job = await create(question_lab)
    async with factory() as session:
        stranger = SpeakingBenchmarkService(session, uuid4(), settings=settings, storage=storage)
        async with session.begin():
            with pytest.raises(AppError, match="NOT_FOUND"):
                await questions.owned_job(stranger, sample, job.id)
        with pytest.raises(DBAPIError):
            async with session.begin():
                row = await session.get(Job, job.id)
                row.windows = []
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        review = await service.review(sample)
        await service.save_review(sample, ReviewPatch(expected_revision=2, draft=review.draft))
        with pytest.raises(AppError, match="REVIEW_CHANGED"):
            await questions.preflight(service, sample, job.id)
