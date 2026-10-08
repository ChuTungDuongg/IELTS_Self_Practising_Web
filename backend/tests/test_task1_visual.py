import base64
import json
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.domains.scoring.task1_facts import derive_facts
from app.domains.scoring.task1_verification import verify_claim
from app.domains.writing.task_types import TASK_ONE_TYPES, WritingTaskType
from app.domains.writing.visual_families import VISUAL_FAMILIES, visual_family
from app.providers.writing_llm import create_provider
from app.providers.writing_llm.base import Completion, ImagePart
from app.providers.writing_llm.messages import serialize_messages
from app.schemas.task1_claims import ExtractedClaim, Task1Analysis
from app.schemas.task1_visual import VisualGroundingOutput
from app.services.task1_grounding import Task1VisualGroundingService
from app.services.task1_input import TASK1_PROMPT_VERSION, Task1ScoringRequest
from app.services.task1_writing import Task1WritingScoringService
from app.services.writing_ai import input_fingerprint

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS5kAAAAASUVORK5CYII="
)
ESSAY = "A increased from 20 to 50. B fell from 30 to 10."


def chart(confidence="HIGH", values=(20, 50), other=(30, 10)):
    return VisualGroundingOutput.model_validate(
        {
            "reference": {
                "visual_family": "chart_table",
                "confidence": confidence,
                "summary": "A tăng và B giảm.",
                "components": [
                    {
                        "id": "chart",
                        "kind": "line_graph",
                        "unit": "percent",
                        "ordered_categories": True,
                        "categories": ["2000", "2010"],
                        "series": [
                            {
                                "id": "a",
                                "name": "A",
                                "points": [
                                    {"category": category, "value": value, "confidence": 0.95}
                                    for category, value in zip(
                                        ["2000", "2010"], values, strict=True
                                    )
                                ],
                            },
                            {
                                "id": "b",
                                "name": "B",
                                "points": [
                                    {"category": category, "value": value, "confidence": 0.95}
                                    for category, value in zip(["2000", "2010"], other, strict=True)
                                ],
                            },
                        ],
                    }
                ],
            }
        }
    ).reference


def reference(family):
    contents = {
        "chart_table": chart().model_dump(mode="json"),
        "process": {
            "process_kind": "linear",
            "stages": [{"id": "s1", "label": "Collect"}, {"id": "s2", "label": "Sort"}],
            "edges": [{"source": "s1", "target": "s2"}],
            "starts": ["s1"],
            "ends": ["s2"],
        },
        "map": {
            "states": [
                {
                    "id": "old",
                    "label": "2000",
                    "features": [{"id": "forest", "label": "Forest", "location": "north"}],
                },
                {
                    "id": "new",
                    "label": "2010",
                    "features": [{"id": "shops", "label": "Shops", "location": "north"}],
                },
            ],
            "changes": [
                {
                    "kind": "replacement",
                    "from_state": "old",
                    "to_state": "new",
                    "before": "forest",
                    "after": "shops",
                    "location": "north",
                }
            ],
        },
        "system": {
            "components": [{"id": "in", "label": "Intake"}, {"id": "out", "label": "Tank"}],
            "connections": [{"source": "in", "target": "out"}],
            "inputs": ["in"],
            "outputs": ["out"],
        },
        "other": {
            "entities": [{"id": "x", "label": "Object"}],
            "relationships": [],
            "observations": ["Một vật thể được thể hiện."],
        },
    }
    return VisualGroundingOutput.model_validate(
        {"reference": {"visual_family": family, "confidence": "HIGH", **contents[family]}}
    ).reference


@pytest.mark.parametrize(
    "task_type,family", [(name, family.value) for name, family in VISUAL_FAMILIES.items()]
)
def test_family_mapping_covers_existing_taxonomy(task_type, family):
    assert visual_family(task_type).value == family
    assert set(VISUAL_FAMILIES) == TASK_ONE_TYPES


@pytest.mark.parametrize("family", ["chart_table", "process", "map", "system", "other"])
def test_typed_family_round_trip(family):
    value = reference(family)
    assert (
        VisualGroundingOutput.model_validate_json(
            VisualGroundingOutput(reference=value).model_dump_json()
        ).reference
        == value
    )


def test_tables_pies_and_mixed_charts_keep_structure_and_units():
    table = {
        "id": "t",
        "kind": "table",
        "row_headers": ["A", "B"],
        "column_headers": ["Count"],
        "cells": [{"row": "A", "column": "Count", "value": None, "confidence": 0.2}],
    }
    pie = {
        "id": "p",
        "kind": "pie_chart",
        "state": "2010",
        "unit": "percent",
        "categories": ["Slice"],
        "series": [
            {
                "id": "pie",
                "name": "Share",
                "points": [{"category": "Slice", "value": 40, "confidence": 0.9}],
            }
        ],
    }
    value = VisualGroundingOutput.model_validate(
        {
            "reference": {
                "visual_family": "chart_table",
                "confidence": "MEDIUM",
                "components": [table, pie],
            }
        }
    ).reference
    assert value.components[0].x_axis is None and value.components[1].x_axis is None
    assert value.components[0].cells[0].value is None
    assert not any(fact.kind == "start" for fact in derive_facts(value))


@pytest.mark.parametrize("family", ["process", "system", "other", "map"])
def test_invalid_relation_endpoints_rejected(family):
    data = reference(family).model_dump(mode="json")
    if family == "map":
        data["changes"][0]["after"] = "unknown"
    else:
        field = {"process": "edges", "system": "connections", "other": "relationships"}[family]
        data[field] = [{"source": "missing", "target": "unknown"}]
    with pytest.raises(ValidationError):
        VisualGroundingOutput.model_validate({"reference": data})


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan")])
def test_numeric_confidence_bounds(confidence):
    data = chart().model_dump(mode="json")
    data["components"][0]["series"][0]["points"][0]["confidence"] = confidence
    with pytest.raises(ValidationError):
        VisualGroundingOutput.model_validate({"reference": data})


def test_invalid_family_numeric_structure_and_duplicate_ids_rejected():
    for change in ({"visual_family": "unknown"}, {"confidence": "unknown"}):
        with pytest.raises(ValidationError):
            VisualGroundingOutput.model_validate(
                {"reference": {**chart().model_dump(mode="json"), **change}}
            )
    data = chart().model_dump(mode="json")
    data["components"][0]["series"][0]["points"][0]["value"] = "unreadable"
    with pytest.raises(ValidationError):
        VisualGroundingOutput.model_validate({"reference": data})
    data = chart().model_dump(mode="json")
    data["components"].append(data["components"][0])
    with pytest.raises(ValidationError):
        VisualGroundingOutput.model_validate({"reference": data})


def test_display_lengths_normalized_without_weakening_structure():
    data = chart().model_dump(mode="json")
    data.update(summary="Dữ liệu. " * 200, uncertainty=["Ghi chú. " * 100] * 12)
    value = VisualGroundingOutput.model_validate({"reference": data}).reference
    assert len(value.summary) == 600 and len(value.uncertainty) == 4
    assert all(len(note) <= 240 for note in value.uncertainty)


def test_decimal_facts_extrema_changes_rankings_and_crossovers():
    facts = derive_facts(chart())

    def find(kind, name, category=None):
        return next(
            fact
            for fact in facts
            if fact.kind == kind
            and name in fact.subjects
            and (category is None or fact.category == category)
        )

    assert find("min", "A").value == Decimal(20)
    assert find("max", "A").value == Decimal(50)
    assert find("start", "A").value == Decimal(20)
    assert find("end", "A").value == Decimal(50)
    assert find("absolute_change", "A").value == Decimal(30)
    assert find("percentage_change", "A").value == Decimal(150)
    assert find("rank", "A", "2000").value == Decimal(2)
    assert find("rank", "A", "2010").value == Decimal(1)
    assert find("rank_change", "A").value == Decimal(1)
    assert find("largest_increase", "A").value == Decimal(30)
    assert find("largest_decrease", "B").value == Decimal(-20)
    assert find("overall_direction", "B").direction == "decrease"
    assert find("crossover", "A").subjects == ["A", "B"]


def test_zero_start_stability_ties_and_missing_or_uncertain_values():
    zero = derive_facts(chart(values=(0, 50)))
    assert not any(f.kind == "percentage_change" and f.subjects == ["A"] for f in zero)
    stable = derive_facts(chart(values=(20, 20), other=(20, 20)))
    assert len([f for f in stable if f.kind == "stable"]) == 2
    assert all(f.value == 1 for f in stable if f.kind == "rank")
    missing = derive_facts(chart(values=(None, 50)))
    assert not any(
        f.subjects == ["A"] and f.kind in {"min", "max", "start", "absolute_change"}
        for f in missing
    )
    value = chart()
    value.components[0].series[0].points[0].confidence = 0.2
    assert not any(
        f.kind == "value" and f.subjects == ["A"] and f.category == "2000"
        for f in derive_facts(value)
    )
    assert derive_facts(chart(confidence="LOW")) == []


@pytest.mark.parametrize(
    "check,verdict",
    [
        (
            {"type": "numeric", "subject": "A", "fact": "value", "category": "2000", "value": 20},
            "SUPPORTED",
        ),
        (
            {"type": "numeric", "subject": "A", "fact": "value", "category": "2000", "value": 99},
            "CONTRADICTED",
        ),
        (
            {"type": "numeric", "subject": "A", "fact": "percentage_change", "value": 150},
            "SUPPORTED",
        ),
        (
            {"type": "numeric", "subject": "A", "fact": "percentage_change", "value": 200},
            "CONTRADICTED",
        ),
        (
            {"type": "numeric", "subject": "A", "fact": "rank", "category": "2000", "value": 1},
            "CONTRADICTED",
        ),
        (
            {
                "type": "comparison",
                "subject": "A",
                "other": "B",
                "category": "2010",
                "operator": "gt",
            },
            "SUPPORTED",
        ),
        (
            {
                "type": "comparison",
                "subject": "A",
                "other": "Unknown",
                "category": "2010",
                "operator": "gt",
            },
            "INSUFFICIENT_EVIDENCE",
        ),
        (
            {"type": "numeric", "subject": "A", "fact": "value", "value": 20},
            "INSUFFICIENT_EVIDENCE",
        ),
    ],
)
def test_deterministic_claim_checks(check, verdict):
    claim = ExtractedClaim(
        claim_id="c1", source_ids=["P1S1"], kind="numeric_value", claim="Nhận định.", check=check
    )
    visual = chart()
    assert verify_claim(claim, visual, derive_facts(visual))[0] == verdict
    low = chart(confidence="LOW")
    assert verify_claim(claim, low, [])[0] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.parametrize(
    "family,check,verdict",
    [
        ("process", {"subject": "Collect", "other": "Sort", "relation": "before"}, "SUPPORTED"),
        ("process", {"subject": "Sort", "other": "Collect", "relation": "before"}, "CONTRADICTED"),
        ("system", {"subject": "Intake", "other": "Tank", "relation": "connected"}, "SUPPORTED"),
        ("system", {"subject": "Tank", "other": "Intake", "relation": "connected"}, "CONTRADICTED"),
        (
            "map",
            {
                "subject": "Forest",
                "other": "Shops",
                "relation": "replacement",
                "from_state": "2000",
                "to_state": "2010",
            },
            "SUPPORTED",
        ),
        (
            "map",
            {
                "subject": "Forest",
                "other": "Airport",
                "relation": "replacement",
                "from_state": "2000",
                "to_state": "2010",
            },
            "CONTRADICTED",
        ),
    ],
)
def test_non_numeric_visual_claim_checks(family, check, verdict):
    claim = ExtractedClaim(
        claim_id="c1",
        source_ids=["P1S1"],
        kind="other_visual_claim",
        claim="Nhận định.",
        check={"type": "relation", **check},
    )
    assert verify_claim(claim, reference(family), [])[0] == verdict


@pytest.mark.parametrize("provider", ["vllm", "openai"])
@pytest.mark.parametrize(
    "mime,data",
    [
        ("image/png", PNG),
        ("image/jpeg", b"\xff\xd8\xfftrusted"),
        ("image/webp", b"RIFF1234WEBPtrusted"),
    ],
)
async def test_multimodal_adapters_have_one_trusted_image_and_unchanged_text(
    monkeypatch, provider, mime, data
):
    settings = Settings(
        _env_file=None,
        ai_writing_enabled=True,
        ai_writing_provider=provider,
        ai_writing_vllm_base_url="https://provider.example/v1",
        ai_writing_openai_api_key="fake",
    )
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    adapter = create_provider(settings)
    messages = [{"role": "user", "content": "Text-only Task 2."}]
    await adapter.complete(messages, {"type": "object"})
    assert bodies[0]["messages"] == messages
    await adapter.complete(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Visual grounding."},
                    ImagePart(mime_type=mime, data=data),
                ],
            }
        ],
        {"type": "object"},
    )
    parts = bodies[1]["messages"][0]["content"]
    assert len(parts) == 2 and parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"] == f"data:{mime};base64,{base64.b64encode(data).decode()}"
    assert "image_url" not in json.dumps(bodies[0])


def test_invalid_mime_bytes_urls_and_multiple_images_are_rejected():
    for mime, data in [("image/svg+xml", PNG), ("image/png", b"invalid"), ("image/png", b"")]:
        with pytest.raises(ValueError):
            ImagePart(mime_type=mime, data=data)
    with pytest.raises(ValueError):
        serialize_messages(
            [
                {
                    "role": "user",
                    "content": [{"type": "image_url", "image_url": {"url": "http://internal/"}}],
                }
            ]
        )
    with pytest.raises(ValueError):
        serialize_messages(
            [
                {
                    "role": "user",
                    "content": [ImagePart("image/png", PNG), ImagePart("image/png", PNG)],
                }
            ]
        )


class Task1FakeProvider:
    def __init__(
        self,
        *,
        confidence="HIGH",
        malformed_grounding=0,
        fail_trait=None,
        bad_sources=0,
        semantic=False,
        bad_verification=False,
    ):
        self.calls = []
        self.confidence, self.malformed_grounding, self.fail_trait = (
            confidence,
            malformed_grounding,
            fail_trait,
        )
        self.bad_sources, self.semantic, self.bad_verification = (
            bad_sources,
            semantic,
            bad_verification,
        )

    async def ensure_ready(self):
        pass

    async def complete(self, messages, schema):
        self.calls.append(messages)
        properties = schema["properties"]
        if "reference" in properties:
            if self.malformed_grounding:
                self.malformed_grounding -= 1
                return Completion("{}")
            output = {"reference": chart(self.confidence).model_dump(mode="json")}
        elif "claims" in properties:
            bad = self.bad_sources > 0
            self.bad_sources -= int(bad)
            output = {
                "claims": [
                    {
                        "claim_id": "c1",
                        "source_ids": ["P99S1" if bad else "P1S1"],
                        "kind": "change",
                        "claim": "A tăng thêm 30.",
                        "check": None
                        if self.semantic
                        else {
                            "type": "numeric",
                            "subject": "A",
                            "fact": "absolute_change",
                            "value": 30,
                        },
                    }
                ]
            }
        elif "items" in properties:
            output = (
                {}
                if self.bad_verification
                else {
                    "items": [
                        {
                            "claim_id": "c1",
                            "verdict": "SUPPORTED",
                            "explanation": "Nhận định phù hợp với hình.",
                        }
                    ]
                }
            )
        elif "evidence" in properties:
            output = {"evidence": [{"source_id": "P1S1", "assessment": "Dẫn chứng cụ thể."}]}
        else:
            system = messages[0]["content"]
            output = {
                "score": 6.3 if self.fail_trait and self.fail_trait in system else 7,
                "feedback": "Nhận xét tại P1S1.",
                "strengths": ["Rõ ràng."],
                "improvements": ["Nêu chi tiết."],
            }
        return Completion(json.dumps(output), {"total_tokens": 10})


def request():
    return Task1ScoringRequest(
        attempt_id=uuid4(),
        writing_task_id=uuid4(),
        prompt="Describe fictional data.",
        response=ESSAY,
        task_type=WritingTaskType.LINE_GRAPH,
        image=ImagePart("image/png", PNG),
    )


async def assess(provider):
    service = Task1WritingScoringService(provider)
    events = []

    async def trace(event, payload):
        events.append((event, payload.model_dump(mode="json")))

    result = await service.assess(request(), trace)
    return service, result, events


async def test_task1_pipeline_grounded_ta_text_only_languages_and_exact_quotes():
    provider = Task1FakeProvider()
    service, result, events = await assess(provider)
    assert result is not None and result.overall_band == Decimal(7) and len(provider.calls) == 10
    assert result.task_number == 1 and result.task1_analysis.claims[0].verdict == "SUPPORTED"
    assert result.task1_analysis.claims[0].quote == "A increased from 20 to 50."
    assert all(
        getattr(result.criteria, trait).evidence[0].quote == "A increased from 20 to 50."
        for trait in ("ta", "cc", "lr", "gra")
    )
    assert (
        sum(isinstance(message["content"], list) for call in provider.calls for message in call)
        == 1
    )
    for call in provider.calls[1:]:
        assert all(isinstance(message["content"], str) for message in call)
    score_calls = [
        call for call in provider.calls if "Return only four fields" in call[0]["content"]
    ]
    assert (
        "visual_reference" in score_calls[0][1]["content"]
        and "Task Achievement" in score_calls[0][0]["content"]
    )
    assert all(
        "visual_reference" not in call[1]["content"]
        and "claim_verification" not in call[1]["content"]
        for call in score_calls[1:]
    )
    assert "image content" in provider.calls[0][0]["content"].lower()
    assert not service.failures
    names = [event for event, _ in events]
    assert all(
        stage in names
        for stage in [
            "visual_grounding.started",
            "visual_grounding.completed",
            "derived_facts.completed",
            "claim_extraction.completed",
            "claim_verification.completed",
        ]
    )


@pytest.mark.parametrize("confidence,success", [("LOW", True), ("UNUSABLE", False)])
async def test_confidence_isolation_and_no_invented_overall(confidence, success):
    service, result, events = await assess(Task1FakeProvider(confidence=confidence))
    assert (result is not None) == success
    if result:
        assert "VISUAL_LOW_CONFIDENCE" in result.task1_analysis.warnings
        assert not result.task1_analysis.derived_facts
        assert result.task1_analysis.claims[0].verdict == "INSUFFICIENT_EVIDENCE"
    else:
        assert list(service.failures) == ["ta"]
        assert [
            payload["criterion"] for event, payload in events if event == "criterion.completed"
        ] == ["cc", "lr", "gra"]


@pytest.mark.parametrize("malformed,success", [(1, True), (2, False)])
async def test_one_grounding_repair_then_linguistic_criteria_continue(malformed, success):
    provider = Task1FakeProvider(malformed_grounding=malformed)
    service, result, events = await assess(provider)
    assert (result is not None) == success
    assert len([call for call in provider.calls if isinstance(call[1]["content"], list)]) == 2
    if not success:
        assert [
            payload["criterion"] for event, payload in events if event == "criterion.completed"
        ] == ["cc", "lr", "gra"]
        assert "ta" in service.failures


async def test_trait_failure_does_not_stop_later_traits_and_sources_repair_once():
    provider = Task1FakeProvider(fail_trait="Lexical Resource", bad_sources=1)
    service, result, events = await assess(provider)
    assert result is None and list(service.failures) == ["lr"]
    assert [
        payload["criterion"] for event, payload in events if event == "criterion.completed"
    ] == ["ta", "cc", "gra"]
    assert (
        sum(
            "Extract at most" in call[0]["content"]
            for call in provider.calls
            if isinstance(call[0]["content"], str)
        )
        == 2
    )


@pytest.mark.parametrize("bad_verification", [False, True])
async def test_semantic_verification_is_one_text_call_and_failure_keeps_ta_grounded(
    bad_verification,
):
    provider = Task1FakeProvider(semantic=True, bad_verification=bad_verification)
    _, result, events = await assess(provider)
    assert result is not None
    verification = [call for call in provider.calls if "Verify only these" in call[0]["content"]]
    assert len(verification) == 1 and isinstance(verification[0][1]["content"], str)
    assert ("CLAIM_VERIFICATION_FAILED" in result.task1_analysis.warnings) == bad_verification
    assert ("claim_verification.completed" in [event for event, _ in events]) != bad_verification


def test_task1_fingerprint_changes_with_bytes_type_and_prompt_version():
    original = request()
    baseline = input_fingerprint(original, TASK1_PROMPT_VERSION, "vllm", "model")
    assert input_fingerprint(original, TASK1_PROMPT_VERSION, "vllm", "model") == baseline
    for changed in [
        original.model_copy(update={"image": ImagePart("image/png", PNG + b"different")}),
        original.model_copy(update={"task_type": WritingTaskType.BAR_CHART}),
    ]:
        assert input_fingerprint(changed, TASK1_PROMPT_VERSION, "vllm", "model") != baseline
    assert input_fingerprint(original, "other", "vllm", "model") != baseline
    assert "image" not in original.model_dump(mode="json") and "iVBOR" not in repr(original)


def test_unknown_numeric_fields_never_become_false_contradictions():
    claim = ExtractedClaim(
        claim_id="c",
        source_ids=["P1S1"],
        kind="trend",
        claim="Hai đường giao nhau.",
        check={"type": "numeric", "subject": "A", "fact": "crossover", "value": 99},
    )
    assert verify_claim(claim, chart(), derive_facts(chart()))[0] == "INSUFFICIENT_EVIDENCE"


def test_derived_changes_can_exceed_point_bounds_without_failing_the_pipeline():
    facts = derive_facts(chart(values=(Decimal("0.00000001"), Decimal("1000000000000"))))
    percent = next(
        fact for fact in facts if fact.kind == "percentage_change" and fact.subjects == ["A"]
    )
    assert percent.value > Decimal("1e12")
    analysis = Task1Analysis(visual_family="chart_table", reference=chart(), derived_facts=facts)
    assert Task1Analysis.model_validate_json(analysis.model_dump_json()).derived_facts == facts


async def test_empty_perception_cannot_claim_usable_grounding():
    class EmptyProvider:
        async def complete(self, _messages, _schema):
            return Completion(
                json.dumps(
                    {
                        "reference": {
                            "visual_family": "process",
                            "confidence": "HIGH",
                            "process_kind": "unknown",
                            "stages": [],
                            "edges": [],
                        }
                    }
                )
            )

    output = await Task1VisualGroundingService(EmptyProvider(), []).ground(
        request().model_copy(update={"task_type": WritingTaskType.PROCESS})
    )
    assert output.reference.confidence == "UNUSABLE"


def test_table_tied_changes_respect_bounded_fact_subjects():
    rows = [f"Row {index}" for index in range(30)]
    table = VisualGroundingOutput.model_validate(
        {
            "reference": {
                "visual_family": "chart_table",
                "confidence": "HIGH",
                "components": [
                    {
                        "id": "table",
                        "kind": "table",
                        "ordered_categories": True,
                        "row_headers": rows,
                        "column_headers": ["2000", "2010"],
                        "cells": [
                            {"row": row, "column": category, "value": value, "confidence": 1}
                            for row in rows
                            for category, value in [("2000", 10), ("2010", 20)]
                        ],
                    }
                ],
            }
        }
    ).reference
    facts = derive_facts(table)
    largest = [fact for fact in facts if fact.kind == "largest_increase"]
    assert {fact.subjects[0] for fact in largest} == set(rows)
    assert all(fact.value == Decimal(10) for fact in largest)
    assert Task1Analysis.model_validate_json(
        Task1Analysis(visual_family="chart_table", derived_facts=facts).model_dump_json()
    )


def test_long_chart_title_is_display_metadata_and_normalizes_locally():
    output = chart().model_dump(mode="json")
    output["components"][0]["title"] = "A fictional display title. " * 20
    parsed = VisualGroundingOutput.model_validate({"reference": output}).reference
    assert 0 < len(parsed.components[0].title) <= 120
    assert parsed.components[0].series == chart().components[0].series
