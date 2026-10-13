"""Task 2 dependency isolation and grounded feedback, using fictional prose only."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domains.scoring.essay_sources import segment_essay
from app.domains.scoring.mts_prompts import TRAIT_NAMES, feedback_messages, scoring_messages
from app.domains.scoring.writing import WritingScoringRequest
from app.providers.writing_llm.base import Completion
from app.schemas.writing_ai import CriterionBandScore, EvidenceResult
from app.services.mts_writing import MTSWritingScoringService

ESSAY = "Community gardens support neighbours.\n\nGardening creates shared routines."


def observation(**changes):
    return {
        "source_id": "P2S1",
        "kind": "STRENGTH",
        "observation": "Ý hỗ trợ rõ ràng và liên quan đến chủ đề.",
        "original_span": None,
        "suggested_revision": None,
        "confidence": "HIGH",
        **changes,
    }


def draft(**changes):
    from app.schemas.writing_ai import Task2FeedbackDraft

    return Task2FeedbackDraft(observations=[observation(**changes)])


def sources():
    return {s.source_id: s for s in segment_essay(ESSAY)}


def test_generated_assessment_prose_never_enters_task2_score_payload():
    selections = [
        EvidenceResult(
            evidence=[{"source_id": "P1S1", "quote": ESSAY.split("\n")[0], "assessment": text}]
        )
        for text in ("Diễn đạt rất yếu.", "Diễn đạt hoàn toàn chính xác.")
    ]
    messages = [scoring_messages("Discuss gardens.", ESSAY, "gra", e) for e in selections]
    assert messages[0] == messages[1]
    payload = json.loads(messages[0][1]["content"])
    assert set(payload) == {"question", "segmented_essay"}
    assert "P2S1" in payload["segmented_essay"]


def test_feedback_wire_contract_is_structured_and_cannot_write_score():
    from app.schemas.writing_ai import Task2FeedbackDraft

    messages = feedback_messages("Discuss gardens.", ESSAY, "gra", EvidenceResult(evidence=[]), 7.5)
    schema = json.loads(messages[0]["content"].split("JSON schema: ", 1)[1])
    assert set(schema["properties"]) == set(schema["required"]) == {"observations"}
    assert schema["additionalProperties"] is False
    with pytest.raises(ValidationError):
        Task2FeedbackDraft(observations=[], score=9)
    assert set(CriterionBandScore.model_json_schema()["properties"]) == {"score"}
    for band in (0, 6.5, 7, 9):
        assert CriterionBandScore(score=band).score == Decimal(str(band))
    with pytest.raises(ValidationError):
        CriterionBandScore(score=6.3)


@pytest.mark.parametrize("trait", TRAIT_NAMES)
def test_fixed_score_is_metadata_without_a_defect_quota(trait):
    system = feedback_messages("Discuss gardens.", ESSAY, trait, EvidenceResult(evidence=[]), 7.5)[
        0
    ]["content"]
    for guard in (
        "Do not search for defects to justify fixed_score",
        "Empty limitation and improvement lists are valid",
        "If uncertain, omit",
        "does not have to account for every 0.5",
        "only source_id",
    ):
        assert guard in system


@pytest.mark.parametrize(
    "trait,guards",
    [
        (
            "gra",
            [
                "actually ungrammatical",
                "Gerund clauses can be subjects",
                "Linking/copular verbs",
                "OPTIONAL_REFINEMENT",
                "article",
                "subject-verb",
            ],
        ),
        (
            "lr",
            [
                "not recommend synonyms merely for variety",
                "British and American",
                "preserve meaning, register and collocation",
                "accurate topic terminology",
            ],
        ),
        (
            "cc",
            [
                "not the number of linking words",
                "logical progression alone",
                "not require an explicit connector",
                "precise nouns",
            ],
        ),
        (
            "ta",
            [
                "does not require research citations",
                "statistics",
                "named countries",
                "hypothetical example",
                "plausible examples",
            ],
        ),
    ],
)
def test_criterion_feedback_guards_preserve_conservative_semantics(trait, guards):
    system = feedback_messages("Discuss gardens.", ESSAY, trait, EvidenceResult(evidence=[]), 7.5)[
        0
    ]["content"]
    assert all(guard in system for guard in guards)


@pytest.mark.parametrize(
    "changes",
    [
        {"source_id": "P8S1"},
        {"kind": "ERROR", "original_span": "not in the essay"},
        {"observation": "Sai ở đoạn 8, câu 99."},
        {"observation": "Phù hợp Band 6."},
    ],
)
def test_ungrounded_feedback_claims_are_omitted_locally(changes):
    from app.domains.scoring.task2_feedback import validate_task2_feedback

    assert (
        validate_task2_feedback(draft(**changes), sources(), "gra", Decimal("7.5")).observations
        == []
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "ERROR", "confidence": "MEDIUM", "original_span": "Gardening"},
        {"kind": "LIMITATION", "confidence": "LOW"},
        {"kind": "ERROR", "confidence": "HIGH"},
        {"kind": "ERROR", "confidence": "HIGH", "original_span": " "},
        {
            "kind": "OPTIONAL_REFINEMENT",
            "original_span": "Gardening",
            "suggested_revision": " Gardening ",
        },
    ],
)
def test_unconfident_or_ungrounded_negative_claims_and_noop_rewrites_are_omitted(changes):
    from app.domains.scoring.task2_feedback import validate_task2_feedback

    assert (
        validate_task2_feedback(draft(**changes), sources(), "gra", Decimal("7.5")).observations
        == []
    )


def test_optional_error_accusation_is_omitted_without_fabricated_rewrite():
    from app.domains.scoring.task2_feedback import render_task2_feedback, validate_task2_feedback

    value = draft(
        kind="OPTIONAL_REFINEMENT",
        observation="Sai ngữ pháp nghiêm trọng.",
        original_span="creates shared routines",
        suggested_revision="builds shared routines",
    )
    value = validate_task2_feedback(value, sources(), "gra", Decimal("7.5"))
    display, evidence = render_task2_feedback(value, sources())
    public = display.model_dump_json() + evidence.model_dump_json()
    assert "Sai ngữ pháp" not in public and "builds shared routines" not in public
    assert display.improvements == display.strengths == evidence.evidence == []


class Provider:
    def __init__(self, output=None, assessment="Nhận xét chưa kiểm chứng."):
        self.output, self.assessment, self.calls = output, assessment, []

    async def complete(self, messages, schema, *, options=None):
        properties = schema["properties"]
        self.calls.append((messages, schema, options))
        if "verdict" in properties:
            return Completion(
                json.dumps(
                    {
                        "verdict": "ON_TOPIC",
                        "confidence": "HIGH",
                        "source_ids": [],
                        "reason": "Nội dung liên quan.",
                    }
                )
            )
        if "score" in properties:
            return Completion('{"score":7.5}')
        if "evidence" in properties:
            return Completion(
                json.dumps({"evidence": [{"source_id": "P2S1", "assessment": self.assessment}]})
            )
        value = self.output if self.output is not None else {"observations": [observation()]}
        if isinstance(value, BaseException):
            raise value
        return value if isinstance(value, Completion) else Completion(json.dumps(value))


async def grade(provider):
    events = []

    async def trace(event, payload):
        events.append((event, payload))

    service = MTSWritingScoringService(provider)
    result = await service.assess(
        WritingScoringRequest(
            attempt_id=uuid4(),
            writing_task_id=uuid4(),
            prompt="Discuss community gardens.",
            response=ESSAY,
        ),
        trace,
    )
    return result, service, events


async def test_real_orchestration_scores_before_generated_assessment_and_keeps_public_trace():
    providers = [Provider(assessment=text) for text in ("Sai mọi câu.", "Không sai câu nào.")]
    results = [await grade(provider) for provider in providers]
    scores = [[(m, s, o) for m, s, o in p.calls if "score" in s["properties"]] for p in providers]
    assert scores[0] == scores[1] and len(scores[0]) == 4
    for provider in providers:
        criterion_calls = [s for _, s, _ in provider.calls if "verdict" not in s["properties"]]
        assert [set(s["properties"]) for s in criterion_calls] == [
            {"score"},
            {"evidence"},
            {"observations"},
        ] * 4
    result, service, events = results[0]
    assert result.overall_band == 7.5 and not service.failures
    assert result.criteria.gra.strengths and result.criteria.gra.improvements == []
    assert "Sai mọi câu" not in result.model_dump_json()
    assert "P2S1" not in result.criteria.gra.feedback
    ta_events = [
        e for e, p in events if p.criterion == "ta" and e.startswith(("evidence.", "criterion."))
    ]
    assert ta_events.index("criterion.evidence.completed") < ta_events.index(
        "criterion.scoring.started"
    )


@pytest.mark.parametrize(
    "bad",
    [
        Completion("broken JSON"),
        Completion("", finish_reason="length"),
        {"observations": [observation(source_id="P8S1")]},
        {"observations": [observation(kind="ERROR", original_span="invented quote")]},
        {"observations": [], "score": 9},
    ],
)
async def test_recoverable_structured_feedback_failure_never_erases_valid_score(bad):
    result, service, _ = await grade(Provider(output=bad))
    assert result is not None and result.overall_band == 7.5 and not service.failures
    assert result.criteria.gra.strengths == result.criteria.gra.improvements == []
    assert all(state.band_score.score == 7.5 for state in service.states.values())
    assert all(d.attempt <= 2 for d in service.diagnostics)
    assert sum(d.reason == "FEEDBACK_FALLBACK_USED" for d in service.diagnostics) == 4


async def test_empty_observations_are_valid_without_inventing_feedback_or_changing_score():
    result, service, _ = await grade(Provider(output={"observations": []}))
    assert result.overall_band == 7.5 and not service.diagnostics
    assert all(not getattr(result.criteria, t).improvements for t in TRAIT_NAMES)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
async def test_persisted_textarea_four_paragraphs_reach_all_scoring_sources(newline):
    from test_writing_paragraph_identity import production_input

    essay = newline.join(
        [
            "Community gardens support neighbours.",
            "Gardening creates shared routines.",
            "Shared responsibilities help residents cooperate.",
            "These activities can strengthen a community.",
        ]
    )
    request, row = await production_input(essay)
    assert request.response == row.content == essay
    provider = Provider()

    async def trace(event, payload):
        pass

    result = await MTSWritingScoringService(provider).assess(request, trace)
    assert result is not None
    for messages, schema, _ in provider.calls:
        if "verdict" in schema["properties"]:
            continue
        payload = json.loads(messages[1]["content"])
        assert all(f"P{paragraph}S1" in payload["segmented_essay"] for paragraph in range(1, 5))
        assert "P1S2" not in payload["segmented_essay"]
        assert "Community gardens support neighbours." in payload["segmented_essay"]
