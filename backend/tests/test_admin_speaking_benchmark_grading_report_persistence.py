from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.speaking_benchmark import SpeakingBenchmarkHumanLabel as Label
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.schemas.speaking_benchmark_reports import ReportFilters
from app.services.speaking_benchmark import SpeakingBenchmarkService
from app.services.speaking_benchmark_reports import comparison, csv_export, report


async def test_latest_run_one_weight_latest_verified_label_and_owner_isolation(grading_lab):
    factory, settings, storage, owner, sample, run_id = grading_lab
    async with factory() as session, session.begin():
        old = await session.get(Run, run_id)
        old.status, old.prediction = (
            "PARTIAL",
            {"bands": {"overall": 5}, "criteria": {}, "limitations": []},
        )
        new = Run(
            sample_id=sample,
            owner_id=owner,
            review_revision=old.review_revision,
            source_sha256=old.source_sha256,
            manifest_fingerprint=old.manifest_fingerprint,
            config_fingerprint=old.config_fingerprint,
            configuration=old.configuration,
            submission_key=uuid4(),
            consent=old.consent,
            candidate_ms=old.candidate_ms,
            window_count=3,
            status="COMPLETED",
            prediction={"bands": {"overall": 6.5}, "criteria": {}, "limitations": []},
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        )
        session.add(new)
        session.add_all(
            [
                Label(
                    sample_id=sample,
                    revision=1,
                    overall=6,
                    provenance="human_examiner",
                    reference="Fictional independent source",
                    verified=True,
                    examiner="PRIVATE",
                    notes="PRIVATE",
                ),
                Label(
                    sample_id=sample,
                    revision=2,
                    overall=9,
                    provenance="unverified",
                    reference="",
                    verified=False,
                    examiner="PRIVATE",
                    notes="PRIVATE",
                ),
            ]
        )
    async with factory() as session:
        summary, rows = await report(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            ReportFilters(),
        )
        assert summary["eligible_samples"] == 1
        assert summary["criteria"]["overall"]["mae"] == 0.5
        assert rows[0]["run_id"] == str(new.id)
        assert rows[0]["label_revision"] == 1
        assert "PRIVATE" not in csv_export(rows)
    async with factory() as session:
        value = await comparison(
            SpeakingBenchmarkService(session, owner, settings=settings, storage=storage),
            sample,
            new.id,
            2,
        )
        assert value["human"]["overall"] == 9
        assert value["verified"] is False
    async with factory() as session:
        summary, rows = await report(
            SpeakingBenchmarkService(session, uuid4(), settings=settings, storage=storage),
            ReportFilters(),
        )
        assert rows == [] and summary["uploaded_samples"] == 0
