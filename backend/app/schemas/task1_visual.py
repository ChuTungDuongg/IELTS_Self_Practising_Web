"""Bounded semantic visual contracts. Labels/facts stay strict; display prose clips locally."""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.schemas.visual_number import parse_visual_number

Text = Annotated[str, Field(min_length=1, max_length=120)]
Identifier = Annotated[str, Field(min_length=1, max_length=40)]
Number = Annotated[
    Decimal,
    Field(
        allow_inf_nan=False,
        ge=-1_000_000_000_000,
        le=1_000_000_000_000,
        max_digits=24,
        decimal_places=8,
    ),
]
VisualValue = Annotated[Number | None, BeforeValidator(parse_visual_number)]
VisualInvariantError = Literal[
    "duplicate_visual_identifier",
    "duplicate_series_name",
    "duplicate_table_cell",
    "unknown_chart_category",
    "unknown_table_header",
    "table_series_forbidden",
    "chart_cells_forbidden",
]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
_labelled_boolean = TypeAdapter(bool)


class GroundingConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNUSABLE = "UNUSABLE"


class VisualModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def unique(values: list[str], code: VisualInvariantError = "duplicate_visual_identifier") -> None:
    if len(values) != len(set(values)):
        raise PydanticCustomError(code, "Duplicate visual identity")


class VisualBase(VisualModel):
    confidence: GroundingConfidence
    summary: str = Field(default="", max_length=600)
    uncertainty: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("summary", mode="before")
    @classmethod
    def concise_summary(cls, value: object) -> object:
        return value.strip()[:600] if isinstance(value, str) else value

    @field_validator("uncertainty", mode="before")
    @classmethod
    def concise_notes(cls, value: object) -> object:
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return [item.strip()[:240] for item in value[:4] if item.strip()]
        return value


class Point(VisualModel):
    category: Text
    value: VisualValue
    confidence: Confidence
    value_is_labelled: bool | None = None

    @field_validator("value_is_labelled", mode="before")
    @classmethod
    def optional_label_metadata(cls, value: object) -> bool | None:
        # Confidence metadata cannot invalidate an otherwise valid chart point.
        # Use Pydantic's existing boolean conversions; unknown is not false.
        if value is None:
            return None
        try:
            return _labelled_boolean.validate_python(value)
        except ValidationError:
            return None


class Series(VisualModel):
    id: Identifier
    name: Text
    points: list[Point] = Field(max_length=30)

    @model_validator(mode="after")
    def categories_are_unique(self) -> Self:
        unique([point.category for point in self.points])
        return self


class TableCell(VisualModel):
    row: Text
    column: Text
    value: VisualValue
    label: str | None = Field(default=None, max_length=120)
    confidence: Confidence


class ChartComponent(VisualModel):
    id: Identifier
    kind: Literal["line_graph", "bar_chart", "pie_chart", "table"]
    title: str = Field(default="", max_length=120)
    unit: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=120)
    x_axis: str | None = Field(default=None, max_length=120)
    y_axis: str | None = Field(default=None, max_length=120)
    ordered_categories: bool = False
    categories: list[Text] = Field(default_factory=list, max_length=30)
    legend: list[Text] = Field(default_factory=list, max_length=12)
    series: list[Series] = Field(default_factory=list, max_length=12)
    row_headers: list[Text] = Field(default_factory=list, max_length=30)
    column_headers: list[Text] = Field(default_factory=list, max_length=30)
    cells: list[TableCell] = Field(default_factory=list, max_length=120)

    @field_validator("title", mode="before")
    @classmethod
    def concise_title(cls, value: object) -> object:
        return value.strip()[:120] if isinstance(value, str) else value

    @model_validator(mode="after")
    def references_are_valid(self) -> Self:
        for labels in (self.categories, self.row_headers, self.column_headers):
            unique(labels)
        unique([series.id for series in self.series])
        unique([series.name for series in self.series], "duplicate_series_name")
        unique([f"{cell.row}\0{cell.column}" for cell in self.cells], "duplicate_table_cell")
        if any(
            cell.row not in self.row_headers or cell.column not in self.column_headers
            for cell in self.cells
        ):
            raise PydanticCustomError("unknown_table_header", "Undeclared table header")
        if any(
            point.category not in self.categories
            for series in self.series
            for point in series.points
        ):
            raise PydanticCustomError("unknown_chart_category", "Undeclared chart category")
        if self.kind == "table" and self.series:
            raise PydanticCustomError("table_series_forbidden", "Tables must use cells")
        if self.kind != "table" and self.cells:
            raise PydanticCustomError("chart_cells_forbidden", "Charts must use series")
        return self


class ChartTableVisualReference(VisualBase):
    visual_family: Literal["chart_table"]
    components: list[ChartComponent] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def unique_components(self) -> Self:
        unique([component.id for component in self.components])
        return self


class Entity(VisualModel):
    id: Identifier
    label: Text


class Edge(VisualModel):
    source: Identifier
    target: Identifier
    label: str | None = Field(default=None, max_length=120)


def validate_edges(entities: list[Entity], edges: list[Edge]) -> None:
    unique([entity.id for entity in entities])
    allowed = {entity.id for entity in entities}
    if any(edge.source not in allowed or edge.target not in allowed for edge in edges):
        raise ValueError("Unknown relation endpoint")


class ProcessVisualReference(VisualBase):
    visual_family: Literal["process"]
    process_kind: Literal["linear", "cyclic", "branched", "unknown"]
    stages: list[Entity] = Field(max_length=24)
    edges: list[Edge] = Field(max_length=40)
    starts: list[Identifier] = Field(default_factory=list, max_length=8)
    ends: list[Identifier] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def valid_graph(self) -> Self:
        validate_edges(self.stages, self.edges)
        if not set(self.starts + self.ends) <= {stage.id for stage in self.stages}:
            raise ValueError("Unknown process boundary")
        return self


Location = Literal[
    "north",
    "south",
    "east",
    "west",
    "northeast",
    "northwest",
    "southeast",
    "southwest",
    "centre",
    "unspecified",
]


class MapFeature(Entity):
    location: Location = "unspecified"


class MapState(VisualModel):
    id: Identifier
    label: Text
    features: list[MapFeature] = Field(max_length=24)

    @model_validator(mode="after")
    def unique_features(self) -> Self:
        unique([feature.id for feature in self.features])
        return self


class MapChange(VisualModel):
    kind: Literal["addition", "removal", "replacement", "relocation", "expansion", "unchanged"]
    from_state: Identifier
    to_state: Identifier
    before: Identifier | None = None
    after: Identifier | None = None
    location: Location = "unspecified"


class MapVisualReference(VisualBase):
    visual_family: Literal["map"]
    states: list[MapState] = Field(min_length=1, max_length=4)
    changes: list[MapChange] = Field(max_length=24)

    @model_validator(mode="after")
    def valid_changes(self) -> Self:
        unique([state.id for state in self.states])
        states = {state.id: {feature.id for feature in state.features} for state in self.states}
        for change in self.changes:
            if change.from_state not in states or change.to_state not in states:
                raise ValueError("Unknown map state")
            if change.before is not None and change.before not in states[change.from_state]:
                raise ValueError("Unknown original feature")
            if change.after is not None and change.after not in states[change.to_state]:
                raise ValueError("Unknown resulting feature")
            required = {"addition": (False, True), "removal": (True, False)}.get(
                change.kind, (True, True)
            )
            if (required[0] and change.before is None) or (required[1] and change.after is None):
                raise ValueError("Missing map change endpoints")
        return self


class SystemVisualReference(VisualBase):
    visual_family: Literal["system"]
    components: list[Entity] = Field(max_length=24)
    connections: list[Edge] = Field(max_length=40)
    inputs: list[Identifier] = Field(default_factory=list, max_length=8)
    outputs: list[Identifier] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def valid_system(self) -> Self:
        validate_edges(self.components, self.connections)
        if not set(self.inputs + self.outputs) <= {item.id for item in self.components}:
            raise ValueError("Unknown system boundary")
        return self


class OtherVisualReference(VisualBase):
    visual_family: Literal["other"]
    entities: list[Entity] = Field(max_length=24)
    relationships: list[Edge] = Field(max_length=30)
    observations: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=8)

    @model_validator(mode="after")
    def valid_relations(self) -> Self:
        validate_edges(self.entities, self.relationships)
        return self


VisualReference = Annotated[
    ChartTableVisualReference
    | ProcessVisualReference
    | MapVisualReference
    | SystemVisualReference
    | OtherVisualReference,
    Field(discriminator="visual_family"),
]


class VisualGroundingOutput(VisualModel):
    reference: VisualReference
