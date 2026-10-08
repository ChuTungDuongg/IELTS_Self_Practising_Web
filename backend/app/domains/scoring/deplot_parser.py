"""Parse only bounded linearized table data, never specialist instructions/code."""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from app.schemas.chart_cross_check import SpecialistCell, SpecialistChartObservation


class DePlotParseError(ValueError):
    pass


def normalize_label(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def _label(value: str) -> str:
    label = unicodedata.normalize("NFC", value.strip())
    if not label or len(label) > 120:
        raise DePlotParseError("Invalid table label")
    return label


def _column(value: str) -> tuple[str, bool]:
    percent = bool(re.search(r"\s*\(%\)$", value))
    return _label(re.sub(r"\s*\(%\)$", "", value)), percent


def _cell(row: str, column: str, text: str, percent: bool) -> SpecialistCell:
    unit = "percent" if percent or text.endswith("%") else None
    numeric = text.removesuffix("%").strip()
    value, status = None, "UNPARSEABLE"
    if normalize_label(text) in {"", "-", "—", "n/a", "na", "null", "?"}:
        status = "MISSING"
    elif len(numeric) <= 48 and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", numeric):
        try:
            value = Decimal(numeric)
            # Validate against the same bounded Decimal contract as primary data.
            return SpecialistCell(row=row, column=column, value=value, unit=unit, status="VALUE")
        except (InvalidOperation, ValidationError):
            value = None
    return SpecialistCell(row=row, column=column, value=value, unit=unit, status=status)


def parse_deplot(text: str) -> SpecialistChartObservation:
    if not isinstance(text, str) or not 0 < len(text) <= 16384:
        raise DePlotParseError("Invalid table size")
    lines = [line.strip() for line in text.replace("<0x0A>", "\n").splitlines() if line.strip()]
    title = ""
    if lines and lines[0].upper().startswith("TITLE |"):
        title = _label(lines.pop(0).split("|", 1)[1])
    if not 2 <= len(lines) <= 31:
        raise DePlotParseError("Invalid row count")
    headers = [item.strip() for item in lines[0].split("|")]
    if not 2 <= len(headers) <= 31:
        raise DePlotParseError("Invalid column count")
    columns = [_column(item) for item in headers[1:]]
    keys = [normalize_label(item[0]) for item in columns]
    if len(set(keys)) != len(keys):
        raise DePlotParseError("Duplicate columns")
    rows, cells = [], []
    for line in lines[1:]:
        parts = [item.strip() for item in line.split("|")]
        if len(parts) != len(headers):
            raise DePlotParseError("Inconsistent columns")
        row = _label(parts[0])
        if normalize_label(row) in {normalize_label(existing) for existing in rows}:
            raise DePlotParseError("Duplicate rows")
        rows.append(row)
        cells.extend(
            _cell(row, column, item, percent)
            for (column, percent), item in zip(columns, parts[1:], strict=True)
        )
    if not any(cell.status == "VALUE" for cell in cells):
        raise DePlotParseError("No usable values")
    return SpecialistChartObservation(
        title=title, rows=rows, columns=[item[0] for item in columns], cells=cells
    )
