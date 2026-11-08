"""Human-only annotation and narrow assignment access. No inference dependencies."""

from datetime import UTC, datetime
from itertools import combinations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.evaluation.speaking.metrics import score_metrics
from app.models import User
from app.models.enums import UserRole
from app.models.speaking_benchmark import SpeakingBenchmarkHumanLabel as LegacyLabel
from app.models.speaking_benchmark import SpeakingBenchmarkJob as Job
from app.models.speaking_benchmark import SpeakingBenchmarkReview as Review
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
from app.models.speaking_benchmark_human import (
    SpeakingBenchmarkRaterAssignment as Assignment,
)
from app.schemas.speaking_benchmark_human import (
    AdjudicationDTO,
    AssessmentDTO,
    AssignmentDTO,
    LabelSelection,
    RaterDTO,
)
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark import check_revision, failure

FIELDS = ("fc", "lr", "gra", "pr", "overall")
AGREEMENT_PROTOCOL = "speaking-human-agreement-v1"


def bands(row):
    return {
        key: float(getattr(row, key)) if row and getattr(row, key) is not None else None
        for key in FIELDS
    }


def assessment_eligible(row):
    return bool(
        row
        and row.independently_performed
        and row.provenance in {"internal_blind", "external_verified_report"}
        and row.source_reference.strip()
        and any(getattr(row, key) is not None for key in FIELDS)
    )


def assessment_dto(row):
    return AssessmentDTO(
        **{
            key: getattr(row, key)
            for key in AssessmentDTO.model_fields
            if key not in {"bands", "eligible"}
        },
        bands=bands(row),
        eligible=assessment_eligible(row),
    )


def adjudication_dto(row):
    return AdjudicationDTO(
        **{key: getattr(row, key) for key in AdjudicationDTO.model_fields if key != "bands"},
        bands=bands(row),
    )


def blind_projection(assignment, sample, review, own_assessments):
    """Allowlist projection; never serialize the owner sample or arbitrary JSON."""
    return {
        "id": assignment.id,
        "sample_id": assignment.sample_id,
        "review_revision": assignment.review_revision,
        "source_sha256": assignment.source_sha256,
        "manifest_fingerprint": assignment.manifest_fingerprint,
        "revision": assignment.revision,
        "duration_ms": sample.duration_ms,
        "audio_url": f"/api/v1/admin/speaking-benchmark/reviewer-assignments/{assignment.id}/audio",
        "questions": [
            {
                key: segment.get(key)
                for key in (
                    "id",
                    "part_number",
                    "prompt_type",
                    "prompt_text",
                    "cue_points",
                    "start_ms",
                    "end_ms",
                )
            }
            for segment in review.manifest["segments"]
        ],
        "assessments": [assessment_dto(row) for row in own_assessments],
        "created_at": assignment.created_at,
    }


def pairwise_agreement(rows):
    """Rows represent latest eligible ratings; stable rater pairs span samples."""
    raters = sorted({r["rater_id"] for r in rows})
    samples = {r["sample_id"] for r in rows}
    lookup = {(r["sample_id"], r["rater_id"]): r["bands"] for r in rows}
    output = []
    for left, right in combinations(raters, 2):
        matched = sorted(
            sample for sample in samples if (sample, left) in lookup and (sample, right) in lookup
        )
        criteria = {}
        for field in FIELDS:
            values = [
                (lookup[(sample, left)].get(field), lookup[(sample, right)].get(field))
                for sample in matched
            ]
            available = [(a, b) for a, b in values if a is not None and b is not None]
            criteria[field] = score_metrics(
                [a for a, _ in available], [b for _, b in available]
            ) | {
                "missing_labels": sum(a is None or b is None for a, b in values),
                "signed_direction": "right-minus-left",
                "absolute_differences": [abs(b - a) for a, b in available],
            }
        output.append(
            {
                "left_rater_id": left,
                "right_rater_id": right,
                "matched_samples": len(matched),
                "criteria": criteria,
            }
        )
    return {
        "protocol": AGREEMENT_PROTOCOL,
        "independent_raters": len(raters),
        "independent_samples": len(samples),
        "pairs": output,
        "limitations": [
            "HUMAN_DISAGREEMENT_IS_NOT_MODEL_ACCURACY",
            "SMALL_COHORT_KAPPA_UNAVAILABLE",
        ],
    }


async def approved_binding(session, owner_id, sample_id, review_revision, *, lock=False):
    query = select(Sample).where(
        Sample.id == sample_id, Sample.owner_id == owner_id, Sample.deletion_pending_at.is_(None)
    )
    sample = await session.scalar(query.with_for_update() if lock else query)
    if sample is None:
        raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
    review = await session.get(Review, (sample_id, review_revision))
    if not review or not review.approved_at or not review.manifest or not review.fingerprint:
        raise failure("SPEAKING_BENCHMARK_APPROVED_REVIEW_REQUIRED", 409)
    job = await session.get(Job, review.job_id)
    if (
        not job
        or not job.result
        or job.source_sha256 != sample.source_sha256
        or review.draft.get("source_sha256") != sample.source_sha256
        or review.fingerprint
        != fingerprint([sample.source_sha256, job.result.get("identity"), review.manifest])
    ):
        raise failure("REPLAY_APPROVED_SOURCE_CHANGED", 409)
    return sample, review


def matches_binding(row, sample, review):
    return (
        row.source_sha256 == sample.source_sha256
        and row.manifest_fingerprint == review.fingerprint
        and row.review_revision == review.revision
    )


async def owned_rater(session, owner_id, rater_id):
    row = await session.scalar(
        select(Rater).where(Rater.id == rater_id, Rater.owner_id == owner_id)
    )
    if row is None:
        raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
    return row


async def create_rater(service, body):
    try:
        async with service.session.begin():
            if body.kind == "INTERNAL":
                user = await service.session.get(User, body.user_id)
                if (
                    not user
                    or user.role != UserRole.ADMIN
                    or not user.is_active
                    or user.id == service.owner_id
                ):
                    raise failure("SPEAKING_HUMAN_RATER_ADMIN_REQUIRED", 422)
            row = Rater(owner_id=service.owner_id, **body.model_dump())
            service.session.add(row)
            await service.session.flush()
            return RaterDTO.model_validate(row)
    except IntegrityError:
        raise failure("SPEAKING_HUMAN_RATER_IDENTITY_EXISTS", 409) from None


async def list_raters(service, offset=0, limit=25):
    async with service.session.begin():
        scope = Rater.owner_id == service.owner_id
        total = await service.session.scalar(select(func.count()).select_from(Rater).where(scope))
        rows = await service.session.scalars(
            select(Rater)
            .where(scope)
            .order_by(Rater.created_at.desc(), Rater.id)
            .offset(offset)
            .limit(limit)
        )
        return {
            "items": [RaterDTO.model_validate(r) for r in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }


async def create_assignment(service, sample_id, body):
    try:
        async with service.session.begin():
            sample, review = await approved_binding(
                service.session, service.owner_id, sample_id, body.review_revision, lock=True
            )
            rater = await owned_rater(service.session, service.owner_id, body.rater_id)
            if rater.kind == "INTERNAL":
                user = await service.session.get(User, rater.user_id)
                if (
                    not user
                    or not user.is_active
                    or user.role != UserRole.ADMIN
                    or user.id == service.owner_id
                ):
                    raise failure("SPEAKING_HUMAN_RATER_ADMIN_REQUIRED", 422)
            row = Assignment(
                owner_id=service.owner_id,
                sample_id=sample.id,
                review_revision=review.revision,
                source_sha256=sample.source_sha256,
                manifest_fingerprint=review.fingerprint,
                rater_id=rater.id,
                assigned_by=service.owner_id,
                permitted_original_audio=True,
            )
            service.session.add(row)
            await service.session.flush()
            return AssignmentDTO.model_validate(row)
    except IntegrityError:
        raise failure("SPEAKING_HUMAN_ASSIGNMENT_EXISTS", 409) from None


async def list_assignments(service, sample_id, offset=0, limit=25):
    async with service.session.begin():
        await service.owned(sample_id)
        scope = (Assignment.owner_id == service.owner_id, Assignment.sample_id == sample_id)
        total = await service.session.scalar(
            select(func.count()).select_from(Assignment).where(*scope)
        )
        rows = await service.session.scalars(
            select(Assignment)
            .where(*scope)
            .order_by(Assignment.created_at.desc(), Assignment.id)
            .offset(offset)
            .limit(limit)
        )
        return {
            "items": [AssignmentDTO.model_validate(r) for r in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }


async def revoke_assignment(service, sample_id, assignment_id, body):
    async with service.session.begin():
        await service.owned(sample_id, lock=True)
        row = await service.session.scalar(
            select(Assignment)
            .where(
                Assignment.id == assignment_id,
                Assignment.owner_id == service.owner_id,
                Assignment.sample_id == sample_id,
            )
            .with_for_update()
        )
        if row is None:
            raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
        check_revision(row.revision, body.expected_revision)
        if row.revoked_at is None:
            row.revoked_at, row.revoked_by = datetime.now(UTC), service.owner_id
            row.revision += 1
            await service.session.flush()
        return AssignmentDTO.model_validate(row)


async def assigned_access(session, actor_id, assignment_id, *, lock=False):
    """Actor is never elevated into the dataset owner's service scope."""
    query = (
        select(Assignment)
        .join(Rater, Rater.id == Assignment.rater_id)
        .where(
            Assignment.id == assignment_id,
            Assignment.revoked_at.is_(None),
            Rater.user_id == actor_id,
            Rater.kind == "INTERNAL",
            Rater.owner_id == Assignment.owner_id,
            Assignment.owner_id != actor_id,
        )
    )
    row = await session.scalar(query.with_for_update(of=Assignment) if lock else query)
    if row is None:
        raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
    user = await session.get(User, actor_id)
    if not user or not user.is_active or user.role != UserRole.ADMIN:
        raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
    sample, review = await approved_binding(
        session, row.owner_id, row.sample_id, row.review_revision
    )
    if not matches_binding(row, sample, review):
        raise failure("SPEAKING_HUMAN_ASSIGNMENT_STALE", 409)
    return row, sample, review


async def reviewer_assignments(session, actor_id, offset=0, limit=25):
    async with session.begin():
        scope = (
            Rater.user_id == actor_id,
            Rater.kind == "INTERNAL",
            Assignment.revoked_at.is_(None),
            Assignment.owner_id != actor_id,
            Sample.deletion_pending_at.is_(None),
        )
        query = (
            select(Assignment)
            .join(Rater, Rater.id == Assignment.rater_id)
            .join(Sample, Sample.id == Assignment.sample_id)
            .where(*scope)
        )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await session.scalars(
            query.order_by(Assignment.created_at.desc(), Assignment.id).offset(offset).limit(limit)
        )
        return {
            "items": [AssignmentDTO.model_validate(r) for r in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }


async def blind_detail(session, actor_id, assignment_id):
    async with session.begin():
        assignment, sample, review = await assigned_access(session, actor_id, assignment_id)
        rows = list(
            await session.scalars(
                select(Assessment)
                .where(
                    Assessment.assignment_id == assignment.id, Assessment.authored_by == actor_id
                )
                .order_by(Assessment.revision.desc())
                .limit(100)
            )
        )
        return blind_projection(assignment, sample, review, rows)


async def blind_audio(session, actor_id, assignment_id):
    async with session.begin():
        assignment, sample, _ = await assigned_access(session, actor_id, assignment_id)
        if not assignment.permitted_original_audio:
            raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
        return sample.audio_key, sample.mime_type


async def submit_assessment(
    session, actor_id, assignment_id, body, *, owner_id=None, sample_id=None
):
    async with session.begin():
        if owner_id is None:
            assignment, sample, review = await assigned_access(
                session, actor_id, assignment_id, lock=True
            )
            provenance = "internal_blind"
            reference = body.source_reference.strip() or f"assignment:{assignment.id}"
        else:
            assignment = await session.scalar(
                select(Assignment)
                .where(
                    Assignment.id == assignment_id,
                    Assignment.owner_id == owner_id,
                    Assignment.revoked_at.is_(None),
                )
                .with_for_update()
            )
            if (
                assignment is None
                or actor_id != owner_id
                or sample_id is not None
                and assignment.sample_id != sample_id
            ):
                raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
            rater = await owned_rater(session, owner_id, assignment.rater_id)
            if rater.kind != "EXTERNAL":
                raise failure("SPEAKING_HUMAN_REVIEWER_SUBMISSION_REQUIRED", 403)
            sample, review = await approved_binding(
                session, owner_id, assignment.sample_id, assignment.review_revision
            )
            if not matches_binding(assignment, sample, review):
                raise failure("SPEAKING_HUMAN_ASSIGNMENT_STALE", 409)
            provenance, reference = body.provenance, body.source_reference
        latest = (
            await session.scalar(
                select(func.max(Assessment.revision)).where(
                    Assessment.assignment_id == assignment_id
                )
            )
            or 0
        )
        check_revision(latest, body.expected_revision)
        row = Assessment(
            owner_id=assignment.owner_id,
            sample_id=sample.id,
            review_revision=review.revision,
            source_sha256=sample.source_sha256,
            manifest_fingerprint=review.fingerprint,
            assignment_id=assignment.id,
            rater_id=assignment.rater_id,
            revision=latest + 1,
            **body.bands.model_dump(),
            comments=body.comments.model_dump(),
            provenance=provenance,
            source_reference=reference,
            independently_performed=body.independently_performed,
            authored_by=actor_id,
            submitted_at=datetime.now(UTC),
        )
        session.add(row)
        await session.flush()
        return assessment_dto(row)


async def latest_assessments(session, owner_id, sample_id, review_revision=None):
    query = select(Assessment).where(
        Assessment.owner_id == owner_id, Assessment.sample_id == sample_id
    )
    if review_revision is not None:
        query = query.where(Assessment.review_revision == review_revision)
    rows = await session.scalars(
        query.order_by(
            Assessment.submitted_at.desc(), Assessment.revision.desc(), Assessment.id.desc()
        )
    )
    latest = {}
    for row in rows:
        latest.setdefault((row.rater_id, row.review_revision), row)
    return list(latest.values())


async def list_assessments(service, sample_id, review_revision=None, offset=0, limit=25):
    async with service.session.begin():
        await service.owned(sample_id)
        query = select(Assessment).where(
            Assessment.owner_id == service.owner_id, Assessment.sample_id == sample_id
        )
        if review_revision:
            query = query.where(Assessment.review_revision == review_revision)
        total = await service.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await service.session.scalars(
            query.order_by(Assessment.submitted_at.desc(), Assessment.id)
            .offset(offset)
            .limit(limit)
        )
        return {
            "items": [assessment_dto(r) for r in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }


async def human_agreement(service, sample_id=None, review_revision=None):
    async with service.session.begin():
        if sample_id:
            await service.owned(sample_id)
            sample_ids = [sample_id]
        else:
            sample_ids = list(
                await service.session.scalars(
                    select(Sample.id)
                    .where(
                        Sample.owner_id == service.owner_id, Sample.deletion_pending_at.is_(None)
                    )
                    .limit(101)
                )
            )
            if len(sample_ids) > 100:
                raise failure("SPEAKING_HUMAN_AGREEMENT_NARROW_SCOPE", 422)
        inputs = []
        for sid in sample_ids:
            sample = await service.session.get(Sample, sid)
            revision = review_revision or sample.review_revision
            # Latest P1 draft may be unapproved; do not compare ratings across reviews.
            rows = await latest_assessments(service.session, service.owner_id, sid, revision)
            for row in rows:
                if assessment_eligible(row):
                    inputs.append(
                        {"sample_id": str(sid), "rater_id": str(row.rater_id), "bands": bands(row)}
                    )
        return pairwise_agreement(inputs)


async def create_adjudication(service, sample_id, body):
    async with service.session.begin():
        sample, review = await approved_binding(
            service.session, service.owner_id, sample_id, body.review_revision, lock=True
        )
        rows = list(
            await service.session.scalars(
                select(Assessment).where(
                    Assessment.id.in_(body.assessment_ids),
                    Assessment.owner_id == service.owner_id,
                    Assessment.sample_id == sample_id,
                    Assessment.review_revision == review.revision,
                )
            )
        )
        current = await latest_assessments(
            service.session, service.owner_id, sample_id, review.revision
        )
        current_ids = {r.id for r in current}
        if (
            len(rows) != len(body.assessment_ids)
            or len({r.rater_id for r in rows}) != len(rows)
            or any(r.id not in current_ids or not matches_binding(r, sample, review) for r in rows)
        ):
            raise failure("SPEAKING_HUMAN_ADJUDICATION_ASSESSMENTS_STALE", 409)
        if any(not assessment_eligible(r) for r in rows):
            raise failure("SPEAKING_HUMAN_INDEPENDENT_ASSESSMENT_REQUIRED", 422)
        latest = (
            await service.session.scalar(
                select(func.max(Adjudication.revision)).where(
                    Adjudication.sample_id == sample_id,
                    Adjudication.review_revision == review.revision,
                )
            )
            or 0
        )
        check_revision(latest, body.expected_revision)
        row = Adjudication(
            owner_id=service.owner_id,
            sample_id=sample_id,
            review_revision=review.revision,
            source_sha256=sample.source_sha256,
            manifest_fingerprint=review.fingerprint,
            revision=latest + 1,
            assessment_refs=[
                {"id": str(r.id), "revision": r.revision, "rater_id": str(r.rater_id)}
                for r in sorted(rows, key=lambda r: str(r.id))
            ],
            **body.bands.model_dump(),
            rationale=body.rationale,
            policy_version=body.policy_version,
            provenance="owner_human_adjudication",
            adjudicator_id=service.owner_id,
            adjudicated_at=datetime.now(UTC),
        )
        service.session.add(row)
        await service.session.flush()
        return adjudication_dto(row)


async def list_adjudications(service, sample_id, review_revision=None, offset=0, limit=25):
    async with service.session.begin():
        await service.owned(sample_id)
        query = select(Adjudication).where(
            Adjudication.owner_id == service.owner_id, Adjudication.sample_id == sample_id
        )
        if review_revision:
            query = query.where(Adjudication.review_revision == review_revision)
        total = await service.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await service.session.scalars(
            query.order_by(Adjudication.adjudicated_at.desc(), Adjudication.id)
            .offset(offset)
            .limit(limit)
        )
        return {
            "items": [adjudication_dto(r) for r in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }


async def resolve_human_label(session, owner_id, sample_id, review_revision, selection):
    """Caller owns the transaction. Never changes inference or legacy selection."""
    selection = LabelSelection.model_validate(selection)
    sample, review = await approved_binding(session, owner_id, sample_id, review_revision)
    row = None
    if selection.kind == "LEGACY":
        query = select(LegacyLabel).where(LegacyLabel.sample_id == sample_id)
        if selection.id is not None and selection.id != sample_id:
            raise failure("SPEAKING_HUMAN_LABEL_NOT_FOUND", 404)
        if selection.revision is not None:
            query = query.where(LegacyLabel.revision == selection.revision)
        else:
            query = query.where(
                LegacyLabel.verified.is_(True),
                or_(*(getattr(LegacyLabel, field).is_not(None) for field in FIELDS)),
            )
        row = await session.scalar(
            query.order_by(LegacyLabel.verified.desc(), LegacyLabel.revision.desc()).limit(1)
        )
        eligible = bool(
            row and row.verified and any(getattr(row, field) is not None for field in FIELDS)
        )
        identifier = str(sample_id) if row else None
        binding_status = "LEGACY_UNBOUND"
    elif selection.kind == "INDEPENDENT":
        if selection.id is not None or selection.revision is not None:
            query = select(Assessment).where(
                Assessment.owner_id == owner_id,
                Assessment.sample_id == sample_id,
                Assessment.review_revision == review_revision,
            )
            if selection.id is not None:
                query = query.where(Assessment.id == selection.id)
            if selection.revision is not None:
                query = query.where(Assessment.revision == selection.revision)
            if selection.rater_id is not None:
                query = query.where(Assessment.rater_id == selection.rater_id)
            row = await session.scalar(
                query.order_by(Assessment.submitted_at.desc(), Assessment.id.desc()).limit(1)
            )
        else:
            rows = await latest_assessments(session, owner_id, sample_id, review_revision)
            row = next(
                (
                    r
                    for r in rows
                    if assessment_eligible(r)
                    and (selection.rater_id is None or selection.rater_id == r.rater_id)
                    and (selection.revision is None or selection.revision == r.revision)
                ),
                None,
            )
        if row and (
            not matches_binding(row, sample, review)
            or selection.revision is not None
            and row.revision != selection.revision
            or selection.rater_id is not None
            and row.rater_id != selection.rater_id
        ):
            raise failure("SPEAKING_HUMAN_LABEL_BINDING_MISMATCH", 409)
        eligible, identifier, binding_status = (
            assessment_eligible(row),
            str(row.id) if row else None,
            "SOURCE_BOUND",
        )
    else:
        query = select(Adjudication).where(
            Adjudication.owner_id == owner_id,
            Adjudication.sample_id == sample_id,
            Adjudication.review_revision == review_revision,
        )
        if selection.id is not None:
            query = query.where(Adjudication.id == selection.id)
        if selection.revision is not None:
            query = query.where(Adjudication.revision == selection.revision)
        row = await session.scalar(query.order_by(Adjudication.revision.desc()).limit(1))
        if row and not matches_binding(row, sample, review):
            raise failure("SPEAKING_HUMAN_LABEL_BINDING_MISMATCH", 409)
        eligible, identifier, binding_status = (
            bool(row and any(getattr(row, field) is not None for field in FIELDS)),
            str(row.id) if row else None,
            "SOURCE_BOUND",
        )
    if (selection.id is not None or selection.revision is not None) and row is None:
        raise failure("SPEAKING_HUMAN_LABEL_NOT_FOUND", 404)
    result = {
        "kind": selection.kind,
        "id": identifier,
        "revision": row.revision if row else None,
        "bands": bands(row),
        "eligible": eligible,
        "provenance": row.provenance if row else None,
        "binding_status": binding_status if row else "MISSING",
        "sample_id": str(sample_id),
        "review_revision": review_revision,
        "source_sha256": sample.source_sha256,
        "manifest_fingerprint": review.fingerprint,
    }
    result["fingerprint"] = fingerprint(result)
    return result


async def resolve_label_id(session, owner_id, sample_id, review_revision, selection):
    return await resolve_human_label(session, owner_id, sample_id, review_revision, selection)
