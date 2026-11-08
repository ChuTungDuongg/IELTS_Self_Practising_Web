"""Append-only independent human transcripts, isolated from inference."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.models.speaking_benchmark_research import SpeakingBenchmarkASRReference as Reference
from app.schemas.speaking_benchmark_research import ReferenceDTO, ReferenceWrite
from app.services.speaking_benchmark import check_revision, failure
from app.services.speaking_benchmark_audio import load_approved_input


async def reference_history(service, sample_id, revision, *, segment_id=None, offset=0, limit=50):
    async with service.session.begin():
        await service.owned(sample_id)
        query = select(Reference).where(
            Reference.owner_id == service.owner_id,
            Reference.sample_id == sample_id,
            Reference.review_revision == revision,
        )
        if segment_id:
            query = query.where(Reference.segment_id == segment_id)
        rows = await service.session.scalars(
            query.order_by(Reference.created_at.desc(), Reference.id).offset(offset).limit(limit)
        )
        return [ReferenceDTO.model_validate(r) for r in rows]


async def write_reference(service, sample_id, body: ReferenceWrite, *, verify=False):
    async with service.session.begin():
        await service.owned(sample_id, lock=True)
        sample, review, manifest, _ = await load_approved_input(
            service, sample_id, body.review_revision
        )
        segment = next((s for s in manifest.segments if s.id == body.segment_id), None)
        if not segment or (body.source_sha256, body.start_ms, body.end_ms) != (
            sample.source_sha256,
            segment.start_ms,
            segment.end_ms,
        ):
            raise failure("SPEAKING_RESEARCH_REFERENCE_BINDING_MISMATCH", 409)
        previous = await service.session.scalar(
            select(Reference)
            .where(
                Reference.sample_id == sample_id,
                Reference.review_revision == body.review_revision,
                Reference.segment_id == body.segment_id,
            )
            .order_by(Reference.revision.desc())
            .limit(1)
        )
        check_revision(previous.revision if previous else 0, body.expected_revision)
        if verify and (
            not previous
            or body.provenance != "independent_human_transcriber"
            or not body.source_reference.strip()
            or not body.text.strip()
        ):
            raise failure("SPEAKING_RESEARCH_INDEPENDENT_REFERENCE_REQUIRED", 409)
        row = Reference(
            sample_id=sample_id,
            owner_id=service.owner_id,
            review_revision=body.review_revision,
            source_sha256=body.source_sha256,
            manifest_fingerprint=review.fingerprint,
            segment_id=body.segment_id,
            start_ms=body.start_ms,
            end_ms=body.end_ms,
            revision=body.expected_revision + 1,
            normalization=body.normalization,
            text=body.text,
            annotations=[a.model_dump() for a in body.annotations],
            uncertainty=[s.model_dump() for s in body.uncertainty],
            metadata_labels={
                "accent": body.accent,
                "speaking_speed": body.speaking_speed,
                "response_length": body.response_length,
                "voluntary_metadata": body.voluntary_metadata,
            },
            status="VERIFIED" if verify else "DRAFT",
            provenance=body.provenance,
            source_reference=body.source_reference,
            author_id=previous.author_id if verify else service.owner_id,
            reviewer_id=service.owner_id if verify else None,
            verified_at=datetime.now(UTC) if verify else None,
        )
        service.session.add(row)
        await service.session.flush()
        return ReferenceDTO.model_validate(row)


async def verify_reference(service, sample_id, reference_id, body):
    async with service.session.begin():
        await service.owned(sample_id)
        row = await service.session.scalar(
            select(Reference).where(
                Reference.id == reference_id,
                Reference.sample_id == sample_id,
                Reference.owner_id == service.owner_id,
            )
        )
        if row is None:
            raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
        check_revision(row.revision, body.expected_revision)
        data = {
            k: getattr(row, k)
            for k in (
                "review_revision",
                "source_sha256",
                "segment_id",
                "start_ms",
                "end_ms",
                "normalization",
                "text",
                "annotations",
                "uncertainty",
                "provenance",
                "source_reference",
            )
        }
        data.update(row.metadata_labels)
    return await write_reference(
        service,
        sample_id,
        ReferenceWrite(**data, expected_revision=body.expected_revision),
        verify=True,
    )
