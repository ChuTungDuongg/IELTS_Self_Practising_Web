"""Original synthetic chart data; no inference or copyrighted exam material."""

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from test_task1_visual import Task1FakeProvider, chart, reference, request

from app.core.config import Settings
from app.domains.scoring.chart_reconciliation import reconcile_chart
from app.domains.scoring.deplot_parser import DePlotParseError, normalize_label, parse_deplot
from app.domains.scoring.mts_prompts import scoring_messages
from app.domains.scoring.task1_facts import derive_facts
from app.domains.scoring.task1_prompts import score_prompt
from app.domains.scoring.task1_verification import verify_claim
from app.domains.writing.task_types import WritingTaskType
from app.providers.chart_derendering import ChartSpecialistFailure
from app.providers.chart_derendering.deplot import DePlotChartDerenderingProvider
from app.schemas.chart_cross_check import DEPLOT_MODEL, DEPLOT_REVISION, ChartSpecialistIdentity
from app.schemas.task1_claims import ExtractedClaim, Task1Analysis
from app.schemas.task1_visual import ChartTableVisualReference
from app.schemas.writing_ai import EvidenceResult
from app.services.task1_writing import Task1WritingScoringService
from app.services.writing_ai import input_fingerprint

IDENTITY = ChartSpecialistIdentity(enabled=True)
LINE = "Year | A (%) | B (%)<0x0A>2000 | 20 | 30<0x0A>2010 | 50 | 10"
PIE = "Region | Agriculture (%) | Industry (%) | Domestic (%)\nRegion A | 60 | 25 | 15\nRegion B | 30 | 50 | 20"


def multi_pie():
    return ChartTableVisualReference.model_validate(
        {
            "visual_family": "chart_table",
            "confidence": "HIGH",
            "components": [
                {
                    "id": f"region-{i}",
                    "kind": "pie_chart",
                    "state": region,
                    "unit": "%",
                    "categories": ["Agriculture", "Industry", "Domestic"],
                    "series": [
                        {
                            "id": "share",
                            "name": "Share",
                            "points": [
                                {
                                    "category": label,
                                    "value": value,
                                    "confidence": 0.85,
                                    "value_is_labelled": True,
                                }
                                for label, value in zip(
                                    ["Agriculture", "Industry", "Domestic"], values, strict=True
                                )
                            ],
                        }
                    ],
                }
                for i, (region, values) in enumerate(
                    [("Region A", [60, 25, 15]), ("Region B", [30, 50, 20])]
                )
            ],
        }
    )


@pytest.mark.parametrize(
    "text,value,unit,status",
    [
        ("48", "48", None, "VALUE"),
        ("48.0", "48", None, "VALUE"),
        ("48%", "48", "percent", "VALUE"),
        (".125", ".125", None, "VALUE"),
        ("-12.5", "-12.5", None, "VALUE"),
        ("", None, None, "MISSING"),
        ("—", None, None, "MISSING"),
        ("N/A", None, None, "MISSING"),
        ("NaN", None, None, "UNPARSEABLE"),
        ("Infinity", None, None, "UNPARSEABLE"),
        ("1e50", None, None, "UNPARSEABLE"),
        ("1,000", None, None, "UNPARSEABLE"),
        ("10000000000001", None, None, "UNPARSEABLE"),
        ("0.123456789", None, None, "UNPARSEABLE"),
        ("__import__('os')", None, None, "UNPARSEABLE"),
    ],
)
def test_decimal_percentage_and_explicit_missing_cells(text, value, unit, status):
    observation = parse_deplot(f"Item | First | Second\nA | {text} | 1")
    cell = observation.cells[0]
    assert cell.value == (Decimal(value) if value is not None else None)
    assert (cell.unit, cell.status) == (unit, status)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello",
        "A | B",
        "A | B\nC | 1 | 2",
        "A | B\nC | nan",
        "A | B | b\nC | 1 | 2",
        "A | B\nC | 1\nc | 2",
        "A | " + "x" * 121 + "\nC | 1",
        "A | B\n" + "\n".join(f"R{i} | 1" for i in range(31)),
        "A | "
        + " | ".join(f"C{i}" for i in range(31))
        + "\nR | "
        + " | ".join("1" for _ in range(31)),
        "x" * 16385,
    ],
)
def test_malformed_duplicate_and_bounded_tables(text):
    with pytest.raises(DePlotParseError):
        parse_deplot(text)


def test_unicode_and_title_header():
    observation = parse_deplot(
        "TITLE | Synthetic chart\r\nItem | Cafe\u0301 (%)\r\n Thành   phố | 48.0"
    )
    assert observation.title == "Synthetic chart"
    assert observation.columns == ["Café"]
    assert normalize_label(observation.cells[0].row) == "thành phố"
    assert observation.cells[0].unit == "percent"


@pytest.mark.parametrize("value", ["48", "48.0", "48%"])
def test_exact_decimal_agreement(value):
    primary = chart(values=(48, 50))
    reconciled, diagnostic = reconcile_chart(
        primary,
        parse_deplot(f"Year | A (%) | B (%)\n2000 | {value} | 30\n2010 | 50 | 10"),
        IDENTITY,
    )
    assert diagnostic.agreement_count == 4 and diagnostic.disagreement_count == 0
    assert reconciled.components[0].series[0].points[0].value == 48
    assert primary.components[0].series[0].points[0].value == 48


def test_conflict_removes_exact_value_and_cannot_contradict_student():
    primary = chart(values=(48, 50))
    primary.summary = "A starts at 48."
    reconciled, diagnostic = reconcile_chart(primary, parse_deplot(LINE), IDENTITY)
    assert diagnostic.disagreement_count == 1
    assert reconciled.confidence == "MEDIUM"
    assert reconciled.components[0].series[0].points[0].value is None
    assert "48" not in reconciled.summary
    facts = derive_facts(reconciled)
    assert not any(f.subjects == ["A"] and f.category == "2000" for f in facts)
    claim = ExtractedClaim(
        claim_id="c",
        source_ids=["P1S1"],
        kind="numeric_value",
        claim="A là 20.",
        check={"type": "numeric", "subject": "A", "fact": "value", "category": "2000", "value": 20},
    )
    assert verify_claim(claim, reconciled, facts)[0] == "INSUFFICIENT_EVIDENCE"
    assert primary.components[0].series[0].points[0].value == 48


def test_primary_only_specialist_only_and_unsafe_labels():
    reconciled, diagnostic = reconcile_chart(
        chart(), parse_deplot("Year | Unknown\n2000 | 1\n2010 | 2"), IDENTITY
    )
    assert diagnostic.agreement_count == 0
    assert diagnostic.unmatched_primary_count == 4
    assert diagnostic.unmatched_specialist_count == 2
    assert "CHART_ALIGNMENT_UNCERTAIN" in diagnostic.warnings
    assert reconciled == chart()
    missing = chart(values=(None, 50))
    reconciled, diagnostic = reconcile_chart(missing, parse_deplot(LINE), IDENTITY)
    assert diagnostic.unmatched_specialist_count == 1
    assert reconciled.components[0].series[0].points[0].value is None


def test_multi_pie_percentages_independent_of_time_axis():
    reconciled, diagnostic = reconcile_chart(multi_pie(), parse_deplot(PIE), IDENTITY)
    assert diagnostic.agreement_count == 6
    assert not diagnostic.warnings
    assert len(reconciled.components) == 2
    assert all(not component.ordered_categories for component in reconciled.components)
    assert not any(f.kind in {"start", "end", "absolute_change"} for f in derive_facts(reconciled))
    fixture = Path(__file__).parent / "fixtures" / "synthetic_multi_pie.svg"
    assert fixture.exists() and "Region A" in fixture.read_text()


def test_table_cells_and_conservative_visual_estimates():
    primary = ChartTableVisualReference.model_validate(
        {
            "visual_family": "chart_table",
            "confidence": "HIGH",
            "components": [
                {
                    "id": "table",
                    "kind": "table",
                    "row_headers": ["A"],
                    "column_headers": ["2000"],
                    "cells": [{"row": "A", "column": "2000", "value": 20, "confidence": 0.7}],
                }
            ],
        }
    )
    reconciled, diagnostic = reconcile_chart(primary, parse_deplot("Item | 2000\nA | 20"), IDENTITY)
    assert diagnostic.agreement_count == 1 and reconciled.components[0].cells[0].confidence == 0.9
    primary = chart()
    primary.components[0].series[0].points[0].value_is_labelled = False
    reconciled, _ = reconcile_chart(primary, parse_deplot(LINE), IDENTITY)
    assert reconciled.components[0].series[0].points[0].confidence < 0.8
    assert not any(
        f.kind == "value" and f.subjects == ["A"] and f.category == "2000"
        for f in derive_facts(reconciled)
    )


def test_mixed_units_and_ambiguous_components_are_unknown():
    primary = chart()
    another = primary.components[0].model_copy(deep=True)
    another.id, another.unit = "second", "tonnes"
    primary.components.append(another)
    reconciled, diagnostic = reconcile_chart(primary, parse_deplot(LINE), IDENTITY)
    assert diagnostic.unknown_count == 8 and not diagnostic.agreement_count
    assert reconciled == primary
    primary.components[1].series[0].name = "C"
    primary.components[1].series[1].name = "D"
    observation = parse_deplot(
        "Year | A | B | C | D\n2000 | 20 | 30 | 20 | 30\n2010 | 50 | 10 | 50 | 10"
    )
    reconciled, diagnostic = reconcile_chart(primary, observation, IDENTITY)
    assert diagnostic.unknown_count == 8 and len(reconciled.components) == 2


class FakeSpecialist:
    def __init__(self, text=LINE, error=None):
        self.text, self.error, self.calls = text, error, []

    async def extract(self, image):
        self.calls.append(image)
        if self.error:
            raise ChartSpecialistFailure(self.error)
        return parse_deplot(self.text)


async def grade(specialist, primary=None, task=None):
    req = task or request()
    req.chart_specialist = IDENTITY
    events = []

    async def trace(event, payload):
        events.append((event, payload))

    scorer = Task1WritingScoringService(primary or Task1FakeProvider(), specialist)
    result = await scorer.assess(req, trace)
    return scorer, result, events


@pytest.mark.parametrize(
    "text,error,status",
    [
        (LINE, None, "COMPLETED"),
        (LINE, "CHART_SPECIALIST_UNAVAILABLE", "UNAVAILABLE"),
        ("bad", None, "PARSE_FAILED"),
        (LINE.replace("20 |", "99 |"), None, "COMPLETED"),
    ],
)
async def test_optional_service_success_failure_malformed_disagreement(text, error, status):
    specialist = FakeSpecialist(text, error)
    scorer, result, events = await grade(specialist)
    assert result is not None and len(specialist.calls) == 1
    assert result.task1_analysis.cross_check.status == status
    assert len(result.criteria.model_dump()) == 4
    assert [event for event, _ in events].index("chart_specialist.started") < [
        event for event, _ in events
    ].index("derived_facts.completed")
    assert (
        len(
            [
                calls
                for calls in scorer.provider.provider.calls
                if isinstance(calls[1]["content"], list)
            ]
        )
        == 1
    )
    if status != "COMPLETED":
        assert result.task1_analysis.reference == chart()
    if "99" in text:
        assert result.task1_analysis.cross_check.disagreement_count == 1
        assert result.task1_analysis.claims[0].verdict == "INSUFFICIENT_EVIDENCE"


async def test_primary_failure_never_uses_specialist_as_replacement():
    specialist = FakeSpecialist()
    scorer, result, _ = await grade(specialist, Task1FakeProvider(malformed_grounding=2))
    assert result is None and "ta" in scorer.failures
    # Extraction now overlaps primary perception, but it cannot replace a failed reference.
    assert len(specialist.calls) == 1
    assert scorer.states["ta"].result is None
    assert all(scorer.states[trait].result for trait in ("cc", "lr", "gra"))
    assert (
        len(
            [
                messages
                for messages in scorer.provider.provider.calls
                if "Score 0 through 9" in messages[0]["content"]
            ]
        )
        == 3
    )


@pytest.mark.parametrize(
    "kind,family",
    [
        (WritingTaskType.PROCESS, "process"),
        (WritingTaskType.MAP_PLAN, "map"),
        (WritingTaskType.OBJECT_SYSTEM_DIAGRAM, "system"),
        (WritingTaskType.OTHER_VISUAL, "other"),
    ],
)
async def test_non_chart_never_calls_specialist(kind, family):
    class NonChartPrimary(Task1FakeProvider):
        async def complete(self, messages, schema, *, options=None):
            if "reference" in schema["properties"]:
                from app.providers.writing_llm.base import Completion

                return Completion(
                    json.dumps({"reference": reference(family).model_dump(mode="json")})
                )
            return await super().complete(messages, schema, options=options)

    req = request()
    req.task_type = kind
    specialist = FakeSpecialist()
    _, result, events = await grade(specialist, NonChartPrimary(), req)
    assert result is not None and not specialist.calls
    assert result.task1_analysis.cross_check is None
    assert not any(event.startswith("chart_") for event, _ in events)


def test_fingerprint_includes_chart_config_but_not_non_chart_config():
    req = request()
    base = input_fingerprint(req, "v2", "vllm", "primary")
    for identity in [
        IDENTITY,
        IDENTITY.model_copy(update={"model": "new"}),
        IDENTITY.model_copy(update={"revision": "new"}),
        IDENTITY.model_copy(update={"contract_version": "new"}),
    ]:
        req.chart_specialist = identity
        assert input_fingerprint(req, "v2", "vllm", "primary") != base
    req.task_type = WritingTaskType.PROCESS
    base = input_fingerprint(req, "v2", "vllm", "primary")
    req.chart_specialist = ChartSpecialistIdentity()
    assert input_fingerprint(req, "v2", "vllm", "primary") == base


def test_descriptor_fit_contract_and_separate_task_achievement():
    evidence = EvidenceResult(evidence=[])
    for trait in ["ta", "cc", "lr", "gra"]:
        system = scoring_messages("Synthetic question", "Synthetic essay", trait, evidence)[0][
            "content"
        ]
        for wording in [
            "official IELTS",
            "Evaluate the entire response for this criterion",
            "Choose the band whose descriptor best matches",
            "Do not favor the higher or lower band by default",
            "Half-bands are interpolation",
            "No score offsets, hard caps, error-count rules or cross-criterion penalties",
            "Vietnamese",
            "only four fields",
        ]:
            assert wording in system
    system = score_prompt(request(), "ta", evidence, Task1Analysis(visual_family="chart_table"))[0][
        "content"
    ]
    assert "Task Achievement" in system and "Task Response" not in system
    assert "not additional scoring criteria" in system
    assert "Do not convert counts of supported or contradicted claims" in system


@pytest.mark.parametrize(
    "response,error",
    [
        (200, None),
        (503, "CHART_SPECIALIST_UNAVAILABLE"),
        (303, "CHART_SPECIALIST_UNAVAILABLE"),
        ("malformed", "CHART_SPECIALIST_PARSE_FAILED"),
        ("wrong_revision", "CHART_SPECIALIST_UNAVAILABLE"),
    ],
)
async def test_transport_only_trusted_bytes_one_request_and_safe_identity(
    monkeypatch, response, error
):
    calls = []
    actual_client = httpx.AsyncClient

    def handle(req):
        calls.append(req)
        assert req.content == request().image.data
        if response == "malformed":
            return httpx.Response(
                200, json={"model": DEPLOT_MODEL, "revision": DEPLOT_REVISION, "table": "bad"}
            )
        if response == "wrong_revision":
            return httpx.Response(
                200, json={"model": DEPLOT_MODEL, "revision": "wrong", "table": LINE}
            )
        return httpx.Response(
            response, json={"model": DEPLOT_MODEL, "revision": DEPLOT_REVISION, "table": LINE}
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: actual_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    provider = DePlotChartDerenderingProvider(
        Settings(
            ai_writing_deplot_base_url="https://specialist.example",
            ai_writing_modal_key="fictional",
            ai_writing_modal_secret="fictional",
        )
    )
    if error:
        with pytest.raises(ChartSpecialistFailure) as failure:
            await provider.extract(request().image)
        assert failure.value.code == error
    else:
        assert len((await provider.extract(request().image)).cells) == 4
    assert len(calls) == 1
    assert calls[0].url.path == "/extract"
    assert "essay" not in calls[0].content.decode("latin1")


@pytest.mark.parametrize(
    "kind",
    [
        WritingTaskType.LINE_GRAPH,
        WritingTaskType.BAR_CHART,
        WritingTaskType.PIE_CHART,
        WritingTaskType.TABLE,
        WritingTaskType.MIXED_CHARTS,
    ],
)
async def test_all_chart_task_types_take_exactly_one_specialist_pass(kind):
    req = request()
    req.task_type = kind
    specialist = FakeSpecialist()
    _, result, _ = await grade(specialist, task=req)
    assert result is not None and len(specialist.calls) == 1


@pytest.mark.parametrize("mode", ["timeout", "exception"])
async def test_timeout_or_unexpected_transport_failure_falls_back(mode):
    class Unavailable:
        async def extract(self, image):
            if mode == "exception":
                raise RuntimeError("fictional unsafe provider body")
            await asyncio.sleep(10)

    req = request()
    req.chart_specialist = IDENTITY
    events = []

    async def trace(event, payload):
        events.append((event, payload))

    result = await Task1WritingScoringService(Task1FakeProvider(), Unavailable(), 0.01).assess(
        req, trace
    )
    assert result is not None
    assert result.task1_analysis.reference == chart()
    assert result.task1_analysis.cross_check.status == "UNAVAILABLE"
    assert "unsafe" not in result.model_dump_json()


async def test_disabled_specialist_makes_no_call():
    specialist = FakeSpecialist()

    async def trace(event, payload):
        pass

    result = await Task1WritingScoringService(Task1FakeProvider(), specialist).assess(
        request(), trace
    )
    assert result is not None and not specialist.calls
    assert result.task1_analysis.cross_check is None


def test_low_root_confidence_is_never_promoted_and_units_must_establish_percentages():
    result, diagnostic = reconcile_chart(chart(confidence="LOW"), parse_deplot(LINE), IDENTITY)
    assert diagnostic.agreement_count == 4 and result.confidence == "LOW"
    assert derive_facts(result) == []
    primary = chart()
    primary.components[0].unit = None
    result, diagnostic = reconcile_chart(primary, parse_deplot(LINE), IDENTITY)
    assert diagnostic.unknown_count == 4 and result == primary


async def test_disputed_unstructured_claim_cannot_become_semantic_contradiction():
    provider = Task1FakeProvider(semantic=True)
    _, result, _ = await grade(FakeSpecialist(LINE.replace("20 |", "99 |")), provider)
    assert result.task1_analysis.claims[0].verdict == "INSUFFICIENT_EVIDENCE"
    assert not any(
        "Verify only these semantic claims" in messages[0]["content"] for messages in provider.calls
    )


async def test_provider_response_size_and_timeout_are_bounded(monkeypatch):
    original = httpx.AsyncClient
    calls = []

    def handle(req):
        calls.append(req)
        return httpx.Response(200, content=b"x" * 32769)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    provider = DePlotChartDerenderingProvider(
        Settings(ai_writing_deplot_base_url="https://chart.example")
    )
    with pytest.raises(ChartSpecialistFailure) as failure:
        await provider.extract(request().image)
    assert failure.value.code == "CHART_SPECIALIST_PARSE_FAILED" and len(calls) == 1


def test_actual_single_smoke_malformed_multi_pie_output_is_rejected():
    # Recorded output of our original synthetic fixture, not user/exam content.
    table = "TITLE | Region A <0x0A> Region A | 0.4% <0x0A> Agriculture: 60%<0x0A>Industry: 25%<0x0A>Domestic: 15% | 15% <0x0A> Agriculture: 30%<0x0A>Industry: 50%<0x0A>Domestic: 20% | 0.3%"
    with pytest.raises(DePlotParseError):
        parse_deplot(table)


def test_enabled_model_revision_and_reconciliation_version_each_change_chart_cache():
    req = request()
    fingerprints = set()
    for identity in [
        ChartSpecialistIdentity(),
        IDENTITY,
        IDENTITY.model_copy(update={"model": "new"}),
        IDENTITY.model_copy(update={"revision": "new"}),
        IDENTITY.model_copy(update={"contract_version": "new"}),
    ]:
        req.chart_specialist = identity
        fingerprints.add(input_fingerprint(req, "v2", "vllm", "primary"))
    assert len(fingerprints) == 5
