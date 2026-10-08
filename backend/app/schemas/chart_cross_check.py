"""Bounded specialist data and safe persisted diagnostics; never IELTS scores."""

from typing import Literal

from pydantic import Field

from app.schemas.task1_visual import Number, Text, VisualModel

DEPLOT_MODEL = "google/deplot"
DEPLOT_REVISION = "6e76d62430da16986be3426bae32301fb9115397"
CHART_CONTRACT_VERSION = "deplot-table-v1:exact-label-decimal-v1"
ChartWarning = Literal[
    "CHART_SPECIALIST_UNAVAILABLE",
    "CHART_SPECIALIST_PARSE_FAILED",
    "CHART_RECONCILIATION_FAILED",
    "CHART_DATA_DISAGREEMENT",
    "CHART_ALIGNMENT_UNCERTAIN",
    "CHART_CELLS_UNPARSEABLE",
]


class ChartSpecialistIdentity(VisualModel):
    enabled: bool = False
    provider: str = Field(default="deplot", max_length=40)
    model: str = Field(default=DEPLOT_MODEL, max_length=160)
    revision: str = Field(default=DEPLOT_REVISION, max_length=80)
    contract_version: str = Field(default=CHART_CONTRACT_VERSION, max_length=80)


class SpecialistCell(VisualModel):
    row: Text
    column: Text
    value: Number | None
    unit: Literal["percent"] | None = None
    status: Literal["VALUE", "MISSING", "UNPARSEABLE"]


class SpecialistChartObservation(VisualModel):
    title: str = Field(default="", max_length=120)
    rows: list[Text] = Field(min_length=1, max_length=30)
    columns: list[Text] = Field(min_length=1, max_length=30)
    cells: list[SpecialistCell] = Field(max_length=900)


class ChartCrossCheckResult(VisualModel):
    specialist_used: bool
    specialist_model: str = Field(max_length=160)
    specialist_revision: str = Field(max_length=80)
    status: Literal["COMPLETED", "UNAVAILABLE", "PARSE_FAILED", "RECONCILIATION_FAILED"]
    agreement_count: int = Field(default=0, ge=0, le=2000)
    disagreement_count: int = Field(default=0, ge=0, le=2000)
    unmatched_primary_count: int = Field(default=0, ge=0, le=2000)
    unmatched_specialist_count: int = Field(default=0, ge=0, le=2000)
    unknown_count: int = Field(default=0, ge=0, le=2000)
    warnings: list[ChartWarning] = Field(default_factory=list, max_length=6)
