"""Synthetic six-region pies and isolated perception failures; no inference."""

import asyncio
import json
import logging
from copy import deepcopy
from decimal import Decimal

import pytest
from test_chart_cross_check import FakeSpecialist
from test_task1_visual import Task1FakeProvider, reference, request

from app.domains.scoring.task1_facts import derive_facts
from app.domains.writing.task_types import WritingTaskType
from app.providers.writing_llm.base import Completion, ProviderFailure
from app.schemas.task1_visual import GroundingConfidence, VisualGroundingOutput
from app.services.task1_grounding import Task1VisualGroundingService
from app.services.task1_input import TASK1_PROMPT_VERSION
from app.services.task1_writing import Task1WritingScoringService


@pytest.fixture
def six_region_pies():
    # Same semantic shape allowed by T1-A; optional T1-B metadata is omitted.
    categories = ["Agriculture", "Industry", "Domestic"]
    percentages = [
        (55, 30, 15),
        (45, 35, 20),
        (70, 20, 10),
        (40, 45, 15),
        (60, 25, 15),
        (50, 20, 30),
    ]
    return {
        "reference": {
            "visual_family": "chart_table",
            "confidence": "HIGH",
            "summary": "Sáu biểu đồ thể hiện ba nhóm sử dụng nước ở các vùng giả định.",
            "components": [
                {
                    "id": "regions",
                    "kind": "pie_chart",
                    "unit": "percent",
                    "categories": categories,
                    "series": [
                        {
                            "id": f"region-{letter}",
                            "name": f"Region {letter}",
                            "points": [
                                {"category": category, "value": value, "confidence": 0.95}
                                for category, value in zip(categories, values, strict=True)
                            ],
                        }
                        for letter, values in zip("ABCDEF", percentages, strict=True)
                    ],
                }
            ],
        },
    }


class PieProvider(Task1FakeProvider):
    def __init__(self, *outputs):
        super().__init__()
        self.outputs, self.image_calls = list(outputs), 0

    async def complete(self, messages, schema):
        if "reference" in schema["properties"]:
            self.calls.append(messages)
            output = self.outputs[min(self.image_calls, len(self.outputs) - 1)]
            self.image_calls += 1
            if isinstance(output, Completion):
                return output
            return Completion(json.dumps(output), {"total_tokens": 10})
        return await super().complete(messages, schema)


def pie_request(enabled=False):
    req = request()
    req.task_type = WritingTaskType.PIE_CHART
    req.chart_specialist.enabled = enabled
    return req


async def grade(provider, specialist=None, *, enabled=False):
    events = []

    async def trace(event, payload):
        # Capture stage snapshots, not a subsequently mutated analysis object.
        events.append((event, payload.model_copy(deep=True)))

    scorer = Task1WritingScoringService(provider, specialist)
    result = await scorer.assess(pie_request(enabled), trace)
    return scorer, result, events


def test_old_t1a_six_region_shape_still_validates(six_region_pies):
    output = VisualGroundingOutput.model_validate_json(json.dumps(six_region_pies))
    component = output.reference.components[0]
    assert len(component.series) == 6
    assert all(len(series.points) == 3 for series in component.series)
    assert all(sum(p.value for p in series.points) == 100 for series in component.series)
    assert all(p.value_is_labelled is None for series in component.series for p in series.points)
    assert component.x_axis is None and component.y_axis is None
    assert not component.ordered_categories
    assert len([fact for fact in derive_facts(output.reference) if fact.kind == "value"]) == 18
    assert TASK1_PROMPT_VERSION == "mts-task1-visual-v3"


@pytest.mark.parametrize(
    "metadata,expected",
    [
        (True, True),
        (False, False),
        (None, None),
        ("true", True),
        ("false", False),
        (1, True),
        (0, False),
        ("unknown", None),
        (2, None),
        ({"label": "unknown"}, None),
        ([], None),
    ],
)
async def test_optional_label_metadata_never_retries_image(six_region_pies, metadata, expected):
    data = deepcopy(six_region_pies)
    raw_point = data["reference"]["components"][0]["series"][0]["points"][0]
    raw_point["value_is_labelled"] = metadata
    provider = PieProvider(data)
    usage, diagnostics = [], []
    output = await Task1VisualGroundingService(provider, usage, diagnostics).ground(pie_request())
    point = output.reference.components[0].series[0].points[0]
    assert point.value_is_labelled is expected
    assert (point.category, point.value, point.confidence) == ("Agriculture", Decimal(55), 0.95)
    assert provider.image_calls == 1 and len(usage) == 1 and not diagnostics
    assert raw_point["value_is_labelled"] == metadata


async def test_primary_only_pies_complete_all_criteria(six_region_pies, caplog):
    provider, specialist = PieProvider(six_region_pies), FakeSpecialist()
    with caplog.at_level(logging.INFO, logger="app.services.task1_writing"):
        scorer, result, events = await grade(provider, specialist)
    assert result is not None and not scorer.failures
    assert set(result.criteria.model_dump()) == {"ta", "cc", "lr", "gra"}
    assert result.task1_analysis.confidence == "HIGH" and result.task1_analysis.cross_check is None
    assert result.task1_analysis.derived_facts
    assert provider.image_calls == 1 and not specialist.calls
    assert not any(event.startswith("chart_") for event, _ in events)
    assert "chart_specialist_enabled=false" in caplog.text


@pytest.mark.parametrize(
    "mode,code",
    [
        ("unavailable", "CHART_SPECIALIST_UNAVAILABLE"),
        ("parse", "CHART_SPECIALIST_PARSE_FAILED"),
        ("reconcile", "CHART_RECONCILIATION_FAILED"),
        ("provider_failure", "CHART_RECONCILIATION_FAILED"),
    ],
)
async def test_specialist_fallback_retains_primary_and_derives_facts(
    six_region_pies, monkeypatch, caplog, mode, code
):
    provider = PieProvider(six_region_pies)
    specialist = FakeSpecialist(
        "bad" if mode == "parse" else "Category | Region A\nAgriculture | 55",
        "CHART_SPECIALIST_UNAVAILABLE" if mode == "unavailable" else None,
    )
    if mode in {"reconcile", "provider_failure"}:

        def broken_reconcile(primary, *_):
            primary.confidence = "UNUSABLE"
            primary.components[0].series[0].points[0].value = None
            if mode == "provider_failure":
                raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE")
            raise RuntimeError("SECRET RAW SPECIALIST OUTPUT")

        monkeypatch.setattr(
            "app.services.task1_chart_cross_check.reconcile_chart", broken_reconcile
        )
    original_derive, derived_inputs = derive_facts, []

    def record_derive(primary):
        derived_inputs.append(primary.model_copy(deep=True))
        return original_derive(primary)

    monkeypatch.setattr("app.services.task1_writing.derive_facts", record_derive)
    scorer, result, events = await grade(provider, specialist, enabled=True)
    assert result is not None and not scorer.failures
    analysis = result.task1_analysis
    primary = VisualGroundingOutput.model_validate(six_region_pies).reference
    assert analysis.reference == primary and analysis.confidence == "HIGH"
    assert derived_inputs == [primary] and analysis.derived_facts == original_derive(primary)
    assert analysis.cross_check.specialist_used is False and code in analysis.warnings
    assert "VISUAL_GROUNDING_FAILED" not in analysis.warnings
    assert provider.image_calls == 1 and len(specialist.calls) == 1
    names = [event for event, _ in events]
    assert names.index("visual_grounding.completed") < names.index("chart_specialist.started")
    assert names.index("chart_specialist.failed") < names.index("derived_facts.completed")
    assert "visual_grounding.failed" not in names
    assert code in caplog.text and "SECRET RAW SPECIALIST OUTPUT" not in caplog.text


async def test_successful_specialist_facts_use_reconciled_reference(six_region_pies, monkeypatch):
    def reconcile(primary, *_):
        from app.schemas.chart_cross_check import ChartCrossCheckResult

        primary.confidence = GroundingConfidence.MEDIUM
        primary.components[0].series[0].points[0].value = None
        return primary, ChartCrossCheckResult(
            specialist_used=True,
            specialist_model="synthetic",
            specialist_revision="test",
            status="COMPLETED",
        )

    monkeypatch.setattr("app.services.task1_chart_cross_check.reconcile_chart", reconcile)
    _, result, _ = await grade(PieProvider(six_region_pies), FakeSpecialist(), enabled=True)
    assert result.task1_analysis.confidence == "MEDIUM"
    assert result.task1_analysis.derived_facts == derive_facts(result.task1_analysis.reference)
    assert not any(
        fact.kind == "value" and fact.subjects == ["Region A"] and fact.category == "Agriculture"
        for fact in result.task1_analysis.derived_facts
    )
    assert six_region_pies["reference"]["components"][0]["series"][0]["points"][0]["value"] == 55


@pytest.mark.parametrize("repair_valid", [False, True])
async def test_core_failure_repairs_once_then_preserves_linguistic_criteria(
    six_region_pies, repair_valid
):
    broken = deepcopy(six_region_pies)
    broken["reference"]["components"][0]["series"][0]["points"][0]["value"] = (
        "invalid numeric value"
    )
    provider = PieProvider(broken, six_region_pies if repair_valid else broken)
    specialist = FakeSpecialist()
    scorer, result, events = await grade(provider, specialist, enabled=False)
    assert provider.image_calls == 2 and not specialist.calls
    assert (result is not None) is repair_valid
    assert len(scorer.diagnostics) == (1 if repair_valid else 2)
    issue = scorer.diagnostics[0].validation_issues[0]
    assert issue.field == "reference.components.0.series.0.points.0.value"
    assert issue.validation_type == "decimal_parsing"
    if not repair_valid:
        failed = next(payload for event, payload in events if event == "visual_grounding.failed")
        assert failed.task1_analysis.confidence == "UNUSABLE"
        assert list(scorer.failures) == ["ta"]
        assert [
            payload.criterion for event, payload in events if event == "criterion.completed"
        ] == ["cc", "lr", "gra"]


@pytest.mark.parametrize("failure", ["value", "category", "components", "extra", "family"])
async def test_safe_schema_diagnostics_do_not_log_rejected_data(six_region_pies, failure, caplog):
    data = deepcopy(six_region_pies)
    secret = "PRIVATE_PROMPT_ESSAY_IMAGE_APIKEY_PROVIDER_BODY"
    point = data["reference"]["components"][0]["series"][0]["points"][0]
    data["reference"]["summary"] = secret
    expected_type = {
        "value": "decimal_parsing",
        "category": "string_type",
        "components": "too_long",
        "extra": "extra_forbidden",
        "family": "union_tag_invalid",
    }[failure]
    if failure == "value":
        point["value"] = secret
    elif failure == "category":
        point["category"] = {secret: secret}
    elif failure == "components":
        data["reference"]["components"] *= 6
    elif failure == "extra":
        point[secret] = secret
    else:
        data["reference"]["visual_family"] = secret
    usage, diagnostics = [], []
    req = pie_request()
    req.prompt = req.response = secret
    with pytest.raises(ProviderFailure):
        await Task1VisualGroundingService(PieProvider(data), usage, diagnostics).ground(req)
    safe_records = [
        record for record in caplog.records if record.name == "app.services.task1_grounding"
    ]
    assert len(diagnostics) == 2 and len(safe_records) == 2
    for attempt, (diagnostic, record) in enumerate(zip(diagnostics, safe_records, strict=True), 1):
        issue = diagnostic.validation_issues[0]
        assert issue.validation_type == expected_type
        message = record.getMessage()
        assert f"stage=visual_grounding attempt={attempt}" in message
        assert f"field={issue.field} type={expected_type}" in message
        assert "GROUNDING_SCHEMA_INVALID" in message
        assert record.exc_info is None
    assert secret not in caplog.text + str([d.model_dump() for d in diagnostics])
    assert "base64" not in caplog.text and "iVBOR" not in caplog.text


@pytest.mark.parametrize("kind", ["json", "wrong_family", "length"])
async def test_safe_distinct_grounding_failure_classifications(kind, caplog):
    output = {
        "json": Completion('{"PRIVATE_RAW_COMPLETION":'),
        "wrong_family": Completion(
            json.dumps({"reference": reference("process").model_dump(mode="json")})
        ),
        "length": Completion("PRIVATE_RAW_COMPLETION", finish_reason="length"),
    }[kind]
    diagnostics = []
    with pytest.raises(ProviderFailure):
        await Task1VisualGroundingService(PieProvider(output), [], diagnostics).ground(
            pie_request()
        )
    code = {
        "json": "GROUNDING_JSON_INVALID",
        "wrong_family": "GROUNDING_WRONG_FAMILY",
        "length": "GROUNDING_FINISH_LENGTH",
    }[kind]
    assert len(diagnostics) == 2 and code in caplog.text
    assert "PRIVATE_RAW_COMPLETION" not in caplog.text
    if kind == "wrong_family":
        assert diagnostics[0].validation_issues[0].field == "reference.visual_family"


async def test_fact_error_is_separate_and_cannot_reclassify_primary(
    six_region_pies, monkeypatch, caplog
):
    def broken_derive(primary):
        primary.confidence = "UNUSABLE"
        raise RuntimeError("SECRET CHART LABELS")

    monkeypatch.setattr("app.services.task1_writing.derive_facts", broken_derive)
    scorer, result, events = await grade(PieProvider(six_region_pies))
    assert result is not None and not scorer.failures
    analysis = result.task1_analysis
    assert analysis.confidence == "HIGH" and not analysis.derived_facts
    assert analysis.reference == VisualGroundingOutput.model_validate(six_region_pies).reference
    assert "DERIVED_FACTS_FAILED" in analysis.warnings
    assert analysis.claims[0].verdict == "INSUFFICIENT_EVIDENCE"
    names = [event for event, _ in events]
    assert "derived_facts.failed" in names and "visual_grounding.failed" not in names
    assert "stage=derived_facts reason=DERIVED_FACTS_FAILED" in caplog.text
    assert "SECRET CHART LABELS" not in caplog.text


async def test_reconciliation_cancellation_propagates(six_region_pies, monkeypatch):
    def cancelled(*_):
        raise asyncio.CancelledError()

    monkeypatch.setattr("app.services.task1_chart_cross_check.reconcile_chart", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await grade(PieProvider(six_region_pies), FakeSpecialist(), enabled=True)


async def test_trace_errors_are_not_swallowed_as_grounding_failures(six_region_pies):
    events = []

    async def trace(event, payload):
        events.append(event)
        if event == "chart_specialist.completed":
            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE")

    with pytest.raises(ProviderFailure):
        await Task1WritingScoringService(PieProvider(six_region_pies), FakeSpecialist()).assess(
            pie_request(True), trace
        )
    assert "visual_grounding.completed" in events
    assert "visual_grounding.failed" not in events and "chart_specialist.failed" not in events
