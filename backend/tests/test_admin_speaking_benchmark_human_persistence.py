"""Synthetic, isolated PostgreSQL tests for human rating privacy and immutability."""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import AppError
from app.models import User
from app.models.enums import UserRole
from app.models.speaking_benchmark import SpeakingBenchmarkHumanLabel as Legacy
from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_human import (
    SpeakingBenchmarkAdjudication as Adjudication,
)
from app.models.speaking_benchmark_human import (
    SpeakingBenchmarkHumanAssessment as Assessment,
)
from app.models.speaking_benchmark_human import (
    SpeakingBenchmarkRater as Rater,
)
from app.schemas.speaking_benchmark_human import (
    AdjudicationCreate,
    AssessmentSubmit,
    AssignmentCreate,
    AssignmentRevoke,
    RaterCreate,
)
from app.services import speaking_benchmark_human as human
from app.services.speaking_benchmark import SpeakingBenchmarkService

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def human_lab(grading_lab):
    factory, settings, storage, owner, sample, _ = grading_lab
    reviewers = [uuid4(), uuid4()]
    async with factory() as session, session.begin():
        for index, user_id in enumerate(reviewers):
            session.add(
                User(
                    id=user_id,
                    email=f"human-{user_id}@example.com",
                    display_name=f"Synthetic reviewer {index}",
                    role=UserRole.ADMIN,
                    is_active=True,
                    email_verified=True,
                )
            )
    try:
        yield factory, settings, storage, owner, sample, reviewers
    finally:
        async with factory() as session, session.begin():
            # The parent removes sample; raters must go before its owner user.
            await session.execute(delete(Rater).where(Rater.owner_id == owner))
            await session.execute(delete(User).where(User.id.in_(reviewers)))


def service(session, lab):
    _, settings, storage, owner, _, _ = lab
    return SpeakingBenchmarkService(session, owner, settings=settings, storage=storage)


async def assign(lab, index=0, *, external=False):
    factory, _, _, _, sample, reviewers = lab
    async with factory() as session:
        rater = await human.create_rater(
            service(session, lab),
            RaterCreate(
                kind="EXTERNAL" if external else "INTERNAL",
                display_name=f"Fictional examiner {index}",
                **(
                    {"external_key": f"external-{index}"}
                    if external
                    else {"user_id": reviewers[index]}
                ),
            ),
        )
        assignment = await human.create_assignment(
            service(session, lab), sample, AssignmentCreate(rater_id=rater.id, review_revision=1)
        )
    return rater, assignment


async def rating(lab, assignment, *, actor=None, external=False, expected=0, **kwargs):
    factory, _, _, owner, sample, reviewers = lab
    async with factory() as session:
        return await human.submit_assessment(
            session,
            actor or (owner if external else reviewers[0]),
            assignment.id,
            AssessmentSubmit(
                expected_revision=expected,
                bands=kwargs.pop("bands", {"fc": 6.5, "overall": None}),
                independently_performed=True,
                **kwargs,
            ),
            **({"owner_id": owner, "sample_id": sample} if external else {}),
        )


async def test_user_bound_identity_rejects_owner_and_duplicate_alias(human_lab):
    factory, _, _, owner, _, reviewers = human_lab
    async with factory() as session:
        with pytest.raises(AppError) as caught:
            await human.create_rater(
                service(session, human_lab),
                RaterCreate(kind="INTERNAL", user_id=owner, display_name="Owner alias"),
            )
        assert caught.value.status_code == 422
        await human.create_rater(
            service(session, human_lab),
            RaterCreate(kind="INTERNAL", user_id=reviewers[0], display_name="First alias"),
        )
        with pytest.raises(AppError) as caught:
            await human.create_rater(
                service(session, human_lab),
                RaterCreate(kind="INTERNAL", user_id=reviewers[0], display_name="Second alias"),
            )
        assert caught.value.status_code == 409


async def test_explicit_p2_labels_use_run_review_and_preserve_legacy_default(human_lab):
    from sqlalchemy import select

    from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
    from app.schemas.speaking_benchmark_reports import ReportFilters
    from app.services.speaking_benchmark_reports import comparison, report

    factory, _, _, owner, sample, _ = human_lab
    _, assignment = await assign(human_lab)
    assessment = await rating(human_lab, assignment, bands={"fc": 6.5, "overall": None})
    async with factory() as session, session.begin():
        run = await session.scalar(select(Run).where(Run.sample_id == sample))
        run.status = "COMPLETED"
        run.prediction = {"bands": {"fc": 6.0, "overall": 9}}
        run_id = run.id
    async with factory() as session:
        svc = service(session, human_lab)
        default = await comparison(svc, sample, run_id)
        explicit = await comparison(
            svc, sample, run_id, label_selection={"kind": "INDEPENDENT", "id": str(assessment.id)}
        )
        assert default["human"]["fc"] is None
        assert explicit["human"]["fc"] == 6.5 and explicit["human"]["overall"] is None
        assert explicit["differences"]["fc"] == -0.5 and explicit["differences"]["overall"] is None
        summary, rows = await report(svc, ReportFilters(human_label_kind="INDEPENDENT"))
        assert summary["criteria"]["fc"]["mae"] == 0.5
        assert rows[0]["human_label_selection"]["id"] == str(assessment.id)


async def test_assignment_scope_blind_dto_audio_and_revocation(human_lab):
    factory, _, _, owner, sample, reviewers = human_lab
    _, assignment = await assign(human_lab)
    async with factory() as session:
        blind = await human.blind_detail(session, reviewers[0], assignment.id)
        assert blind["assessments"] == []
        assert blind["questions"] and "prediction" not in str(blind)
        key, mime = await human.blind_audio(session, reviewers[0], assignment.id)
        assert key.endswith("synthetic.wav") and mime == "audio/wav"
        for actor in (owner, reviewers[1], uuid4()):
            with pytest.raises(AppError) as caught:
                await human.blind_audio(session, actor, assignment.id)
            assert caught.value.status_code == 404
        # Existing owner service never acquires the scoped reviewer's permission.
        with pytest.raises(AppError) as caught:
            await SpeakingBenchmarkService(session, reviewers[0]).audio(sample)
        assert caught.value.status_code == 404
        await human.revoke_assignment(
            service(session, human_lab),
            sample,
            assignment.id,
            AssignmentRevoke(expected_revision=1),
        )
        with pytest.raises(AppError):
            await human.blind_audio(session, reviewers[0], assignment.id)


async def test_rating_corrections_are_append_only_and_not_impersonated(human_lab):
    factory, _, _, owner, sample, reviewers = human_lab
    _, assignment = await assign(human_lab)
    original = await rating(human_lab, assignment)
    corrected = await rating(human_lab, assignment, expected=1, bands={"fc": 7, "overall": 6.5})
    assert original.id != corrected.id and corrected.revision == 2
    assert original.bands.overall is None and corrected.bands.overall == 6.5
    assert original.provenance == "internal_blind" and original.authored_by == reviewers[0]
    with pytest.raises(AppError) as caught:
        await rating(human_lab, assignment, expected=1)
    assert caught.value.status_code == 409
    with pytest.raises(AppError):
        await rating(human_lab, assignment, actor=reviewers[1])
    async with factory() as session:
        with pytest.raises(AppError):
            await human.submit_assessment(
                session,
                owner,
                assignment.id,
                AssessmentSubmit(expected_revision=2, bands={"overall": 9}),
                owner_id=owner,
                sample_id=sample,
            )
        blind = await human.blind_detail(session, reviewers[0], assignment.id)
        assert len(blind["assessments"]) == 2
    async with factory() as session, session.begin():
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(
                    update(Assessment).where(Assessment.id == original.id).values(overall=9)
                )


async def test_external_report_provenance_and_latest_selection(human_lab):
    factory, _, _, owner, sample, _ = human_lab
    _, assignment = await assign(human_lab, external=True)
    unverified = await rating(
        human_lab, assignment, external=True, source_reference="A claimed report"
    )
    assert not unverified.eligible
    verified = await rating(
        human_lab,
        assignment,
        external=True,
        expected=1,
        provenance="external_verified_report",
        source_reference="Verifiable fictional report identifier",
        bands={"fc": 6.5, "overall": 6},
    )
    assert verified.eligible
    async with factory() as session, session.begin():
        resolved = await human.resolve_human_label(
            session, owner, sample, 1, {"kind": "INDEPENDENT"}
        )
        assert resolved["id"] == str(verified.id)
        assert resolved["bands"]["overall"] == 6 and resolved["binding_status"] == "SOURCE_BOUND"
        old = await human.resolve_human_label(
            session, owner, sample, 1, {"kind": "INDEPENDENT", "id": unverified.id, "revision": 1}
        )
        assert not old["eligible"]


async def test_adjudication_is_explicit_human_decision_and_legacy_untouched(human_lab):
    factory, _, _, owner, sample, reviewers = human_lab
    _, first = await assign(human_lab, 0)
    _, second = await assign(human_lab, 1)
    left = await rating(human_lab, first, bands={"fc": 6, "overall": 6})
    right = await rating(human_lab, second, actor=reviewers[1], bands={"fc": 7, "overall": 7})
    async with factory() as session, session.begin():
        session.add(
            Legacy(
                sample_id=sample,
                revision=1,
                fc=5,
                lr=None,
                gra=None,
                pr=None,
                overall=5,
                provenance="human_examiner",
                reference="Fictional earlier report",
                verified=True,
                examiner="Legacy examiner",
                notes="",
                authored_by=owner,
            )
        )
    async with factory() as session:
        decision = await human.create_adjudication(
            service(session, human_lab),
            sample,
            AdjudicationCreate(
                review_revision=1,
                expected_revision=0,
                assessment_ids=[left.id, right.id],
                bands={"fc": 7, "overall": None},
                rationale="Explicit decision after listening; overall not supplied",
            ),
        )
        assert decision.bands.fc == 7 and decision.bands.overall is None
        assert {r["id"] for r in decision.assessment_refs} == {str(left.id), str(right.id)}
        assert decision.adjudicator_id == owner
        agreement = await human.human_agreement(service(session, human_lab), sample, 1)
        assert (
            agreement["independent_raters"] == 2
            and agreement["pairs"][0]["criteria"]["fc"]["mae"] == 1
        )
        async with session.begin():
            resolved = await human.resolve_human_label(
                session, owner, sample, 1, {"kind": "ADJUDICATED"}
            )
            assert resolved["bands"]["fc"] == 7 and resolved["bands"]["overall"] is None
            legacy = await session.get(Legacy, (sample, 1))
            assert float(legacy.overall) == 5
            legacy_selected = await human.resolve_human_label(
                session, owner, sample, 1, {"kind": "LEGACY", "revision": 1}
            )
            assert legacy_selected["binding_status"] == "LEGACY_UNBOUND"
            with pytest.raises(DBAPIError):
                async with session.begin_nested():
                    await session.execute(
                        update(Adjudication).where(Adjudication.id == decision.id).values(overall=9)
                    )


async def test_corrected_rating_does_not_replace_a_frozen_adjudication(human_lab):
    factory, _, _, owner, sample, _ = human_lab
    _, assignment = await assign(human_lab)
    original = await rating(human_lab, assignment)
    async with factory() as session:
        decision = await human.create_adjudication(
            service(session, human_lab),
            sample,
            AdjudicationCreate(
                review_revision=1,
                expected_revision=0,
                assessment_ids=[original.id],
                bands={"fc": 6.5},
                rationale="Reviewed original evidence",
            ),
        )
    await rating(human_lab, assignment, expected=1, bands={"fc": 7})
    async with factory() as session:
        with pytest.raises(AppError) as caught:
            await human.create_adjudication(
                service(session, human_lab),
                sample,
                AdjudicationCreate(
                    review_revision=1,
                    expected_revision=1,
                    assessment_ids=[original.id],
                    bands={"fc": 7},
                    rationale="Reject superseded evidence",
                ),
            )
        assert caught.value.status_code == 409
        async with session.begin():
            frozen = await human.resolve_human_label(
                session, owner, sample, 1, {"kind": "ADJUDICATED", "id": decision.id, "revision": 1}
            )
            assert frozen["bands"]["fc"] == 6.5


async def test_deleted_or_cross_owner_sources_are_not_reviewer_grants(human_lab):
    from datetime import UTC, datetime

    factory, _, _, owner, sample, reviewers = human_lab
    _, assignment = await assign(human_lab)
    async with factory() as session:
        with pytest.raises(AppError):
            await human.create_assignment(
                SpeakingBenchmarkService(session, reviewers[1]),
                sample,
                AssignmentCreate(rater_id=assignment.rater_id, review_revision=1),
            )
        async with session.begin():
            (await session.get(Sample, sample)).deletion_pending_at = datetime.now(UTC)
        with pytest.raises(AppError):
            await human.blind_detail(session, reviewers[0], assignment.id)
        async with session.begin():
            with pytest.raises(AppError):
                await human.resolve_human_label(session, owner, sample, 1, {"kind": "ADJUDICATED"})


async def test_explicit_rater_revision_can_reopen_a_superseded_assessment(human_lab):
    factory, _, _, owner, sample, _ = human_lab
    rater, assignment = await assign(human_lab)
    original = await rating(human_lab, assignment, bands={"fc": 6})
    await rating(human_lab, assignment, expected=1, bands={"fc": 7})
    async with factory() as session, session.begin():
        resolved = await human.resolve_human_label(
            session, owner, sample, 1, {"kind": "INDEPENDENT", "rater_id": rater.id, "revision": 1}
        )
        assert resolved["id"] == str(original.id) and resolved["bands"]["fc"] == 6
        with pytest.raises(AppError):
            await human.resolve_human_label(
                session,
                owner,
                sample,
                1,
                {"kind": "INDEPENDENT", "id": original.id, "rater_id": uuid4()},
            )


async def test_legacy_verified_policy_skips_empty_newer_revision(human_lab):
    factory, _, _, owner, sample, _ = human_lab
    async with factory() as session, session.begin():
        for revision, overall in ((1, 6.5), (2, None)):
            session.add(
                Legacy(
                    sample_id=sample,
                    revision=revision,
                    overall=overall,
                    provenance="human_examiner",
                    reference="Fictional report",
                    verified=True,
                    examiner="Examiner",
                    notes="",
                    authored_by=owner,
                )
            )
    async with factory() as session, session.begin():
        resolved = await human.resolve_human_label(session, owner, sample, 1, {"kind": "LEGACY"})
        assert resolved["revision"] == 1 and resolved["eligible"]
