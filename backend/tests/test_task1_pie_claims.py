"""Fictional two-pie fixtures test grounding, never band calibration."""

import pytest

from app.domains.scoring.task1_facts import derive_facts
from app.domains.scoring.task1_verification import verify_claim
from app.schemas.task1_claims import ExtractedClaim
from app.schemas.task1_visual import ChartTableVisualReference

LABELS = [
    "No other language",
    "French only",
    "German only",
    "Spanish only",
    "Another language",
    "Two other languages",
]
VALUES = {"2000": [20, 15, 10, 30, 15, 10], "2010": [10, 10, 10, 35, 20, 15]}


def pies():
    return ChartTableVisualReference.model_validate(
        {
            "visual_family": "chart_table",
            "confidence": "MEDIUM",
            "summary": "Fictional language survey.",
            "components": [
                {
                    "id": f"pie-{year}",
                    "kind": "pie_chart",
                    "title": f"Language survey {year}",
                    "state": year,
                    "unit": "%",
                    "categories": LABELS,
                    "series": [
                        {
                            "id": "share",
                            "name": "Share",
                            "points": [
                                {"category": label, "value": value, "confidence": 0.95}
                                for label, value in zip(LABELS, values, strict=True)
                            ],
                        }
                    ],
                }
                for year, values in VALUES.items()
            ],
        }
    )


def matrix():
    return ChartTableVisualReference.model_validate(
        {
            "visual_family": "chart_table",
            "confidence": "MEDIUM",
            "components": [
                {
                    "id": "pie-matrix",
                    "kind": "pie_chart",
                    "unit": "%",
                    "categories": list(VALUES),
                    "ordered_categories": True,
                    "series": [
                        {
                            "id": f"slice-{index}",
                            "name": label,
                            "points": [
                                {"category": year, "value": values[index], "confidence": 0.95}
                                for year, values in VALUES.items()
                            ],
                        }
                        for index, label in enumerate(LABELS)
                    ],
                }
            ],
        }
    )


def verdict(check, visual=None):
    visual = visual or pies()
    claim = ExtractedClaim(
        claim_id="c1",
        source_ids=["P3S1"],
        kind="numeric_value",
        claim="Fictional claim.",
        check=check,
    )
    return verify_claim(claim, visual, derive_facts(visual))[0]


@pytest.mark.parametrize(
    "label,start,end", list(zip(LABELS, VALUES["2000"], VALUES["2010"], strict=True))
)
def test_current_perception_pie_matrix_verifies_values_changes_and_comparisons(label, start, end):
    visual = matrix()
    for year, value in [("2000", start), ("2010", end)]:
        assert (
            verdict(
                {
                    "type": "numeric",
                    "subject": label,
                    "fact": "value",
                    "category": year,
                    "value": value,
                },
                visual,
            )
            == "SUPPORTED"
        )
    assert (
        verdict(
            {
                "type": "numeric",
                "subject": label,
                "fact": "absolute_change",
                "category": "2000",
                "end_category": "2010",
                "value": end - start,
            },
            visual,
        )
        == "SUPPORTED"
    )
    assert (
        verdict(
            {
                "type": "comparison",
                "subject": label,
                "other": label,
                "category": "2010",
                "other_category": "2000",
                "operator": "gt" if end > start else "lt" if end < start else "eq",
            },
            visual,
        )
        == "SUPPORTED"
    )
    if start == end:
        assert (
            verdict(
                {
                    "type": "numeric",
                    "subject": label,
                    "fact": "stable",
                    "category": "2000",
                    "end_category": "2010",
                    "value": start,
                },
                visual,
            )
            == "SUPPORTED"
        )


@pytest.mark.parametrize("year", VALUES)
def test_current_pie_matrix_largest_category(year):
    assert (
        verdict(
            {
                "type": "numeric",
                "subject": "Spanish only",
                "fact": "rank",
                "category": year,
                "value": 1,
            },
            matrix(),
        )
        == "SUPPORTED"
    )


@pytest.mark.parametrize(
    "year,label,value",
    [
        (year, label, value)
        for year, values in VALUES.items()
        for label, value in zip(LABELS, values, strict=True)
    ],
)
def test_pie_slice_identity_and_exact_percentage(year, label, value):
    check = {"type": "numeric", "subject": label, "fact": "value", "category": year, "value": value}
    assert verdict(check) == "SUPPORTED"
    assert verdict({**check, "value": value + 1}) == "CONTRADICTED"


@pytest.mark.parametrize(
    "label,start,end", list(zip(LABELS, VALUES["2000"], VALUES["2010"], strict=True))
)
def test_pie_change_and_direct_cross_year_comparison(label, start, end):
    direction = "increase" if end > start else "decrease" if end < start else "stable"
    assert (
        verdict(
            {
                "type": "numeric",
                "subject": label,
                "fact": "overall_direction",
                "category": "2000",
                "end_category": "2010",
                "direction": direction,
            }
        )
        == "SUPPORTED"
    )
    assert (
        verdict(
            {
                "type": "numeric",
                "subject": label,
                "fact": "absolute_change",
                "category": "2000",
                "end_category": "2010",
                "value": end - start,
            }
        )
        == "SUPPORTED"
    )
    assert (
        verdict(
            {
                "type": "comparison",
                "subject": label,
                "other": label,
                "category": "2000",
                "other_category": "2010",
                "operator": "lt" if start < end else "gt" if start > end else "eq",
            }
        )
        == "SUPPORTED"
    )


@pytest.mark.parametrize("year", VALUES)
def test_largest_pie_category(year):
    assert (
        verdict(
            {
                "type": "numeric",
                "subject": "Spanish only",
                "fact": "rank",
                "category": year,
                "value": 1,
            }
        )
        == "SUPPORTED"
    )


def test_unchanged_slice_uses_the_explicit_pair_interval():
    assert (
        verdict(
            {
                "type": "numeric",
                "subject": "German only",
                "fact": "stable",
                "category": "2000",
                "end_category": "2010",
                "value": 10,
            }
        )
        == "SUPPORTED"
    )


def test_missing_declared_slice_cannot_establish_a_largest_category():
    visual = pies()
    visual.components[0].series[0].points.pop(3)
    assert (
        verdict(
            {
                "type": "numeric",
                "subject": "No other language",
                "fact": "rank",
                "category": "2000",
                "value": 1,
            },
            visual,
        )
        == "INSUFFICIENT_EVIDENCE"
    )


def test_fact_view_does_not_rewrite_perception_or_merge_point_identities():
    visual = pies()
    original = visual.model_dump(mode="json")
    facts = derive_facts(visual)
    assert visual.model_dump(mode="json") == original
    assert {f.component_id for f in facts if f.kind == "value"} == {"pie-2000", "pie-2010"}
    assert len([f for f in facts if f.kind == "value"]) == 12
    assert len({f.id for f in facts}) == len(facts)


@pytest.mark.parametrize(
    "mutation", ["null", "unreliable", "unknown_state", "incompatible_unit", "different_cohort"]
)
def test_uncertain_or_incompatible_pies_do_not_manufacture_cross_year_claims(mutation):
    visual = pies()
    if mutation == "null":
        visual.components[1].series[0].points[3].value = None
    elif mutation == "unreliable":
        visual.components[1].series[0].points[3].confidence = 0.5
    elif mutation == "unknown_state":
        visual.components[1].state = None
    elif mutation == "incompatible_unit":
        visual.components[1].unit = "people"
    else:
        visual.components[1].title = "Unrelated cohort 2010"
    assert (
        verdict(
            {
                "type": "numeric",
                "subject": "Spanish only",
                "fact": "overall_direction",
                "category": "2000",
                "end_category": "2010",
                "direction": "increase",
            },
            visual,
        )
        == "INSUFFICIENT_EVIDENCE"
    )
