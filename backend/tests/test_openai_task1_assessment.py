"""Synthetic workflow contracts, never a claim about IELTS band accuracy."""

import asyncio
import json
from decimal import Decimal

import pytest
from test_task1_visual import Task1FakeProvider, chart, reference, request

from app.domains.writing.task_types import WritingTaskType
from app.providers.writing_llm.base import Completion, ImagePart
from app.services.task1_writing import Task1WritingScoringService


def images(messages):
    return [
        part
        for message in messages
        if isinstance(message["content"], list)
        for part in message["content"]
        if isinstance(part, ImagePart)
    ]


def payload(messages):
    content = messages[1]["content"]
    return json.loads(content if isinstance(content, str) else content[0]["text"])


def envelope(status="READY", score=7):
    return {
        "status": status,
        "score": score if status == "READY" else None,
        "conflicts": [
            {
                "kind": "NUMERIC",
                "component_id": "chart",
                "reference_excerpt": "A: 2010 = 40",
                "image_observation": "A: 2010 = 50",
            }
        ]
        if status == "CONFLICT"
        else [],
    }


class SourceImageProvider(Task1FakeProvider):
    task1_image_assessment = True

    def __init__(self, assessments=(), references=(), **kwargs):
        super().__init__(**kwargs)
        self.assessments = list(assessments) or [envelope()]
        self.references = list(references) or [chart()]
        self.records = []
        self.groundings = self.assessment_calls = 0

    async def complete(self, messages, schema, *, options=None):
        self.records.append((messages, schema, options))
        properties = schema["properties"]
        if "status" in properties and "conflicts" in properties:
            value = self.assessments[min(self.assessment_calls, len(self.assessments) - 1)]
            self.assessment_calls += 1
            if isinstance(value, BaseException):
                raise value
            return Completion(json.dumps(value), {"total_tokens": 9})
        if "reference" in properties:
            value = self.references[min(self.groundings, len(self.references) - 1)]
            self.groundings += 1
            return Completion(
                json.dumps({"reference": value.model_dump(mode="json")}), {"total_tokens": 8}
            )
        if "claims" in properties:
            return Completion(
                json.dumps(
                    {
                        "claims": [
                            {
                                "claim_id": "a-end",
                                "source_ids": ["P1S1"],
                                "kind": "numeric_value",
                                "claim": "A đạt 50 vào năm 2010.",
                                "check": {
                                    "type": "numeric",
                                    "subject": "A",
                                    "category": "2010",
                                    "fact": "value",
                                    "value": 50,
                                },
                            }
                        ]
                    }
                )
            )
        return await super().complete(messages, schema, options=options)


async def grade(provider, req=None):
    events = []

    async def trace(event, value):
        events.append((event, value.model_copy(deep=True)))

    service = Task1WritingScoringService(provider)
    result = await service.assess(req or request(), trace)
    return service, result, events


async def test_ta_gets_same_image_whole_essay_and_explicit_stage_through_gate():
    req = request()
    provider = SourceImageProvider()
    service, result, _ = await grade(provider, req)
    assert result is not None
    assert provider.assessment_calls == 1, (
        "TA must assess image/reference consistency before band checkpoint"
    )
    image_calls = [
        (messages, options) for messages, _, options in provider.records if images(messages)
    ]
    assert len(image_calls) == 2
    assert [options.stage for _, options in image_calls] == ["visual_grounding", "score"]
    for messages, options in image_calls:
        assert images(messages) == [req.image]
        assert options.task == "task1" and options.criterion == "ta"
    assert req.response not in json.dumps(payload(image_calls[0][0]))
    ta_messages = image_calls[1][0]
    assert all(
        sentence in json.dumps(payload(ta_messages)) for sentence in req.response.split(". ")
    )
    assert "Use only supplied grounded reference" not in ta_messages[0]["content"]
    assert "extraction may be wrong" in ta_messages[0]["content"]
    assert service.latency_summary()["ta_assessment"]["status"] == "READY"
    assert all(
        not images(messages)
        for messages, _, options in provider.records
        if options and options.criterion in {"cc", "lr", "gra"}
    )


async def test_conflict_rereads_independently_refreshes_facts_claims_and_feedback():
    wrong = chart(values=(20, 40))
    provider = SourceImageProvider([envelope("CONFLICT"), envelope()], [wrong, chart()])
    service, result, events = await grade(provider)
    assert result is not None and provider.groundings == 2 and provider.assessment_calls == 2
    analysis = result.task1_analysis
    assert analysis.reference == chart()
    assert analysis.claims[0].verdict == "SUPPORTED"
    assert any(
        f.kind == "value" and f.category == "2010" and f.value == 50 for f in analysis.derived_facts
    )
    ta_calls = [(m, o) for m, s, o in provider.records if "conflicts" in s["properties"]]
    assert payload(ta_calls[0][0])["claim_verification"][0]["verdict"] == "CONTRADICTED"
    assert payload(ta_calls[1][0])["claim_verification"][0]["verdict"] == "SUPPORTED"
    feedback = [
        payload(m)
        for m, s, o in provider.records
        if o and o.stage == "feedback" and o.criterion == "ta"
    ]
    assert feedback[0]["verified_claims"][0]["verdict"] == "SUPPORTED"
    reread = next(m for m, _, o in provider.records if o and o.stage == "visual_reconciliation")
    assert request().response not in json.dumps(payload(reread))
    assert "claims" not in payload(reread) and "visual_reference" not in payload(reread)
    # No stale band is published while the reference is disputed.
    ta_started = [p for e, p in events if e == "criterion.feedback.started" and p.criterion == "ta"]
    assert len(ta_started) == 1
    assert service.latency_summary()["ta_assessment"]["reconciliations"] == 1


@pytest.mark.parametrize("status", ["CONFLICT", "UNREADABLE", "INSUFFICIENT_EVIDENCE"])
async def test_unresolved_visual_status_preserves_other_criteria_without_guessed_ta(status):
    provider = SourceImageProvider([envelope(status)])
    service, result, events = await grade(provider)
    assert result is None and set(service.failures) == {"ta"}
    assert service.states["ta"].band_score is None
    assert provider.assessment_calls <= 2 and provider.groundings <= 2
    assert all(service.states[trait].result is not None for trait in ("cc", "lr", "gra"))
    assert not any(e == "criterion.completed" and p.criterion == "ta" for e, p in events)


@pytest.mark.parametrize(
    "kind", ["NUMERIC", "LABEL", "UNIT", "AXIS", "LEGEND", "COVERAGE", "MAP", "PROCESS"]
)
async def test_material_conflict_kinds_get_one_reconciliation(kind):
    conflict = envelope("CONFLICT")
    conflict["conflicts"][0]["kind"] = kind
    provider = SourceImageProvider([conflict, envelope()])
    _, result, _ = await grade(provider)
    assert result is not None and provider.groundings == 2


@pytest.mark.parametrize(
    "family,task_type", [("map", WritingTaskType.MAP_PLAN), ("process", WritingTaskType.PROCESS)]
)
async def test_map_process_assessment_uses_original_image(family, task_type):
    req = request()
    req.task_type = task_type
    provider = SourceImageProvider(references=[reference(family)])
    _, result, _ = await grade(provider, req)
    assert result is not None and result.task1_analysis.visual_family == family
    assert provider.assessment_calls == 1


async def test_vllm_keeps_text_ta_path():
    provider = SourceImageProvider()
    provider.task1_image_assessment = False
    _, result, _ = await grade(provider)
    assert result is not None and provider.assessment_calls == 0
    assert sum(bool(images(m)) for m, _, _ in provider.records) == 1


async def test_cancellation_during_ta_reconciliation_propagates():
    provider = SourceImageProvider([envelope("CONFLICT"), asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await grade(provider)


async def test_bad_envelope_cannot_publish_ready_score_with_conflicts():
    invalid = envelope("CONFLICT")
    invalid.update(status="READY", score=7)
    provider = SourceImageProvider([invalid])
    service, result, _ = await grade(provider)
    assert result is None and service.states["ta"].band_score is None
    assert provider.assessment_calls == 2  # one schema repair, no visual reread
    assert provider.groundings == 1
    assert service.latency_summary()["ta_assessment"]["status"] == "FAILED"


async def test_fallible_text_relevance_cannot_bypass_source_image_audit_and_publish_band_one():
    class Provider(SourceImageProvider):
        relevance_calls = 0

        async def complete(self, messages, schema, *, options=None):
            if "verdict" in schema["properties"]:
                self.relevance_calls += 1
                return Completion(
                    json.dumps(
                        {
                            "verdict": "WHOLLY_UNRELATED",
                            "confidence": "HIGH",
                            "source_ids": [],
                            "reason": "Nhãn trích xuất sai khiến bài có vẻ không liên quan.",
                        }
                    )
                )
            return await super().complete(messages, schema, options=options)

    wrong = chart().model_copy(deep=True)
    wrong.components[0].series[0].name = "Incorrectly extracted label"
    provider = Provider([envelope("CONFLICT"), envelope()], [wrong, chart()])
    _, result, events = await grade(provider)
    assert provider.assessment_calls == 2 and provider.groundings == 2
    assert result.criteria.ta.score == Decimal(7) and result.relevance is None
    assert provider.relevance_calls == 0
    assert len([p for e, p in events if e == "criterion.completed" and p.criterion == "ta"]) == 1
