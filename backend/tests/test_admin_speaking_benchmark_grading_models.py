"""Phase 2 persistence contracts; no providers are constructed."""

import inspect

import pytest

from app.models.base import Base


def test_grading_tables_are_registered_and_constrained():
    import app.models  # noqa: F401

    assert "speaking_benchmark_grading_runs" in Base.metadata.tables
    runs = Base.metadata.tables["speaking_benchmark_grading_runs"]
    attempts = Base.metadata.tables["speaking_benchmark_grading_checkpoints"]
    assert {"owner_id", "review_revision", "configuration", "consent", "prediction"} <= set(
        runs.c.keys()
    )
    assert {"status", "billing_state", "identity", "attempt", "result"} <= set(attempts.c.keys())
    assert any(
        {"sample_id", "review_revision"} == {e.parent.name for e in c.elements}
        for c in runs.foreign_key_constraints
    )


def test_run_schema_rejects_prediction_in_submission():
    from pydantic import ValidationError

    from app.schemas.speaking_benchmark_grading import RunSubmit

    with pytest.raises(ValidationError):
        RunSubmit.model_validate({"prediction": {"fc": 9}})


def test_repository_has_no_provider_dependency():
    import app.repositories.speaking_benchmark_grading as repository

    assert callable(repository.owned_run)
    assert "provider" not in inspect.signature(repository.owned_run).parameters
