"""Hand-calculated, provider-free Task 1 benchmark metric examples."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.evaluation.task1.metrics import overall_score, perception_metrics, score_metrics
from app.schemas.task1_visual import ChartTableVisualReference, OtherVisualReference


def pairs(*values: tuple[str, str]) -> list[tuple[Decimal, Decimal]]:
    return [(Decimal(target), Decimal(predicted)) for target, predicted in values]


def matrix() -> ChartTableVisualReference:
    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "synthetic_six_region_pie_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    return ChartTableVisualReference.model_validate(raw["reference"])


def test_score_metrics_report_positive_bias_and_hand_calculated_agreement() -> None:
    result = score_metrics(pairs(("5", "5"), ("5.5", "6"), ("6", "7"), ("6.5", "8")))
    assert result["count"] == 4
    assert result["exact_agreement"] == 0.25
    assert result["within_0_5"] == 0.5
    assert result["within_1_0"] == 0.75
    assert result["signed_bias"] == 0.75
    assert result["mae"] == 0.75
    assert result["rmse"] == pytest.approx(0.9354143466934853)
    assert result["quadratic_weighted_kappa"] is None
    assert result["qwk_status"] == "insufficient_samples"


def test_score_metrics_preserve_negative_signed_bias() -> None:
    result = score_metrics(pairs(("6", "5"), ("7", "6.5")))
    assert result["signed_bias"] == -0.75
    assert result["mae"] == 0.75


def test_qwk_matches_hand_calculated_nontrivial_example() -> None:
    # Observed squared error=3.5; independent marginal squared error=8.5.
    result = score_metrics(
        pairs(("5", "5"), ("5.5", "6"), ("6", "7"), ("6.5", "8")),
        minimum_qwk_samples=4,
    )
    assert result["quadratic_weighted_kappa"] == pytest.approx(10 / 17)
    assert result["qwk_status"] == "ok"


@pytest.mark.parametrize(
    ("values", "expected"),
    [([("0", "0"), ("9", "9")] * 5, 1.0), ([("0", "9"), ("9", "0")] * 5, -1.0)],
)
def test_qwk_perfect_and_worst_agreement_use_official_scale(values, expected) -> None:
    assert score_metrics(pairs(*values))["quadratic_weighted_kappa"] == expected


def test_qwk_does_not_claim_perfect_agreement_when_expected_variance_is_zero() -> None:
    result = score_metrics(pairs(*[("6", "6")] * 10))
    assert result["exact_agreement"] == 1.0
    assert result["quadratic_weighted_kappa"] is None
    assert result["qwk_status"] == "undefined_expected_variance"


def test_qwk_never_quantizes_average_rater_scores() -> None:
    result = score_metrics(pairs(*[("6.25", "6.5")] * 10))
    assert result["signed_bias"] == 0.25
    assert result["quadratic_weighted_kappa"] is None
    assert result["qwk_status"] == "non_half_band_scores"


def test_score_metrics_empty_population_has_no_manufactured_rates() -> None:
    result = score_metrics([])
    assert result["count"] == 0
    assert result["qwk_status"] == "no_samples"
    for name in (
        "exact_agreement",
        "within_0_5",
        "within_1_0",
        "signed_bias",
        "mae",
        "rmse",
        "quadratic_weighted_kappa",
    ):
        assert result[name] is None


@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "-0.5", "9.5"])
def test_score_metrics_reject_invalid_official_band_range(invalid: str) -> None:
    with pytest.raises(ValueError):
        score_metrics(pairs((invalid, "6")))


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ({"ta": "6", "cc": "6", "lr": "6", "gra": "6.5"}, "6"),
        ({"ta": "6", "cc": "6", "lr": "6.5", "gra": "6.5"}, "6.5"),
        ({"ta": "6", "cc": "6.5", "lr": "6.5", "gra": "6.5"}, "6.5"),
    ],
)
def test_overall_uses_existing_mean_and_half_up_rounding(scores, expected) -> None:
    assert overall_score({trait: Decimal(value) for trait, value in scores.items()}) == Decimal(
        expected
    )


def test_overall_missing_criterion_is_unavailable() -> None:
    assert overall_score({"ta": Decimal("6"), "cc": Decimal("6"), "lr": Decimal("6")}) is None
    assert overall_score(dict.fromkeys(("ta", "cc", "lr", "gra"))) is None


def test_perception_exact_synthetic_matrix_preserves_semantic_not_opaque_identity() -> None:
    truth = matrix()
    observed = truth.model_copy(deep=True)
    observed.components[0].id = "provider-component-17"
    observed.components[0].categories[0] = "REGION   A"
    for series in observed.components[0].series:
        series.id = "provider-" + series.id
        series.name = series.name.upper()
        series.points[0].category = "REGION   A"
    result = perception_metrics(truth, observed)
    assert result is not None
    assert result["truth_values"] == 18
    assert result["labelled_numeric_count"] == 18
    assert result["exact_labelled_numeric_count"] == 18
    assert result["exact_labelled_numeric_agreement"] == 1.0
    assert result["value_alignment"] == 1.0
    assert result["identity_complete"] is True
    assert result["perception_ok"] is True


@pytest.mark.parametrize("unit", ["percent", "percentage", " PERCENT ", " PeRcEnTaGe "])
def test_perception_percentage_unit_aliases_preserve_exact_chart_identity(unit: str) -> None:
    truth = matrix()
    observed = truth.model_copy(deep=True)
    observed.components[0].unit = unit
    result = perception_metrics(truth, observed)
    assert result["exact_labelled_numeric_count"] == 18
    assert result["missing_components"] == result["extra_components"] == 0
    assert result["perception_ok"] is True


def test_perception_other_units_remain_strict_and_do_not_match_equal_numbers() -> None:
    truth = matrix()
    observed = truth.model_copy(deep=True)
    observed.components[0].unit = "fraction"
    result = perception_metrics(truth, observed)
    assert result["exact_labelled_numeric_count"] == 0
    assert result["missing_components"] == result["extra_components"] == 1
    assert result["perception_ok"] is False


def test_perception_wrong_category_cannot_match_same_numeric_value() -> None:
    truth = matrix()
    observed = truth.model_copy(deep=True)
    observed.components[0].categories[0] = "Region Z"
    for series in observed.components[0].series:
        series.points[0].category = "Region Z"
    result = perception_metrics(truth, observed)
    assert result["exact_labelled_numeric_count"] == 15
    assert result["missing_values"] == 3
    assert result["extra_values"] == 3
    assert result["missing_categories"] == 1
    assert result["extra_categories"] == 1
    assert result["perception_ok"] is False


def test_perception_wrong_series_cannot_match_same_numeric_value() -> None:
    truth = matrix()
    observed = truth.model_copy(deep=True)
    observed.components[0].series[0].name = "Unrelated sector"
    result = perception_metrics(truth, observed)
    assert result["exact_labelled_numeric_count"] == 12
    assert result["missing_values"] == 6
    assert result["extra_values"] == 6
    assert result["missing_series"] == 1
    assert result["extra_series"] == 1
    assert result["perception_ok"] is False


def test_perception_missing_extra_and_unavailable_values_are_separate() -> None:
    truth = matrix()
    observed = truth.model_copy(deep=True)
    observed.components[0].series[0].points.pop()
    observed.components[0].series[1].points[0].value = None
    observed.components[0].categories.append("Region X")
    extra = observed.components[0].series[2].points[0].model_copy(deep=True)
    extra.category = "Region X"
    observed.components[0].series[2].points.append(extra)
    result = perception_metrics(truth, observed)
    assert result["aligned_values"] == 17
    assert result["missing_values"] == 2
    assert result["extra_values"] == 1
    assert result["unavailable_observed_values"] == 1
    assert result["exact_labelled_numeric_count"] == 16
    assert result["perception_ok"] is False


def test_perception_unknown_truth_values_do_not_claim_numeric_accuracy() -> None:
    truth = matrix()
    truth.components[0].series[0].points[0].value = None
    result = perception_metrics(truth, matrix())
    assert result["unavailable_truth_values"] == 1
    assert result["labelled_numeric_count"] == 17
    assert result["exact_labelled_numeric_agreement"] == 1.0
    assert result["value_alignment"] == 1.0
    assert result["extra_values"] == 0
    assert result["perception_ok"] is None


def test_perception_unlabelled_points_contribute_alignment_but_not_numeric_agreement() -> None:
    truth = matrix()
    truth.components[0].series[0].points[0].value_is_labelled = False
    observed = truth.model_copy(deep=True)
    observed.components[0].series[0].points[0].value = Decimal("999")
    result = perception_metrics(truth, observed)
    assert result["aligned_values"] == 18
    assert result["labelled_numeric_count"] == 17
    assert result["exact_labelled_numeric_agreement"] == 1.0
    assert result["perception_ok"] is None


def test_perception_legacy_absent_label_metadata_is_known_numeric_truth() -> None:
    truth = matrix()
    truth.components[0].series[0].points[0].value_is_labelled = None
    result = perception_metrics(truth, truth)
    assert result["labelled_numeric_count"] == 18
    assert result["perception_ok"] is True


def test_perception_normalized_duplicate_series_are_ambiguous_not_overwritten() -> None:
    truth = matrix()
    observed = truth.model_copy(deep=True)
    duplicate = observed.components[0].series[0].model_copy(deep=True)
    duplicate.id = "other"
    duplicate.name = "AGRICULTURE"
    observed.components[0].series.append(duplicate)
    result = perception_metrics(truth, observed)
    assert result["ambiguous_values"] == 6
    assert result["exact_labelled_numeric_count"] == 12
    assert result["perception_ok"] is False


def test_perception_repeated_same_kind_components_require_semantic_disambiguation() -> None:
    truth = matrix()
    first = truth.components[0]
    first.title = "Year 2020"
    second = first.model_copy(deep=True)
    second.id = "second"
    second.title = "Year 2030"
    second.series[0].points[0].value = Decimal("99")
    truth.components.append(second)
    observed = truth.model_copy(deep=True)
    observed.components.reverse()
    observed.components[0].id = "arbitrary-a"
    observed.components[1].id = "arbitrary-b"
    assert perception_metrics(truth, observed)["perception_ok"] is True
    observed.components[0].title = "Year 2020"
    assert perception_metrics(truth, observed)["perception_ok"] is False


def test_perception_ambiguous_components_are_never_guessed_by_value() -> None:
    truth = matrix()
    second = truth.components[0].model_copy(deep=True)
    second.id = "second"
    truth.components.append(second)
    result = perception_metrics(truth, truth)
    assert result["ambiguous_components"] == 2
    assert result["exact_labelled_numeric_count"] == 0
    assert result["perception_ok"] is False


def test_perception_table_cells_align_by_row_and_column() -> None:
    truth = ChartTableVisualReference.model_validate(
        {
            "visual_family": "chart_table",
            "confidence": "HIGH",
            "components": [
                {
                    "id": "table",
                    "kind": "table",
                    "row_headers": ["North", "South"],
                    "column_headers": ["2020"],
                    "cells": [
                        {"row": "North", "column": "2020", "value": 10, "confidence": 1},
                        {"row": "South", "column": "2020", "value": 20, "confidence": 1},
                    ],
                }
            ],
        }
    )
    observed = truth.model_copy(deep=True)
    observed.components[0].cells[0].value = Decimal("20")
    observed.components[0].cells[1].value = Decimal("10")
    result = perception_metrics(truth, observed)
    assert result["value_alignment"] == 1.0
    assert result["exact_labelled_numeric_agreement"] == 0.0
    assert result["perception_ok"] is False


def test_perception_missing_observation_reports_failure_for_annotated_truth() -> None:
    result = perception_metrics(matrix(), None)
    assert result["missing_values"] == 18
    assert result["missing_components"] == 1
    assert result["perception_ok"] is False


def test_perception_unannotated_and_unsupported_families_are_unavailable() -> None:
    other = OtherVisualReference(
        visual_family="other", confidence="HIGH", entities=[], relationships=[], observations=[]
    )
    assert perception_metrics(None, matrix()) is None
    assert perception_metrics(other, other) is None
