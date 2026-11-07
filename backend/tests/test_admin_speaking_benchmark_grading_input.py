"""P2 consumes P1 approvals, never mutable drafts or human labels."""

from types import SimpleNamespace

import pytest
from test_admin_speaking_benchmark import result_for, valid_draft

from app.services.speaking_benchmark_review import manifest_for_review


def test_approved_projection_requires_exact_source_and_frozen_manifest():
    from app.services.speaking_benchmark_audio import approved_projection

    result = result_for()
    draft = valid_draft(result)
    manifest = manifest_for_review(result, draft, 300000)
    sample = SimpleNamespace(source_sha256=result.source_sha256, review_revision=4)
    review = SimpleNamespace(
        revision=3,
        approved_at=True,
        fingerprint="f" * 64,
        manifest=manifest.model_dump(mode="json"),
        draft=draft.model_dump(mode="json"),
    )
    from app.services.speaking_audio import fingerprint

    review.fingerprint = fingerprint([sample.source_sha256, result.identity, review.manifest])
    safe, warnings = approved_projection(sample, review, result, 300000)
    assert len(safe.segments) == 3
    assert warnings == ["HISTORICAL_APPROVED_REVIEW"]
    sample.source_sha256 = "0" * 64
    with pytest.raises(Exception, match="SOURCE_CHANGED"):
        approved_projection(sample, review, result, 300000)


def test_unapproved_review_cannot_supply_inference_input():
    from app.services.speaking_benchmark_audio import approved_projection

    with pytest.raises(Exception, match="APPROVED_REVIEW_REQUIRED"):
        approved_projection(None, SimpleNamespace(approved_at=None), None, 300000)
