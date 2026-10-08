"""Independent perception reconciliation by exact normalized labels and Decimal.

No numeric tolerance, fuzzy matching, specialist-only additions or score rules.
An uncertain value is removed before derive_facts and claim verification.
"""

from collections import Counter

from app.domains.scoring.deplot_parser import normalize_label
from app.schemas.chart_cross_check import (
    ChartCrossCheckResult,
    ChartSpecialistIdentity,
    SpecialistChartObservation,
)
from app.schemas.task1_visual import ChartTableVisualReference, GroundingConfidence


def reconcile_chart(
    primary: ChartTableVisualReference,
    specialist: SpecialistChartObservation,
    identity: ChartSpecialistIdentity,
) -> tuple[ChartTableVisualReference, ChartCrossCheckResult]:
    reference = primary.model_copy(deep=True)
    diagnostic = ChartCrossCheckResult(
        specialist_used=True,
        specialist_model=identity.model,
        specialist_revision=identity.revision,
        status="COMPLETED",
    )
    index = {}
    for i, cell in enumerate(specialist.cells):
        key = (normalize_label(cell.row), normalize_label(cell.column))
        index.setdefault(key, []).append(i)
    # Keep component separation. A specialist cell cannot attest to two charts.
    entries = []
    for component in reference.components:
        for cell in component.cells:
            entries.append(
                (component, cell, {(normalize_label(cell.row), normalize_label(cell.column))})
            )
        for series in component.series:
            for point in series.points:
                rows = {series.name}
                if component.kind == "pie_chart" and len(component.series) == 1:
                    rows.update(label for label in (component.state, component.title) if label)
                keys = {(normalize_label(row), normalize_label(point.category)) for row in rows}
                entries.append((component, point, keys))
    matches = []
    for _, _, keys in entries:
        candidates = set()
        for row, column in keys:
            candidates.update(index.get((row, column), []))
            candidates.update(index.get((column, row), []))
        matches.append(candidates)
    usage = Counter(next(iter(indices)) for indices in matches if len(indices) == 1)
    percent_units = {"%", "percent", "percentage", "percentages"}
    units = {
        "percent"
        if normalize_label(component.unit or "") in percent_units
        else normalize_label(component.unit or "")
        for component in reference.components
    }
    used = set()
    for (component, point, _), indices in zip(entries, matches, strict=True):
        if not indices:
            diagnostic.unmatched_primary_count += 1
            continue
        if len(indices) != 1 or usage[next(iter(indices))] != 1:
            diagnostic.unknown_count += 1
            continue
        i = next(iter(indices))
        cell = specialist.cells[i]
        primary_unit = normalize_label(component.unit or "")
        percent = primary_unit in percent_units
        # Explicit conflicting units, or unknown units across mixed units, cannot align.
        if (cell.unit == "percent" and not percent) or (cell.unit is None and len(units) > 1):
            diagnostic.unknown_count += 1
            continue
        used.add(i)
        if cell.value is None:
            diagnostic.unmatched_primary_count += 1
        elif point.value is None:
            diagnostic.unmatched_specialist_count += 1
        elif point.value != cell.value:
            diagnostic.disagreement_count += 1
            point.value, point.confidence = None, 0
        else:
            diagnostic.agreement_count += 1
            labelled = getattr(point, "value_is_labelled", None)
            if labelled is False:
                point.confidence = min(point.confidence, 0.79)
            elif component.kind in {"pie_chart", "table"} or labelled is True:
                # Root LOW/UNUSABLE still prevents deriving exact facts.
                point.confidence = max(point.confidence, 0.9)
    diagnostic.unmatched_specialist_count += sum(
        cell.value is not None for i, cell in enumerate(specialist.cells) if i not in used
    )
    if any(cell.status == "UNPARSEABLE" for cell in specialist.cells):
        diagnostic.warnings.append("CHART_CELLS_UNPARSEABLE")
    if diagnostic.disagreement_count:
        diagnostic.warnings.append("CHART_DATA_DISAGREEMENT")
        # The primary narrative may repeat a disputed number. Regenerate only
        # safe display context locally; never leave stale numeric prose as evidence.
        reference.summary = (
            "Một số số liệu chưa được xác nhận chéo; chỉ dùng các dữ kiện còn chắc chắn."
        )
        if reference.confidence == "HIGH":
            reference.confidence = GroundingConfidence.MEDIUM
        reference.uncertainty = reference.uncertainty[:3] + [
            "Một số số liệu chưa được hai nguồn đọc thống nhất; không dùng để khẳng định lỗi số liệu."
        ]
    if (
        diagnostic.unknown_count
        or diagnostic.unmatched_primary_count
        or diagnostic.unmatched_specialist_count
    ):
        diagnostic.warnings.append("CHART_ALIGNMENT_UNCERTAIN")
    return reference, diagnostic
