"""Pure benchmark arithmetic; human labels never alter production scores.

Rates are fractions in [0, 1]. Perception metrics compare exact normalized semantic
identities and Decimal values, without fuzzy matching, tolerances or imputation.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domains.scoring.ai_writing import aggregate_ai_task_two
from app.schemas.task1_visual import ChartComponent, ChartTableVisualReference, VisualReference

TRAITS = ("ta", "cc", "lr", "gra")


def overall_score(scores: Mapping[str, Decimal | None]) -> Decimal | None:
    """Use the same four-criterion mean and half-up rounding as production."""
    values = [scores.get(trait) for trait in TRAITS]
    if any(value is None for value in values):
        return None
    _, overall = aggregate_ai_task_two(*(value for value in values if value is not None))
    return overall


def score_metrics(
    pairs: Sequence[tuple[Decimal, Decimal]], *, minimum_qwk_samples: int = 10
) -> dict[str, Any]:
    """Agreement and signed predicted-minus-human error, without calibrating scores.

    QWK uses all 19 official half-band categories from 0 to 9, including empty
    categories. Non-half-band human averages retain their exact error metrics;
    their QWK is unavailable rather than silently quantizing their labels.
    """
    if minimum_qwk_samples < 1:
        raise ValueError("minimum_qwk_samples must be positive")
    for target, predicted in pairs:
        if any(
            not score.is_finite() or not Decimal(0) <= score <= Decimal(9)
            for score in (target, predicted)
        ):
            raise ValueError("Benchmark scores must be finite and between 0 and 9")
    count = len(pairs)
    result: dict[str, Any] = dict.fromkeys(
        (
            "exact_agreement",
            "within_0_5",
            "within_1_0",
            "signed_bias",
            "mae",
            "rmse",
            "quadratic_weighted_kappa",
        )
    )
    result["count"] = count
    if not count:
        result["qwk_status"] = "no_samples"
        return result
    errors = [predicted - target for target, predicted in pairs]
    absolute = [abs(error) for error in errors]
    result.update(
        exact_agreement=sum(error == 0 for error in errors) / count,
        within_0_5=sum(error <= Decimal("0.5") for error in absolute) / count,
        within_1_0=sum(error <= 1 for error in absolute) / count,
        signed_bias=float(sum(errors, Decimal(0)) / count),
        mae=float(sum(absolute, Decimal(0)) / count),
        rmse=float((sum((error * error for error in errors), Decimal(0)) / count).sqrt()),
    )
    if count < minimum_qwk_samples:
        result["qwk_status"] = "insufficient_samples"
        return result
    if any(score % Decimal("0.5") != 0 for pair in pairs for score in pair):
        result["qwk_status"] = "non_half_band_scores"
        return result
    targets, predictions = [0] * 19, [0] * 19
    observed_disagreement = 0
    for target, predicted in pairs:
        target_index, predicted_index = int(target * 2), int(predicted * 2)
        targets[target_index] += 1
        predictions[predicted_index] += 1
        observed_disagreement += (target_index - predicted_index) ** 2
    # The common quadratic weight divisor (18**2) cancels from the ratio.
    expected_disagreement = sum(
        targets[i] * predictions[j] * (i - j) ** 2 for i in range(19) for j in range(19)
    )
    if expected_disagreement == 0:
        result["qwk_status"] = "undefined_expected_variance"
    else:
        result["quadratic_weighted_kappa"] = float(
            1 - Decimal(count * observed_disagreement) / expected_disagreement
        )
        result["qwk_status"] = "ok"
    return result


def _label(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _component_key(component: ChartComponent) -> tuple[str, str]:
    unit = _label(component.unit)
    return component.kind, "%" if unit in {"%", "percent", "percentage"} else unit


def _declared_labels(component: ChartComponent) -> dict[str, list[str]]:
    return {
        "series": [_label(series.name) for series in component.series],
        "categories": [_label(category) for category in component.categories],
        "legend": [_label(label) for label in component.legend],
        "row_headers": [_label(label) for label in component.row_headers],
        "column_headers": [_label(label) for label in component.column_headers],
    }


def _semantically_identical_component(truth: ChartComponent, observed: ChartComponent) -> bool:
    """Disambiguate repeated kind/unit components by declared labels, never values."""
    truth_semantics = (_label(truth.title), _label(truth.state))
    if any(truth_semantics):
        return truth_semantics == (_label(observed.title), _label(observed.state))
    truth_labels, observed_labels = _declared_labels(truth), _declared_labels(observed)
    return any(truth_labels.values()) and all(
        Counter(truth_labels[name]) == Counter(observed_labels[name]) for name in truth_labels
    )


def _match_components(
    truth: Sequence[ChartComponent], observed: Sequence[ChartComponent]
) -> tuple[dict[int, int], int]:
    truth_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    observed_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, component in enumerate(truth):
        truth_groups[_component_key(component)].append(index)
    for index, component in enumerate(observed):
        observed_groups[_component_key(component)].append(index)
    matches, ambiguous = {}, 0
    for base, truth_indices in truth_groups.items():
        observed_indices = observed_groups.get(base, [])
        if len(truth_indices) == len(observed_indices) == 1:
            matches[truth_indices[0]] = observed_indices[0]
            continue
        candidates = {
            index: [
                other
                for other in observed_indices
                if _semantically_identical_component(truth[index], observed[other])
            ]
            for index in truth_indices
        }
        usage = Counter(other for indices in candidates.values() for other in indices)
        for index, indices in candidates.items():
            if len(indices) == 1 and usage[indices[0]] == 1:
                matches[index] = indices[0]
            elif indices:
                ambiguous += 1
    return matches, ambiguous


@dataclass(frozen=True)
class _Value:
    identity: tuple[str, str]
    value: Decimal | None
    labelled: bool


def _values(component: ChartComponent) -> list[_Value]:
    if component.kind == "table":
        return [
            _Value((_label(cell.row), _label(cell.column)), cell.value, True)
            for cell in component.cells
        ]
    return [
        _Value(
            (_label(series.name), _label(point.category)),
            point.value,
            point.value_is_labelled is not False,
        )
        for series in component.series
        for point in series.points
    ]


def _index(values: Sequence[_Value]) -> dict[tuple[str, str], list[_Value]]:
    result: dict[tuple[str, str], list[_Value]] = defaultdict(list)
    for value in values:
        result[value.identity].append(value)
    return result


def perception_metrics(
    truth: VisualReference | None, observed: VisualReference | None
) -> dict[str, Any] | None:
    """Compare optional human chart/table annotations with a grounded reference.

    Component/series IDs are provider-local and are ignored. Unique kind/unit
    components align directly; repeated components require unique semantic label
    matches. Duplicate normalized identities are ambiguous and never overwritten.
    Unknown or explicitly unlabelled truth numbers prevent asserting perception_ok
    even when every comparable labelled value is exact. Missing/wrong identities
    and known numeric disagreements always report False.
    """
    if not isinstance(truth, ChartTableVisualReference):
        return None
    observed_components = (
        observed.components if isinstance(observed, ChartTableVisualReference) else []
    )
    matches, ambiguous_components = _match_components(truth.components, observed_components)
    truth_values = [_values(component) for component in truth.components]
    observed_values = [_values(component) for component in observed_components]
    all_truth = [value for values in truth_values for value in values]
    all_observed = [value for values in observed_values for value in values]
    result: dict[str, Any] = {
        "truth_values": len(all_truth),
        "observed_values": len(all_observed),
        "labelled_numeric_count": sum(
            value.labelled and value.value is not None for value in all_truth
        ),
        "exact_labelled_numeric_count": 0,
        "aligned_values": 0,
        "missing_values": 0,
        "extra_values": 0,
        "unavailable_truth_values": sum(value.value is None for value in all_truth),
        "unlabelled_truth_values": sum(not value.labelled for value in all_truth),
        "unavailable_observed_values": sum(value.value is None for value in all_observed),
        "missing_components": len(truth.components) - len(matches),
        "extra_components": len(observed_components) - len(matches),
        "ambiguous_components": ambiguous_components,
        "ambiguous_values": 0,
        "ambiguous_labels": 0,
    }
    label_names = tuple(_declared_labels(truth.components[0]))
    for name in label_names:
        result[f"missing_{name}"] = 0
        result[f"extra_{name}"] = 0
    matched_observed = set(matches.values())
    for index, component in enumerate(truth.components):
        target_labels = _declared_labels(component)
        actual_labels = (
            _declared_labels(observed_components[matches[index]]) if index in matches else {}
        )
        for name in label_names:
            target, actual = Counter(target_labels[name]), Counter(actual_labels.get(name, []))
            result[f"missing_{name}"] += sum((target - actual).values())
            result[f"extra_{name}"] += sum((actual - target).values())
            result["ambiguous_labels"] += sum(count > 1 for count in target.values())
            result["ambiguous_labels"] += sum(count > 1 for count in actual.values())
        target_index = _index(truth_values[index])
        actual_index = _index(observed_values[matches[index]]) if index in matches else {}
        for identity in target_index.keys() | actual_index.keys():
            target, actual = target_index.get(identity, []), actual_index.get(identity, [])
            if len(target) > 1 or len(actual) > 1:
                result["ambiguous_values"] += 1
            aligned = len(target) == len(actual) == 1
            if aligned:
                result["aligned_values"] += 1
            for value in target:
                if value.labelled and value.value is not None:
                    if aligned and actual[0].value == value.value:
                        result["exact_labelled_numeric_count"] += 1
                    elif not aligned or actual[0].value is None:
                        result["missing_values"] += 1
            if not target:
                result["extra_values"] += sum(value.value is not None for value in actual)
    for index, component in enumerate(observed_components):
        if index in matched_observed:
            continue
        result["extra_values"] += sum(value.value is not None for value in observed_values[index])
        for name, labels in _declared_labels(component).items():
            result[f"extra_{name}"] += len(labels)
            result["ambiguous_labels"] += sum(count > 1 for count in Counter(labels).values())
    result["unavailable_values"] = (
        result["unavailable_truth_values"] + result["unavailable_observed_values"]
    )
    numeric_count = result["labelled_numeric_count"]
    result["exact_labelled_numeric_agreement"] = (
        result["exact_labelled_numeric_count"] / numeric_count if numeric_count else None
    )
    result["value_alignment"] = result["aligned_values"] / len(all_truth) if all_truth else None
    identity_errors = (
        result["missing_components"]
        + result["extra_components"]
        + result["ambiguous_components"]
        + result["ambiguous_values"]
        + result["ambiguous_labels"]
        + sum(result[f"{prefix}_{name}"] for prefix in ("missing", "extra") for name in label_names)
    )
    result["identity_complete"] = not identity_errors and result["aligned_values"] == len(
        all_truth
    ) == len(all_observed)
    if (
        not result["identity_complete"]
        or result["missing_values"]
        or result["extra_values"]
        or result["exact_labelled_numeric_count"] != numeric_count
    ):
        result["perception_ok"] = False
    elif (
        result["unavailable_truth_values"] or result["unlabelled_truth_values"] or not numeric_count
    ):
        result["perception_ok"] = None
    else:
        result["perception_ok"] = True
    return result


def repeated_perception_metrics(observations: Sequence[dict[str, Any] | None]) -> dict[str, Any] | None:
    """Pool counts across independent perceptions, keeping sample certification strict."""
    available = [item for item in observations if item is not None]
    if not available:
        return None
    count_keys = {
        key for item in available for key, value in item.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }
    result = {key: sum(item.get(key, 0) for item in available) for key in count_keys}
    numeric = result["labelled_numeric_count"]
    truth_values = result["truth_values"]
    result.update(
        exact_labelled_numeric_agreement=result["exact_labelled_numeric_count"] / numeric if numeric else None,
        value_alignment=result["aligned_values"] / truth_values if truth_values else None,
        identity_complete=all(item is not None and item["identity_complete"] for item in observations),
        perception_ok=True
        if all(item is not None and item["perception_ok"] is True for item in observations)
        else False if any(item["perception_ok"] is False for item in available) else None,
        repeat_observation_count=len(available),
        unavailable_repeat_observation_count=len(observations) - len(available),
    )
    return result
