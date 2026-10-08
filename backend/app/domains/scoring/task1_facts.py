"""Provider-free Decimal arithmetic on reliable, structurally compatible visual data."""

from decimal import Decimal
from itertools import combinations
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.task1_visual import (
    ChartComponent,
    ChartTableVisualReference,
    Point,
    Text,
    VisualModel,
    VisualReference,
)

FactKind = Literal[
    "value",
    "min",
    "max",
    "start",
    "end",
    "absolute_change",
    "percentage_change",
    "rank",
    "rank_change",
    "largest_increase",
    "largest_decrease",
    "stable",
    "overall_direction",
    "crossover",
]
RELIABLE_VALUE_CONFIDENCE = 0.8  # Perception reliability, never a score/rubric threshold.
MAX_DERIVED_FACTS = 1600
FactNumber = Annotated[Decimal, Field(allow_inf_nan=False, ge=-1e24, le=1e24)]


class DerivedFact(VisualModel):
    id: str = Field(max_length=40)
    component_id: str = Field(max_length=40)
    kind: FactKind
    subjects: list[Text] = Field(min_length=1, max_length=12)
    category: str | None = Field(default=None, max_length=120)
    end_category: str | None = Field(default=None, max_length=120)
    value: FactNumber | None = None
    direction: Literal["increase", "decrease", "stable"] | None = None


def reliable(point: Point | None) -> bool:
    return (
        point is not None
        and point.value is not None
        and point.confidence >= RELIABLE_VALUE_CONFIDENCE
    )


def component_series(component: ChartComponent) -> dict[str, dict[str, Point]]:
    if component.kind == "table":
        return {
            row: {
                cell.column: Point(
                    category=cell.column, value=cell.value, confidence=cell.confidence
                )
                for cell in component.cells
                if cell.row == row
            }
            for row in component.row_headers
        }
    return {
        series.name: {point.category: point for point in series.points}
        for series in component.series
    }


def derive_facts(reference: VisualReference) -> list[DerivedFact]:
    if not isinstance(reference, ChartTableVisualReference) or reference.confidence not in {
        "HIGH",
        "MEDIUM",
    }:
        return []
    facts: list[DerivedFact] = []

    def add(component: ChartComponent, kind: FactKind, subjects: list[str], **kwargs) -> None:
        if len(facts) >= MAX_DERIVED_FACTS:
            return
        facts.append(
            DerivedFact(
                id=f"f{len(facts) + 1}",
                component_id=component.id,
                kind=kind,
                subjects=subjects,
                **kwargs,
            )
        )

    for component in reference.components:
        series = component_series(component)
        categories = component.column_headers if component.kind == "table" else component.categories
        changes: dict[str, Decimal] = {}
        ranks: dict[str, dict[str, int]] = {}
        for name, points in series.items():
            for category in categories:
                point = points.get(category)
                if reliable(point):
                    add(component, "value", [name], category=category, value=point.value)
            # Extrema require the whole declared series, not a biased reliable subset.
            if categories and all(reliable(points.get(category)) for category in categories):
                minimum = min(points[c].value for c in categories)
                maximum = max(points[c].value for c in categories)
                for kind, value in (("min", minimum), ("max", maximum)):
                    for category in categories:
                        if points[category].value == value:
                            add(component, kind, [name], category=category, value=value)
                if len(categories) > 1 and minimum == maximum:
                    add(component, "stable", [name], value=minimum)
            if not component.ordered_categories or len(categories) < 2:
                continue
            start, end = points.get(categories[0]), points.get(categories[-1])
            if reliable(start) and reliable(end):
                difference = end.value - start.value
                changes[name] = difference
                add(component, "start", [name], category=categories[0], value=start.value)
                add(component, "end", [name], category=categories[-1], value=end.value)
                add(
                    component,
                    "absolute_change",
                    [name],
                    category=categories[0],
                    end_category=categories[-1],
                    value=difference,
                )
                if start.value != 0:
                    add(
                        component,
                        "percentage_change",
                        [name],
                        category=categories[0],
                        end_category=categories[-1],
                        value=difference / start.value * Decimal(100),
                    )
                add(
                    component,
                    "overall_direction",
                    [name],
                    category=categories[0],
                    end_category=categories[-1],
                    direction="increase"
                    if difference > 0
                    else "decrease"
                    if difference < 0
                    else "stable",
                )
        for category in categories:
            if not series or not all(reliable(points.get(category)) for points in series.values()):
                continue
            # Dense rank: ties share a rank, never arbitrary model/iteration order.
            values = sorted({points[category].value for points in series.values()}, reverse=True)
            ranks[category] = {
                name: values.index(points[category].value) + 1 for name, points in series.items()
            }
            for name, rank in ranks[category].items():
                add(component, "rank", [name], category=category, value=Decimal(rank))
        if component.ordered_categories and len(categories) > 1:
            first, last = categories[0], categories[-1]
            if first in ranks and last in ranks:
                for name in series:
                    add(
                        component,
                        "rank_change",
                        [name],
                        category=first,
                        end_category=last,
                        value=Decimal(ranks[first][name] - ranks[last][name]),
                    )
            if len(changes) == len(series) and changes:
                for kind, extreme in (
                    ("largest_increase", max(changes.values())),
                    ("largest_decrease", min(changes.values())),
                ):
                    if (kind == "largest_increase" and extreme > 0) or (
                        kind == "largest_decrease" and extreme < 0
                    ):
                        for name, value in changes.items():
                            if value == extreme:
                                add(
                                    component,
                                    kind,
                                    [name],
                                    category=first,
                                    end_category=last,
                                    value=extreme,
                                )
            for left, right in combinations(series, 2):
                for start_category, end_category in zip(categories, categories[1:], strict=False):
                    points = [
                        series[name].get(category)
                        for name in (left, right)
                        for category in (start_category, end_category)
                    ]
                    if all(reliable(point) for point in points):
                        a, b, c, d = [point.value for point in points]
                        if (a - c) * (b - d) < 0:
                            add(
                                component,
                                "crossover",
                                [left, right],
                                category=start_category,
                                end_category=end_category,
                            )
    return facts
