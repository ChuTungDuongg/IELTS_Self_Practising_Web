"""Exact saved-text annotations and concise feedback, with fake inference only."""

import json
from decimal import Decimal

import pytest
from pydantic import ValidationError
from test_task1_feedback import context
from test_task1_visual import Task1FakeProvider
from test_task1_visual import request as task1_request
from test_writing_completion_budgets import BudgetProvider, assess

from app.domains.scoring.essay_sources import segment_essay
from app.domains.scoring.task1_feedback import normalize_task1_feedback
from app.domains.scoring.task2_feedback import normalize_task2_feedback, render_task2_feedback
from app.providers.writing_llm.base import Completion
from app.schemas.writing_ai import CriterionResult, RawTask2FeedbackDraft
from app.services.task1_writing import Task1WritingScoringService


def observation(**changes):
    return {
        "source_id": "P1S1",
        "kind": "ERROR",
        "observation": "Chủ ngữ số nhiều cần động từ dạng nguyên mẫu.",
        "original_span": "people tends to",
        "suggested_revision": "people tend to",
        "confidence": "HIGH",
        **changes,
    }


def normalize(essay, items, trait="gra"):
    sources = {s.source_id: s for s in segment_essay(essay)}
    draft, issues = normalize_task2_feedback(
        RawTask2FeedbackDraft(observations=items), sources, trait, Decimal("7")
    )
    return draft, sources, issues


def annotations(essay, items, trait="gra"):
    from app.domains.scoring.writing_annotations import build_writing_annotations

    draft, sources, _ = normalize(essay, items, trait)
    return build_writing_annotations(essay, sources, trait, draft.observations)


def test_historical_criterion_defaults_to_no_annotations_and_public_bounds_are_strict():
    card = CriterionResult(score=7, feedback="Clear.", strengths=[], improvements=[], evidence=[])
    assert card.annotations == []
    assert card.feedback_status == "COMPLETED"
    from app.schemas.writing_ai import WritingAnnotation

    item = annotations("people tends to agree.", [observation()])[0]
    for update in [{"end_offset": item.start_offset}, {"start_offset": -1}, {"confidence": "LOW"}]:
        with pytest.raises(ValidationError):
            WritingAnnotation.model_validate({**item.model_dump(), **update})


def test_utf16_crlf_and_repeated_phrase_in_different_sources_resolve_exact_saved_text():
    essay = "😀 First line.\r\n\r\npeople tends to agree. people tends to object."
    items = [observation(source_id="P2S2"), observation(source_id="P2S1")]
    result = annotations(essay, items)
    assert len(result) == 2 and result[0].start_offset < result[1].start_offset
    encoded = essay.encode("utf-16-le")
    for item in result:
        assert (
            encoded[item.start_offset * 2 : item.end_offset * 2].decode("utf-16-le")
            == item.original_span
        )
    assert result[0].start_offset == essay.index("people tends to") + 1
    assert [a.id for a in result] == [a.id for a in annotations(essay, list(reversed(items)))]


def test_ambiguous_span_retains_panel_feedback_but_creates_no_inline_annotation():
    essay = "people tends to agree and people tends to object."
    draft, sources, _ = normalize(essay, [observation()])
    assert len(draft.observations) == 1
    assert render_task2_feedback(draft, sources)[0].improvements
    assert annotations(essay, [observation()]) == []


def test_annotation_dedup_ignores_alternative_explanations_of_same_issue():
    items = [observation(), observation(observation="Động từ chưa hòa hợp với chủ ngữ.")]
    assert len(annotations("people tends to agree.", items)) == 1


def test_overlapping_spans_for_identical_source_correction_are_deduplicated():
    items = [observation(), observation(original_span="tends", suggested_revision="tend")]
    result = annotations("people tends to agree.", items)
    assert len(result) == 1
    assert result == annotations("people tends to agree.", list(reversed(items)))


def test_whole_observation_bounds_never_clip_revision_or_quote():
    long = "Một câu hoàn chỉnh. " + "phần chưa hoàn thành " * 30
    items = [observation(observation=long), observation(suggested_revision="x" * 241)]
    draft, sources, issues = normalize("people tends to agree.", items)
    assert len(draft.observations) == 1
    assert draft.observations[0].observation == "Một câu hoàn chỉnh."
    assert draft.observations[0].suggested_revision == "people tend to"
    display, _ = render_task2_feedback(draft, sources)
    assert "…" not in display.feedback and "Một câu hoàn chỉnh." in display.feedback
    assert issues.normalized and issues.dropped
    assert (
        normalize("people tends to agree.", [observation(observation="x" * 241)])[0].observations
        == []
    )


def test_oversized_observation_cannot_end_at_an_abbreviation_mid_thought():
    text = "Ví dụ dùng cụm e.g. " + "x" * 260
    draft, _, issues = normalize("people tends to agree.", [observation(observation=text)])
    assert draft.observations == [] and issues.dropped


def test_selection_prefers_high_confidence_errors_then_caps_at_four_distinct_items():
    essay = "people tends to agree. Birds sings loudly. Residents shares tools. Workers needs rest."
    items = [
        observation(
            kind="STRENGTH", original_span=None, suggested_revision=None, observation=f"Rõ ý {i}."
        )
        for i in range(6)
    ]
    for index, span, revision in [
        (1, "people tends to", "people tend to"),
        (2, "Birds sings", "Birds sing"),
        (3, "Residents shares", "Residents share"),
        (4, "Workers needs", "Workers need"),
    ]:
        items.append(
            observation(source_id=f"P1S{index}", original_span=span, suggested_revision=revision)
        )
    draft, _, _ = normalize(essay, items)
    assert len(draft.observations) == 4 and all(i.kind == "ERROR" for i in draft.observations)
    assert draft == normalize(essay, list(reversed(items)))[0]


def test_summary_includes_only_whole_items_without_paragraph_labels():
    essay = "First. Second. Third. Fourth."
    items = [
        observation(
            source_id=f"P1S{i}",
            kind="LIMITATION",
            original_span=None,
            suggested_revision=None,
            observation=(f"Nhận xét {i}: " + "x" * 209 + "."),
        )
        for i in range(1, 5)
    ]
    draft, sources, _ = normalize(essay, items, "cc")
    display, _ = render_task2_feedback(draft, sources)
    assert len(display.improvements) == 4
    assert "Đoạn" not in display.feedback and "Đoạn" not in " ".join(display.improvements)
    assert display.feedback == " ".join(i.observation for i in draft.observations[:2])
    assert not display.feedback.endswith("…")


@pytest.mark.parametrize(
    "trait,essay,span,revision,message",
    [
        (
            "gra",
            "Learning languages is useful.",
            "Learning languages is useful",
            "It is useful to learn languages",
            "A gerund cannot be the subject.",
        ),
        (
            "gra",
            "Prices remain stable.",
            "remain stable",
            "are stable",
            "A linking verb needs another main verb.",
        ),
        (
            "gra",
            "The proposal seems reasonable.",
            "seems reasonable",
            "is reasonable",
            "Missing main verb after the copular verb.",
        ),
        (
            "gra",
            "This remains an important issue.",
            "remains an important issue",
            "is still an important issue",
            "A copular verb cannot have a noun complement.",
        ),
        (
            "gra",
            "I bought apples, pears and oranges.",
            "pears and",
            "pears, and",
            "An Oxford comma is required.",
        ),
        ("lr", "The colour is grey.", "colour", "color", "Lỗi chính tả."),
        (
            "lr",
            "This is important.",
            "important",
            "significant",
            "Use a more sophisticated synonym.",
        ),
        ("gra", "The goverment acts.", "goverment", "government", "Lỗi chính tả."),
        (
            "lr",
            "people tends to agree.",
            "people tends to",
            "people tend to",
            "Subject-verb agreement is incorrect.",
        ),
    ],
)
def test_valid_constructions_variants_and_wrong_criterion_claims_are_omitted(
    trait, essay, span, revision, message
):
    draft, _, issues = normalize(
        essay,
        [observation(original_span=span, suggested_revision=revision, observation=message)],
        trait,
    )
    assert draft.observations == [] and issues.dropped


def test_actual_spelling_is_lr_and_task1_uses_shared_guard_and_resolver():
    essay = "The goverment acts."
    result = annotations(
        essay,
        [
            observation(
                original_span="goverment",
                suggested_revision="government",
                observation="Lỗi chính tả.",
            )
        ],
        "lr",
    )
    assert result[0].criterion == "lr" and result[0].category == "spelling"
    req, sources, analysis = context()
    from app.domains.scoring.writing_annotations import build_writing_annotations
    from app.schemas.task1_feedback import RawTask1FeedbackDraft

    draft, _ = normalize_task1_feedback(
        RawTask1FeedbackDraft(
            observations=[
                observation(
                    source_id="P3S1",
                    aspect="punctuation",
                    claim_id=None,
                    original_span="ends.Next",
                    suggested_revision="ends. Next",
                    observation="Thiếu khoảng trắng sau dấu chấm.",
                )
            ]
        ),
        sources,
        "gra",
        Decimal("7"),
        analysis,
    )
    assert (
        build_writing_annotations(req.response, sources, "gra", draft.observations)[0].original_span
        == "ends.Next"
    )


@pytest.mark.parametrize(
    "essay,span,revision,message",
    [
        (
            "Living in large cities can be expensive.",
            "Living in large cities",
            "People living in large cities",
            "Missing subject.",
        ),
        (
            "This remains an important issue.",
            "remains an important issue",
            "is still an important issue",
            "Missing verb/complement.",
        ),
    ],
)
def test_plain_missing_subject_or_verb_claim_does_not_flag_valid_construction(
    essay, span, revision, message
):
    draft, _, issues = normalize(
        essay, [observation(original_span=span, suggested_revision=revision, observation=message)]
    )
    assert draft.observations == [] and issues.dropped


def test_optional_feedback_retains_useful_complete_context_without_error_accusations():
    draft, sources, _ = normalize(
        "A sentence ends.Next sentence starts.",
        [
            observation(
                kind="OPTIONAL_REFINEMENT",
                original_span="ends.Next",
                suggested_revision="ends. Next",
                observation="Có thể dùng hai câu ngắn để làm rõ quan hệ giữa các ý.",
            )
        ],
    )
    display, _ = render_task2_feedback(draft, sources)
    assert "Có thể dùng hai câu ngắn" in display.improvements[0]


def test_optional_error_accusation_is_omitted_instead_of_fabricated_refinement():
    essay = "A sentence ends.Next sentence starts."
    items = [
        observation(
            kind="OPTIONAL_REFINEMENT",
            original_span="ends.Next",
            suggested_revision="ends. Next",
            observation="Sai nghiêm trọng.",
        )
    ]
    draft, _, issues = normalize(essay, items)
    assert draft.observations == [] and issues.dropped
    assert annotations(essay, items) == []


async def test_intentional_empty_task2_feedback_is_valid_without_unavailable_fallback():
    result, service, _ = await assess(BudgetProvider(feedback=[{"observations": []}]))
    assert "Chưa xác định" in result.criteria.ta.feedback
    assert not service.diagnostics


@pytest.mark.parametrize("task", [1, 2])
async def test_feedback_events_follow_accepted_score_and_emit_only_valid_annotations(task):
    req = (
        task1_request().model_copy(update={"response": "people tends to agree."})
        if task == 1
        else None
    )
    base = Task1FakeProvider if task == 1 else BudgetProvider
    events = []

    class Provider(base):
        async def complete(self, messages, schema, *, options=None):
            if "decisions" in schema["properties"]:
                assert task == 1
                return Completion(
                    json.dumps(
                        {
                            "decisions": [
                                {
                                    "observation_index": 0,
                                    "accept": True,
                                    "reason_code": "CLEAR_LANGUAGE_ERROR",
                                }
                            ]
                        }
                    )
                )
            if "observations" in schema["properties"]:
                trait = (
                    "gra" if "Grammatical Range and Accuracy" in messages[0]["content"] else "ta"
                )
                if trait == "gra":
                    assert any(
                        e == "criterion.feedback.started" and p.criterion == "gra"
                        for e, p in events
                    )
                items = (
                    [observation(aspect="grammar", claim_id=None)]
                    if task == 1 and trait == "gra"
                    else [observation()]
                    if trait == "gra"
                    else []
                )
                return Completion(json.dumps({"observations": items}))
            return await super().complete(messages, schema, options=options)

    async def trace(event, payload):
        events.append((event, payload))

    from uuid import uuid4

    from app.domains.scoring.writing import WritingScoringRequest
    from app.services.mts_writing import MTSWritingScoringService

    req = req or WritingScoringRequest(
        attempt_id=uuid4(),
        writing_task_id=uuid4(),
        prompt="Discuss fictional communities.",
        response="people tends to agree.",
    )
    service = (Task1WritingScoringService if task == 1 else MTSWritingScoringService)(Provider())
    result = await service.assess(req, trace)
    assert result is not None and len(result.criteria.gra.annotations) == 1
    assert result.criteria.gra.feedback_status == "COMPLETED"
    local = [(e, p) for e, p in events if p.criterion == "gra"]
    names = [e for e, _ in local]
    assert (
        names.index("criterion.scoring.validation.started")
        < names.index("criterion.feedback.started")
        < names.index("criterion.feedback.annotation")
        < names.index("criterion.feedback.completed")
        < names.index("criterion.completed")
    )
    assert all(p.stage == "feedback" for e, p in local if e.startswith("criterion.feedback."))
    assert (
        next(p.annotation for e, p in local if e == "criterion.feedback.annotation")
        == result.criteria.gra.annotations[0]
    )
    assert (
        next(p.result for e, p in local if e == "criterion.feedback.completed")
        == result.criteria.gra
    )
    assert (
        next(p.result for e, p in local if e == "criterion.feedback.started").feedback_status
        == "PENDING"
    )


async def test_feedback_fallback_completes_without_fabricated_annotations():
    provider = BudgetProvider(feedback=[{"observations": "invalid"}, {"observations": "invalid"}])
    result, service, events = await assess(provider)
    assert result.criteria.ta.score == Decimal("6.5") and result.criteria.ta.annotations == []
    assert result.criteria.ta.feedback_status == "UNAVAILABLE"
    assert not service.failures
    local = [(e, p) for e, p in events if p.criterion == "ta"]
    assert not any(e == "criterion.feedback.annotation" for e, _ in local)
    assert next(p.result for e, p in local if e == "criterion.feedback.completed").score == Decimal(
        "6.5"
    )


def test_concise_prompts_and_versions_preserve_score_only_meaning():
    from app.domains.scoring.mts_prompts import (
        AI_WRITING_PROMPT_VERSION,
        SCORE_ONLY_GUIDANCE,
        TASK2_FEEDBACK_GUIDANCE,
        effective_prompt_version,
    )
    from app.domains.scoring.task1_prompts import TASK1_CONSERVATIVE_FEEDBACK
    from app.services.task1_input import TASK1_PROMPT_VERSION, TASK1_SCORING_PROMPT_VERSION

    assert AI_WRITING_PROMPT_VERSION == effective_prompt_version("mts-task2-v11") == "mts-task2-v12"
    assert TASK1_PROMPT_VERSION == "mts-task1-visual-v12"
    assert TASK1_SCORING_PROMPT_VERSION == "mts-task1-scoring-v12"
    assert "at most 4" in TASK2_FEEDBACK_GUIDANCE and "at most 4" in TASK1_CONSERVATIVE_FEEDBACK
    assert SCORE_ONLY_GUIDANCE == (
        "Score 0 through 9 in increments of 0.5 only. Return ONLY one field: score. "
        "Do not return feedback, strengths, improvements, rationale, calibration or metadata. "
        'Return a tiny complete JSON object, for example {"score":6.5}.'
    )


def test_task1_current_benchmark_version_is_explicit_and_old_reports_remain_readable():
    from app.core.config import Settings
    from app.evaluation.task1.models import BenchmarkConfig
    from app.evaluation.task1.runner import configurations

    configs = configurations(Settings(_env_file=None), "both", "off")
    assert {c.scoring_version for c in configs} == {"v5", "v12"}
    current = next(c for c in configs if c.scoring_version == "v12")
    assert current.prompt_version == "mts-task1-visual-v12"
    with pytest.raises(ValueError, match="BENCHMARK_CONFIGURATION_INVALID"):
        configurations(Settings(_env_file=None), "v10", "off")
    old = {
        **current.model_dump(),
        "scoring_version": "v10",
        "prompt_version": "mts-task1-visual-v10",
        "scoring_prompt_version": "mts-task1-scoring-v10",
    }
    assert BenchmarkConfig.model_validate(old).scoring_version == "v10"
