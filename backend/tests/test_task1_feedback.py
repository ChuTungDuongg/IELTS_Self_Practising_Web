"""Conservative Task 1 explanations; fake observations cannot revise a band."""

import json
from decimal import Decimal

import pytest
from pydantic import ValidationError
from test_task1_pie_claims import pies
from test_task1_visual import Task1FakeProvider, request

from app.domains.scoring.essay_sources import request_sources
from app.domains.scoring.task1_facts import derive_facts
from app.domains.scoring.task1_feedback import normalize_task1_feedback, render_task1_feedback
from app.domains.scoring.task1_prompts import feedback_prompt
from app.providers.writing_llm.base import Completion
from app.schemas.task1_claims import Task1Analysis, VerifiedClaim
from app.schemas.task1_feedback import RawTask1FeedbackDraft
from app.schemas.writing_ai import EvidenceResult
from app.services.task1_writing import Task1WritingScoringService


def context():
    req = request().model_copy(
        update={
            "response": "Overview.\nAnother language rose from 15% to 20%.\nA sentence ends.Next sentence starts.",
            "paragraph_mode": "textarea",
        }
    )
    visual = pies()
    facts = derive_facts(visual)
    fact = next(
        f for f in facts if f.kind == "absolute_change" and f.subjects == ["Another language"]
    )
    analysis = Task1Analysis(
        visual_family="chart_table",
        confidence="MEDIUM",
        reference=visual,
        derived_facts=facts,
        claims=[
            VerifiedClaim(
                claim_id="c1",
                source_ids=["P2S1"],
                quote="Another language rose from 15% to 20%.",
                claim="A supported comparison.",
                verdict="SUPPORTED",
                explanation="Checked.",
                evidence=[fact.id],
            ),
            VerifiedClaim(
                claim_id="c2",
                source_ids=["P2S1"],
                quote="Another language rose from 15% to 20%.",
                claim="Uncertain assertion.",
                verdict="INSUFFICIENT_EVIDENCE",
                explanation="Unknown.",
                evidence=[],
            ),
        ],
    )
    return req, {s.source_id: s for s in request_sources(req)}, analysis


def observation(**changes):
    return {
        "source_id": "P2S1",
        "kind": "STRENGTH",
        "aspect": "comparison",
        "observation": None,
        "confidence": "HIGH",
        "claim_id": "c1",
        **changes,
    }


def display(items, trait="ta"):
    _, sources, analysis = context()
    draft, issues = normalize_task1_feedback(
        RawTask1FeedbackDraft(observations=items), sources, trait, Decimal("7"), analysis
    )
    output, evidence = render_task1_feedback(draft, sources)
    return output, evidence, issues


def test_supported_report_is_not_an_omission_and_empty_weaknesses_are_valid():
    output, evidence, issues = display(
        [
            observation(),
            observation(kind="LIMITATION", aspect="omission", observation="Cần thêm so sánh này."),
        ]
    )
    assert len(output.strengths) == len(evidence.evidence) == 1
    assert output.improvements == [] and len(issues.dropped) == 1
    assert "Đoạn 2" not in output.strengths[0] and evidence.evidence[0].source_id == "P2S1"
    assert "Đoạn 2" in evidence.evidence[0].assessment
    assert "Cần thêm" not in output.feedback


@pytest.mark.parametrize(
    "bad",
    [
        observation(
            kind="ERROR",
            aspect="factual_accuracy",
            observation="Another language remained at 10%.",
            original_span="Another language",
        ),
        observation(
            kind="ERROR", aspect="factual_accuracy", claim_id="c2", original_span="Another language"
        ),
        observation(source_id="P99S1"),
        observation(claim_id="invented"),
        observation(confidence="LOW"),
        {"broken": True},
    ],
)
def test_bad_ta_observation_is_dropped_locally_without_erasing_valid_feedback(bad):
    output, _, issues = display([bad, observation()])
    assert len(output.strengths) == 1 and output.improvements == []
    assert issues.dropped and "10%" not in output.feedback


def test_contradiction_uses_backend_fact_text_and_exact_source():
    _, sources, analysis = context()
    analysis.claims[0].verdict = "CONTRADICTED"
    raw = RawTask1FeedbackDraft(
        observations=[
            observation(kind="ERROR", aspect="factual_accuracy", original_span="Another language")
        ]
    )
    draft, issues = normalize_task1_feedback(raw, sources, "ta", Decimal("7"), analysis)
    output, _ = render_task1_feedback(draft, sources)
    assert not issues.dropped and len(output.improvements) == 1
    assert "Another language" in output.feedback and "5" in output.feedback


@pytest.mark.parametrize(
    "trait,aspect,text",
    [
        ("gra", "cohesion", "Add discourse markers for flow."),
        ("gra", "grammar", "Cần thêm từ nối để chuyển ý mạch lạc."),
        ("lr", "precision", "Replace names with synonyms merely for lexical variety."),
        ("cc", "cohesion", "Add a connector between every sentence."),
    ],
)
def test_criterion_leakage_and_variety_quotas_are_dropped(trait, aspect, text):
    output, _, issues = display(
        [observation(kind="LIMITATION", aspect=aspect, observation=text, claim_id=None)], trait
    )
    assert output.improvements == [] and issues.dropped


def test_fixed_chart_label_is_not_an_optional_synonym_target():
    output, _, issues = display(
        [
            observation(
                kind="OPTIONAL_REFINEMENT",
                aspect="precision",
                observation="More expressive wording.",
                claim_id=None,
                original_span="Another language",
                suggested_revision="A foreign tongue",
            )
        ],
        "lr",
    )
    assert output.improvements == [] and issues.dropped


def test_linguistic_feedback_does_not_guess_labels_before_grounding_finishes():
    _, sources, analysis = context()
    analysis.reference = None
    candidate = observation(
        kind="OPTIONAL_REFINEMENT",
        aspect="precision",
        observation="More expressive wording.",
        claim_id=None,
        original_span="Another language",
        suggested_revision="A foreign tongue",
    )
    draft, issues = normalize_task1_feedback(
        RawTask1FeedbackDraft(observations=[candidate]), sources, "lr", Decimal("7"), analysis
    )
    assert draft.observations == [] and issues.dropped


def test_exact_punctuation_error_survives_and_style_stays_optional():
    base = observation(
        source_id="P3S1",
        kind="ERROR",
        aspect="punctuation",
        observation="Thiếu khoảng trắng sau dấu chấm.",
        claim_id=None,
        original_span="ends.Next",
        suggested_revision="ends. Next",
    )
    output, evidence, issues = display([base], "gra")
    assert not issues.dropped and "Thiếu khoảng trắng" in output.improvements[0]
    assert evidence.evidence[0].quote == "A sentence ends.Next sentence starts."
    optional = {
        **base,
        "kind": "OPTIONAL_REFINEMENT",
        "aspect": "style",
        "observation": "Sai nghiêm trọng.",
    }
    output, _, _ = display([optional], "gra")
    assert output.improvements == [] and "Sai nghiêm trọng" not in output.feedback


@pytest.mark.parametrize(
    "change",
    [{"original_span": "invented"}, {"confidence": "MEDIUM"}, {"suggested_revision": "ends.Next"}],
)
def test_ungrounded_low_confidence_or_noop_error_does_not_survive(change):
    item = observation(
        source_id="P3S1",
        kind="ERROR",
        aspect="punctuation",
        observation="An error.",
        claim_id=None,
        original_span="ends.Next",
        suggested_revision="ends. Next",
    )
    output, _, issues = display([{**item, **change}], "gra")
    assert output.improvements == [] and issues.dropped


def test_feedback_has_no_writable_score():
    with pytest.raises(ValidationError):
        RawTask1FeedbackDraft.model_validate({"observations": [], "score": 8})


@pytest.mark.parametrize(
    "trait,contracts",
    [
        ("ta", ["INSUFFICIENT_EVIDENCE", "already reported", "observation=null"]),
        ("cc", ["logical progression", "causal", "every sentence"]),
        ("lr", ["fixed chart labels", "merely for variety", "meaning"]),
        ("gra", ["conceptual transitions", "discourse markers", "actually ungrammatical"]),
    ],
)
def test_task1_feedback_prompt_conservative_contract(trait, contracts):
    req, _, analysis = context()
    system = feedback_prompt(req, trait, EvidenceResult(evidence=[]), analysis, Decimal("7"))[0][
        "content"
    ]
    for term in contracts:
        assert term in system
    assert "not a target to rationalize" in system and "Empty limitation lists are valid" in system


async def test_bad_items_empty_draft_and_feedback_repair_preserve_the_identical_score_requests():
    runs = []
    for observations in [[], [{"broken": True}], [observation(source_id="P99S1")]]:

        class Provider(Task1FakeProvider):
            scores = None
            feedback_items = observations

            async def complete(self, messages, schema, *, options=None):
                if "observations" in schema["properties"]:
                    return Completion(json.dumps({"observations": self.feedback_items}))
                if set(schema["properties"]) == {"score"}:
                    self.scores = (self.scores or []) + [messages]
                return await super().complete(messages, schema, options=options)

        async def trace(event, payload):
            pass

        provider = Provider()
        service = Task1WritingScoringService(provider)
        result = await service.assess(request(), trace)
        assert result is not None and not service.failures
        assert all(getattr(result.criteria, t).score == 7 for t in ("ta", "cc", "lr", "gra"))
        assert result.criteria.ta.improvements == []
        runs.append(sorted(provider.scores, key=lambda messages: messages[0]["content"]))
    assert runs[0] == runs[1] == runs[2]
