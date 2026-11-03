from types import SimpleNamespace

import pytest
from test_openai_task1_assessment import SourceImageProvider, envelope
from test_task1_visual import request

from app.evaluation.task1.diagnostics import run_diagnostics
from app.services.task1_writing import Task1WritingScoringService


async def trace(*_args):
    pass


async def test_task1_audit_records_actual_image_and_validated_score_without_changing_band():
    for band in (4, 7, 8):
        scorer = Task1WritingScoringService(SourceImageProvider([envelope(score=band)]))
        result = await scorer.assess(request(), trace)
        assert result.criteria.ta.score == band
        audit = scorer.latency_summary()["ta_assessment"]
        assert audit["image_sha256"] == request().image_checksum
        assert audit["source_image_assessment"] is True
        assert audit["validated_score"] == band


def test_run_diagnostics_allowlists_actual_persisted_attempts_and_marks_legacy_unknowns():
    run = SimpleNamespace(
        provider="openai",
        model="gpt-6-luna",
        prompt_version="mts-task1-visual-v12",
        input_fingerprint="a" * 64,
        status="COMPLETED",
        result_json={"criteria": {"ta": {"score": 7, "feedback": "PRIVATE_CONTENT"}}},
        usage_json={
            "latency": {
                "ta_assessment": {
                    "status": "READY",
                    "validated_score": 7,
                    "source_image_assessment": True,
                    "image_sha256": "b" * 64,
                    "secret": "BAD",
                },
                "stages": {
                    "ta.score": {
                        "attempts": [
                            {
                                "provider_attempts": [
                                    {
                                        "profile": "openai_task1_reasoned_v1",
                                        "model": "gpt-6-luna",
                                        "task": "task1",
                                        "stage": "scoring",
                                        "criterion": "ta",
                                        "reasoning_effort": "medium",
                                        "image_detail": "high",
                                        "completion_budget": 16384,
                                        "finish_reason": "stop",
                                        "usage": {"reasoning_tokens": 20},
                                        "chain_of_thought": "BAD",
                                        "api_key": "BAD",
                                        "raw_response": "BAD",
                                    }
                                ]
                            }
                        ]
                    }
                },
            }
        },
    )
    report = run_diagnostics(run)
    assert report["input_fingerprint"] == "a" * 64
    assert report["ta_assessment"]["image_sha256"] == "b" * 64
    assert report["persisted_ta_score"] == 7
    assert report["score_matches_assessment"] is True
    assert report["provider_attempts"][0]["reasoning_effort"] == "medium"
    assert report["cache_hit"] is None
    assert "BAD" not in str(report) and "PRIVATE_CONTENT" not in str(report)
    run.result_json["criteria"]["ta"]["score"] = 8
    assert run_diagnostics(run)["score_matches_assessment"] is False
    run.usage_json = None
    legacy = run_diagnostics(run)
    assert legacy["provider_attempts"] == []
    assert legacy["ta_assessment"] is None
    assert legacy["score_matches_assessment"] is None


@pytest.mark.parametrize("status", [[], {}, 7, None])
def test_malformed_persisted_audit_status_does_not_discard_valid_diagnostics(status):
    run = SimpleNamespace(
        provider="openai",
        model="gpt-6-luna",
        prompt_version="v12",
        input_fingerprint="a" * 64,
        status="COMPLETED",
        result_json=None,
        usage_json={"latency": {"ta_assessment": {"status": status, "image_sha256": "b" * 64}}},
    )
    report = run_diagnostics(run)
    assert report["ta_assessment"]["status"] is None
    assert report["ta_assessment"]["image_sha256"] == "b" * 64
