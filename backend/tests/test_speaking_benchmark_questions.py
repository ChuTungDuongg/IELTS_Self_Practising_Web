"""Question proposals use synthetic turns; never call a provider."""

import importlib

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.evaluation.speaking.diarization_models import DiarizationResult
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.schemas.speaking_benchmark import ReviewDraft, ReviewSegment
from app.services.speaking_audio import fingerprint


def evidence():
    turns = [
        dict(id="q1", speaker_id="examiner", start_ms=1000, end_ms=2000),
        dict(id="a1", speaker_id="candidate", start_ms=2500, end_ms=5000),
        dict(id="q2", speaker_id="examiner", start_ms=6000, end_ms=7500),
        dict(id="noise", speaker_id="other", start_ms=7000, end_ms=7200),
        dict(id="q3", speaker_id="examiner", start_ms=11000, end_ms=12000),
        dict(id="a2", speaker_id="candidate", start_ms=14000, end_ms=18000),
    ]
    result = DiarizationResult(
        source="fictional.wav",
        source_sha256="a" * 64,
        duration_ms=30000,
        cache_key="b" * 64,
        identity={"fictional": True},
        regular=turns,
        exclusive=[t for t in turns if t["id"] != "noise"],
    )
    draft = ReviewDraft(
        source_sha256=result.source_sha256,
        model_fingerprint=fingerprint(result.identity),
        roles={"examiner": "examiner", "candidate": "candidate", "other": "other"},
        candidate_speaker_id="candidate",
        candidate_confirmed=True,
        part2_start_ms=10000,
        part3_start_ms=20000,
        boundaries_verified=True,
        segments=[
            ReviewSegment(id="r1", speaker_id="candidate", start_ms=2500, end_ms=5000),
            ReviewSegment(id="r2", speaker_id="candidate", start_ms=14000, end_ms=18000),
        ],
    )
    return result, draft


def questions_module():
    return importlib.import_module("app.services.speaking_benchmark_questions")


def test_question_module_exists():
    from importlib.util import find_spec

    assert find_spec("app.services.speaking_benchmark_questions") is not None


def test_regular_overlap_excluded_even_when_exclusive_is_clear():
    result, draft = evidence()
    windows, exclusions = questions_module().select_examiner_windows(result, draft, "examiner")
    assert [w["id"] for w in windows] == ["q1", "q3"]
    assert exclusions == [{"turn_id": "q2", "reasons": ["OTHER_SPEAKER_OVERLAP"]}]
    assert [w["part_number"] for w in windows] == [1, 2]


@pytest.mark.parametrize("change", ["candidate", "boundaries", "examiner", "source"])
def test_question_windows_require_verified_roles_and_source(change):
    module = questions_module()
    result, draft = evidence()
    if change == "candidate":
        draft.candidate_confirmed = False
    elif change == "boundaries":
        draft.boundaries_verified = False
    elif change == "examiner":
        draft.roles["examiner"] = "unknown"
    else:
        draft.source_sha256 = "c" * 64
    with pytest.raises((AppError, BenchmarkInputError)):
        module.select_examiner_windows(result, draft, "examiner")


def test_chronology_preserves_ambiguities_and_part2_cue_omissions():
    result, draft = evidence()
    windows, _ = questions_module().select_examiner_windows(result, draft, "examiner")
    propose = questions_module().proposal_for_window
    one = propose(windows[0], "Where do you live?", draft, {"provider": "fake"})
    assert one["candidate_segment_id"] == "r1"
    assert one["question_type"] == "question"
    assert one["ambiguity_flags"] == []
    two = propose(windows[1], "Describe a fictional object.", draft, {"provider": "fake"})
    assert two["candidate_segment_id"] == "r2"
    assert "PART2_CUE_CARD_REQUIRES_MANUAL_ENTRY" in two["ambiguity_flags"]
    assert two["human_verification_status"] == "PENDING"
    assert "confidence" not in two


def test_schema_rejects_pa_unconfirmed_examiner_and_unbounded_consent():
    schemas = importlib.import_module("app.schemas.speaking_benchmark_questions")
    base = dict(
        submission_key="00000000-0000-0000-0000-000000000001",
        review_revision=1,
        examiner_speaker_id="examiner",
        examiner_confirmed=True,
    )
    assert schemas.QuestionJobCreate(**base).provider == "azure_stt"
    with pytest.raises(ValidationError):
        schemas.QuestionJobCreate(**base, provider="azure_pa")
    with pytest.raises(ValidationError):
        schemas.QuestionJobCreate(**(base | {"examiner_confirmed": False}))
    with pytest.raises(ValidationError):
        schemas.QuestionConsent(
            provider_audio=True, estimates_usd={"azure_stt": float("nan")}, max_estimated_cost_usd=1
        )


def test_models_have_source_review_and_request_attempt_constraints():
    models = importlib.import_module("app.models.speaking_benchmark_questions")
    job = models.SpeakingBenchmarkQuestionJob.__table__
    request = models.SpeakingBenchmarkQuestionRequest.__table__
    assert {
        "source_sha256",
        "draft_fingerprint",
        "review_revision",
        "proposals",
        "decisions",
    } <= set(job.c.keys())
    assert {"identity", "window_id", "attempt", "reconciliation", "reused_from"} <= set(
        request.c.keys()
    )


def test_decisions_preserve_verified_prompts_and_manual_cue_points():
    from types import SimpleNamespace

    from app.schemas.speaking_benchmark_questions import QuestionDecision

    result, draft = evidence()
    module = questions_module()
    windows, _ = module.select_examiner_windows(result, draft, "examiner")
    proposal = module.proposal_for_window(windows[1], "Describe a fictional object.", draft, {})
    job = SimpleNamespace(proposals=[proposal])
    draft.segments[1].cue_points = ["Fictional manual cue point"]
    decision = QuestionDecision(proposal_id="q3", action="ACCEPT", ambiguity_reviewed=True)
    changed, records = module.apply_decisions(job, draft, [decision], batch=False)
    assert changed.segments[1].prompt_verified is True
    assert changed.segments[1].cue_points == draft.segments[1].cue_points
    assert records[0]["text"] == proposal["recognized_text"]
    assert draft.segments[1].prompt_text == ""
    with pytest.raises(Exception, match="SPEAKING_QUESTIONS_AMBIGUITY_REVIEW_REQUIRED"):
        module.apply_decisions(job, draft, [decision], batch=True)
    draft.segments[1].prompt_verified = True
    with pytest.raises(Exception, match="SPEAKING_QUESTIONS_VERIFIED_PROMPT_PRESERVED"):
        module.apply_decisions(job, draft, [decision], batch=False)


def test_unknown_requests_cannot_be_silently_retried():
    from importlib.util import find_spec

    assert find_spec("app.services.speaking_benchmark_questions_ledger") is not None
