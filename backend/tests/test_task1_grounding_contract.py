"""Original fictional data exercises the real schema, transport, facts and pipeline."""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from test_chart_cross_check import FakeSpecialist
from test_task1_grounding_regression import PieProvider, grade, pie_request

from app.core.config import Settings
from app.domains.scoring.chart_reconciliation import reconcile_chart
from app.domains.scoring.deplot_parser import parse_deplot
from app.domains.scoring.task1_facts import derive_facts
from app.providers.writing_llm.base import Completion, ProviderFailure
from app.providers.writing_llm.vllm import VLLMProvider, guided_json_schema
from app.schemas.chart_cross_check import ChartSpecialistIdentity
from app.schemas.task1_visual import VisualGroundingOutput
from app.services.task1_diagnostics import safe_task1_issues
from app.services.task1_grounding import Task1VisualGroundingService

MATRIX = Path(__file__).parent / "fixtures" / "synthetic_six_region_pie_matrix.json"
SPECIALIST_MATRIX = (
    "Region | Agriculture (%) | Industry (%) | Domestic (%)\n"
    "Region A | 55 | 30 | 15\nRegion B | 45 | 35 | 20\nRegion C | 70 | 20 | 10\n"
    "Region D | 40 | 45 | 15\nRegion E | 60 | 25 | 15\nRegion F | 50 | 20 | 30"
)


@pytest.fixture
def pie_matrix():
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_domain_serialization_guided_schema_characterizes_original_decimal_string_hole():
    domain = VisualGroundingOutput.model_json_schema(mode="serialization")
    guided = guided_json_schema(domain)
    for model in ("Point", "TableCell"):
        original = domain["$defs"][model]["properties"]["value"]
        assert original["anyOf"][0]["type"] == "string"
        assert "pattern" in original["anyOf"][0]
        # Domain serialization describes stored/API Decimal strings. Stripping
        # their pattern cannot constrain model output to parseable numbers.
        assert guided["$defs"][model]["properties"]["value"] == {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "title": "Value",
        }


async def test_task1_grounding_wire_schema_requests_numbers_for_points_and_cells(
    pie_matrix, monkeypatch
):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(pie_matrix)}}
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    provider = VLLMProvider(
        Settings(_env_file=None, ai_writing_vllm_base_url="https://example.test/v1")
    )
    await Task1VisualGroundingService(provider, []).ground(pie_request())
    assert len(bodies) == 1
    guided = bodies[0]["response_format"]["json_schema"]["schema"]
    prompt_schema = json.loads(bodies[0]["messages"][0]["content"].split("Schema: ", 1)[1])
    for model in ("Point", "TableCell"):
        numeric = guided["$defs"][model]["properties"]["value"]
        assert numeric["anyOf"] == [
            {"type": "number", "minimum": -1000000000000, "maximum": 1000000000000},
            {"type": "null"},
        ]
        assert prompt_schema["$defs"][model]["properties"]["value"] == numeric


def test_six_region_matrix_validates_derives_and_aligns_without_axes(pie_matrix):
    primary = VisualGroundingOutput.model_validate(pie_matrix).reference
    component = primary.components[0]
    assert len(primary.components) == 1 and component.unit == "%"
    assert component.categories == [f"Region {letter}" for letter in "ABCDEF"]
    assert [series.name for series in component.series] == ["Agriculture", "Industry", "Domestic"]
    assert all(len(series.points) == 6 for series in component.series)
    assert all(
        point.category in component.categories
        for series in component.series
        for point in series.points
    )
    assert (
        component.x_axis is None and component.y_axis is None and not component.ordered_categories
    )
    values = [fact for fact in derive_facts(primary) if fact.kind == "value"]
    assert len(values) == 18 and all(isinstance(fact.value, Decimal) for fact in values)
    assert next(
        fact.value
        for fact in values
        if fact.subjects == ["Industry"] and fact.category == "Region A"
    ) == Decimal(30)
    assert not any(f.kind in {"start", "end", "absolute_change"} for f in derive_facts(primary))
    reconciled, cross_check = reconcile_chart(
        primary, parse_deplot(SPECIALIST_MATRIX), ChartSpecialistIdentity(enabled=True)
    )
    assert cross_check.agreement_count == 18
    assert not cross_check.disagreement_count and not cross_check.warnings
    assert reconciled == primary


@pytest.mark.parametrize("enabled", [False, True])
async def test_percent_formatted_pie_matrix_needs_one_image_call_and_completes_ta(
    pie_matrix, enabled
):
    for component in pie_matrix["reference"]["components"]:
        for series in component["series"]:
            for point in series["points"]:
                point["value"] = str(point["value"]) + " %"
    provider, specialist = PieProvider(pie_matrix), FakeSpecialist(SPECIALIST_MATRIX)
    scorer, result, events = await grade(provider, specialist, enabled=enabled)
    assert result is not None and not scorer.failures and not scorer.diagnostics
    assert provider.image_calls == 1
    assert set(result.criteria.model_dump()) == {"ta", "cc", "lr", "gra"}
    assert result.task1_analysis.confidence == "HIGH"
    assert len([f for f in result.task1_analysis.derived_facts if f.kind == "value"]) == 18
    assert len(specialist.calls) == int(enabled)
    if enabled:
        assert result.task1_analysis.cross_check.agreement_count == 18
    assert "visual_grounding.completed" in [event for event, _ in events]
    assert "visual_grounding.failed" not in [event for event, _ in events]


async def test_table_numeric_labels_normalize_without_grounding_repair():
    raw = {
        "reference": {
            "visual_family": "chart_table",
            "confidence": "HIGH",
            "components": [
                {
                    "id": "table",
                    "kind": "table",
                    "row_headers": ["Region A"],
                    "column_headers": ["Share", "Count"],
                    "cells": [
                        {"row": "Region A", "column": "Share", "value": "42%", "confidence": 0.95},
                        {
                            "row": "Region A",
                            "column": "Count",
                            "value": "1,500",
                            "confidence": 0.95,
                        },
                    ],
                }
            ],
        }
    }
    provider = PieProvider(raw)
    output = await Task1VisualGroundingService(provider, []).ground(pie_request())
    assert provider.image_calls == 1
    assert [cell.value for cell in output.reference.components[0].cells] == [
        Decimal(42),
        Decimal(1500),
    ]


async def test_json_numeric_decimals_reach_domain_without_float_rounding(pie_matrix):
    raw = json.dumps(pie_matrix).replace('"value": 55', '"value": 1234567890.12345678', 1)
    output = await Task1VisualGroundingService(PieProvider(Completion(raw)), []).ground(
        pie_request()
    )
    assert output.reference.components[0].series[0].points[0].value == Decimal(
        "1234567890.12345678"
    )


@pytest.mark.parametrize(
    "numeric,error_type",
    [
        ("1000000000000.00001", "less_than_equal"),
        ("1.12345678000000001", "decimal_max_places"),
    ],
)
async def test_json_numbers_cannot_round_into_valid_domain_bounds(pie_matrix, numeric, error_type):
    raw = json.dumps(pie_matrix).replace('"value": 55', f'"value": {numeric}', 1)
    diagnostics = []
    with pytest.raises(ProviderFailure):
        await Task1VisualGroundingService(PieProvider(Completion(raw)), [], diagnostics).ground(
            pie_request()
        )
    assert diagnostics[0].validation_issues[0].validation_type == error_type


@pytest.mark.parametrize("numeric", ["1e9999999999999999999", "1e-9999999999999999999"])
async def test_unrepresentable_json_exponent_has_bounded_repair_and_linguistic_scores(
    pie_matrix, numeric, caplog
):
    raw = json.dumps(pie_matrix).replace('"value": 55', f'"value": {numeric}', 1)
    provider = PieProvider(Completion(raw))
    scorer, result, events = await grade(provider)
    assert result is None and provider.image_calls == 2
    assert list(scorer.failures) == ["ta"] and len(scorer.diagnostics) == 2
    assert all(
        diagnostic.validation_issues[0].model_dump()
        == {"field": "<root>", "validation_type": "decimal_parsing"}
        for diagnostic in scorer.diagnostics
    )
    assert [payload.criterion for event, payload in events if event == "criterion.completed"] == [
        "cc",
        "lr",
        "gra",
    ]
    assert "reason=GROUNDING_SCHEMA_INVALID" in caplog.text
    assert numeric not in caplog.text


@pytest.mark.parametrize("repair_valid", [True, False])
async def test_undeclared_multi_pie_category_has_safe_diagnostic_and_one_repair(
    pie_matrix, caplog, repair_valid
):
    broken = deepcopy(pie_matrix)
    secret = "PRIVATE CHART LABEL"
    broken["reference"]["components"][0]["series"][0]["points"][0]["category"] = secret
    provider = PieProvider(broken, pie_matrix if repair_valid else broken)
    scorer, result, events = await grade(provider)
    assert provider.image_calls == 2 and (result is not None) is repair_valid
    assert len(scorer.diagnostics) == (1 if repair_valid else 2)
    assert scorer.diagnostics[0].validation_issues[0].field == "reference.components.0"
    assert scorer.diagnostics[0].validation_issues[0].validation_type == "unknown_chart_category"
    assert "type=unknown_chart_category" in caplog.text
    assert secret not in caplog.text + str([d.model_dump() for d in scorer.diagnostics])
    if not repair_valid:
        assert list(scorer.failures) == ["ta"]
        assert [
            payload.criterion for event, payload in events if event == "criterion.completed"
        ] == ["cc", "lr", "gra"]


async def test_four_invalid_components_repair_to_percent_matrix_without_another_retry(pie_matrix):
    broken = deepcopy(pie_matrix)
    components = []
    for index in range(4):
        component = deepcopy(broken["reference"]["components"][0])
        component["id"] = f"partial-{index}"
        component["categories"] = ["PRIVATE UNDECLARED REGION"]
        components.append(component)
    broken["reference"]["components"] = components
    for series in pie_matrix["reference"]["components"][0]["series"]:
        for point in series["points"]:
            point["value"] = f"{point['value']}%"
    provider = PieProvider(broken, pie_matrix)
    scorer, result, _ = await grade(provider)
    assert result is not None and provider.image_calls == 2
    assert len(scorer.diagnostics) == 1
    assert [issue.model_dump() for issue in scorer.diagnostics[0].validation_issues] == [
        {"field": f"reference.components.{i}", "validation_type": "unknown_chart_category"}
        for i in range(4)
    ]
    assert len([f for f in result.task1_analysis.derived_facts if f.kind == "value"]) == 18


@pytest.mark.parametrize(
    "failure,expected_type",
    [
        ("category", "unknown_chart_category"),
        ("header", "unknown_table_header"),
        ("series_id", "duplicate_visual_identifier"),
        ("series_name", "duplicate_series_name"),
        ("component_id", "duplicate_visual_identifier"),
        ("declared_category", "duplicate_visual_identifier"),
        ("point_category", "duplicate_visual_identifier"),
        ("table_cell", "duplicate_table_cell"),
        ("table_series", "table_series_forbidden"),
        ("chart_cells", "chart_cells_forbidden"),
    ],
)
def test_component_invariants_remain_strict_with_safe_fixed_types(
    pie_matrix, failure, expected_type
):
    component = pie_matrix["reference"]["components"][0]
    if failure == "category":
        component["series"][0]["points"][0]["category"] = "PRIVATE CHART LABEL"
    elif failure == "header":
        component["cells"] = [
            {
                "row": "PRIVATE CHART LABEL",
                "column": "PRIVATE HEADER",
                "value": 42,
                "confidence": 0.95,
            }
        ]
    elif failure == "series_id":
        component["series"][1]["id"] = component["series"][0]["id"]
    elif failure == "series_name":
        component["series"][1]["name"] = component["series"][0]["name"]
    elif failure == "component_id":
        pie_matrix["reference"]["components"].append(deepcopy(component))
    elif failure == "declared_category":
        component["categories"].append(component["categories"][0])
    elif failure == "point_category":
        component["series"][0]["points"].append(deepcopy(component["series"][0]["points"][0]))
    elif failure == "table_cell":
        component["row_headers"], component["column_headers"] = ["R"], ["C"]
        component["cells"] = [{"row": "R", "column": "C", "value": 42, "confidence": 0.95}] * 2
    elif failure == "table_series":
        component["kind"] = "table"
    elif failure == "chart_cells":
        component["row_headers"], component["column_headers"] = ["R"], ["C"]
        component["cells"] = [{"row": "R", "column": "C", "value": 42, "confidence": 0.95}]
    with pytest.raises(ValidationError) as error:
        VisualGroundingOutput.model_validate(pie_matrix)
    issues = safe_task1_issues(error.value, VisualGroundingOutput)
    assert issues[0].validation_type == expected_type
    assert "PRIVATE" not in str([issue.model_dump() for issue in issues])
