"""Human assessment contracts: no database, providers or private source data."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.speaking_benchmark_human import (
    AdjudicationCreate,
    AssessmentSubmit,
    LabelSelection,
    RaterCreate,
    RaterDTO,
)
from app.services.speaking_benchmark_human import (
    assessment_eligible,
    blind_projection,
    pairwise_agreement,
)


def test_nullable_overall_is_literal_and_bands_are_validated():
    data = AssessmentSubmit(expected_revision=0, bands={"fc": 7, "lr": 6.5})
    assert data.bands.overall is None
    assert data.bands.gra is None
    assert data.bands.fc == 7
    for value in (True, 6.2, -1, 10, float("nan")):
        with pytest.raises(ValidationError):
            AssessmentSubmit(expected_revision=0, bands={"overall": value})


def test_internal_identity_is_a_user_not_an_external_alias():
    with pytest.raises(ValidationError):
        RaterCreate(kind="INTERNAL", display_name="Alias", external_key="alias")
    with pytest.raises(ValidationError):
        RaterCreate(kind="EXTERNAL", display_name="Examiner", user_id=uuid4())
    assert RaterCreate(kind="INTERNAL", display_name="Reviewer", user_id=uuid4()).user_id


def test_rater_dto_reads_only_public_attributes():
    row = SimpleNamespace(
        id=uuid4(),
        kind="EXTERNAL",
        display_name="Fictional examiner",
        user_id=None,
        external_key="fictional-report-author",
        created_at=datetime.now(UTC),
        owner_id=uuid4(),
    )
    dto = RaterDTO.model_validate(row)
    assert dto.external_key == "fictional-report-author"
    assert "owner_id" not in dto.model_dump()


def test_unverified_external_claim_is_not_independent_ground_truth():
    row = SimpleNamespace(
        independently_performed=True,
        provenance="external_unverified",
        source_reference="Owner says this was an examiner",
        overall=7,
        fc=None,
        lr=None,
        gra=None,
        pr=None,
    )
    assert not assessment_eligible(row)
    row.provenance = "external_verified_report"
    assert assessment_eligible(row)
    row.source_reference = " "
    assert not assessment_eligible(row)


def test_adjudication_requires_exact_unique_assessments_and_explicit_decision():
    identifier = uuid4()
    with pytest.raises(ValidationError):
        AdjudicationCreate(
            review_revision=1,
            expected_revision=0,
            assessment_ids=[identifier, identifier],
            bands={"overall": 7},
            rationale="Human decision",
        )
    with pytest.raises(ValidationError):
        AdjudicationCreate(
            review_revision=1,
            expected_revision=0,
            assessment_ids=[identifier],
            bands={"overall": 7},
            rationale=" ",
        )
    assert LabelSelection(kind="ADJUDICATED").kind == "ADJUDICATED"


def test_blind_projection_does_not_serialize_score_bearing_sample_fields():
    assignment = SimpleNamespace(
        id=uuid4(),
        sample_id=uuid4(),
        review_revision=2,
        source_sha256="a" * 64,
        manifest_fingerprint="b" * 64,
        revision=1,
        created_at=datetime.now(UTC),
    )
    sample = SimpleNamespace(
        duration_ms=60000, code="Private owner note", prediction={"overall": 9}
    )
    review = SimpleNamespace(
        manifest={
            "segments": [
                {
                    "id": "q1",
                    "part_number": 1,
                    "prompt_type": "SHORT_ANSWER",
                    "prompt_text": "Fictional question?",
                    "cue_points": [],
                    "start_ms": 0,
                    "end_ms": 1000,
                }
            ]
        }
    )
    value = blind_projection(assignment, sample, review, [])
    assert value["questions"][0]["prompt_text"] == "Fictional question?"
    assert (
        not {"prediction", "labels", "human", "adjudication", "code", "other_raters"} & value.keys()
    )
    assert value["audio_url"].endswith(f"/{assignment.id}/audio")


def test_pairwise_agreement_counts_people_and_preserves_missingness():
    left, right = uuid4(), uuid4()
    rows = [
        {"sample_id": str(uuid4()), "rater_id": str(left), "bands": {"fc": 6.5, "overall": None}},
    ]
    rows.append(
        {
            "sample_id": rows[0]["sample_id"],
            "rater_id": str(right),
            "bands": {"fc": 7, "overall": 7},
        }
    )
    result = pairwise_agreement(rows)
    assert result["independent_raters"] == 2
    assert result["independent_samples"] == 1
    fc = result["pairs"][0]["criteria"]["fc"]
    assert fc["mae"] == 0.5
    assert fc["within_0_5"] == 1
    assert fc["quadratic_weighted_kappa"] is None
    assert fc["qwk_status"] == "insufficient_samples"
    overall = result["pairs"][0]["criteria"]["overall"]
    assert overall["count"] == 0
    assert overall["missing_labels"] == 1
