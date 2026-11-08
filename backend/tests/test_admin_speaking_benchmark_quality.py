from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import AppError
from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_quality import SpeakingBenchmarkEvaluationSuite as Suite
from app.schemas.speaking_benchmark_quality import QualityRequest, SuiteCreate
from app.services.speaking_benchmark import SpeakingBenchmarkService


async def test_quality_is_read_only_and_snapshot_is_bound(grading_lab):
    from app.services.speaking_benchmark_quality import create_suite, quality_report

    factory, settings, storage, owner, sample, _ = grading_lab
    body = QualityRequest(cohort=[{"sample_id": sample, "review_revision": 1}])
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        report = await quality_report(service, body)
        assert report["status"] == "BLOCKED"
        assert {"HUMAN_LABEL_MISSING", "INSUFFICIENT_INDEPENDENT_CANDIDATES"} <= {
            i["code"] for i in report["issues"]
        }
        assert report["samples"][0]["sample_id"] == str(sample)
        assert await session.scalar(select(Suite).where(Suite.owner_id == owner)) is None
        await session.rollback()
        suite = await create_suite(
            service, SuiteCreate(**body.model_dump(), name="Fictional suite")
        )
        frozen = suite.configuration
        assert frozen["samples"][0]["source_sha256"]
        assert frozen["quality"]["status"] == "BLOCKED"
    async with factory() as session, session.begin():
        row = await session.get(Sample, sample)
        row.candidate_id = "later pseudonym"
    async with factory() as session:
        row = await session.get(Suite, suite.id)
        assert row.configuration == frozen
        with pytest.raises(DBAPIError):
            await session.execute(
                text("UPDATE speaking_benchmark_evaluation_suites SET name=:name WHERE id=:id"),
                {"name": "mutated", "id": suite.id},
            )
        await session.rollback()
        with pytest.raises(AppError):
            await quality_report(
                SpeakingBenchmarkService(session, uuid4(), settings=settings, storage=storage), body
            )


async def test_holdout_requires_explicit_audited_consent(grading_lab):
    from app.services.speaking_benchmark_quality import create_suite, get_suite

    factory, settings, storage, owner, sample, _ = grading_lab
    async with factory() as session, session.begin():
        row = await session.get(Sample, sample)
        row.split = "HOLDOUT"
    body = SuiteCreate(cohort=[{"sample_id": sample, "review_revision": 1}], name="Holdout")
    async with factory() as session:
        service = SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)
        with pytest.raises(AppError):
            await create_suite(service, body)
        suite = await create_suite(service, body.model_copy(update={"holdout_evaluation": True}))
        with pytest.raises(AppError):
            await get_suite(service, suite.id, False)
        assert (await get_suite(service, suite.id, True)).id == suite.id
