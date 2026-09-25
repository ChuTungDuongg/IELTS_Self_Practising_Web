from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator


class EmptyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Option(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_option(cls, value: Any) -> Any:
        if isinstance(value, dict) and "text" not in value:
            try:
                uuid.UUID(str(value.get("id")))
            except ValueError:
                return {
                    "id": value.get("id"),
                    "label": value.get("id"),
                    "text": value.get("label"),
                }
        return value


class MultipleChoiceConfig(BaseModel):
    options: list[Option] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_options(self) -> MultipleChoiceConfig:
        _validate_option_identity(self.options)
        return self


class MultipleChoiceMultipleConfig(MultipleChoiceConfig):
    min_selections: int = Field(default=2, ge=1, le=10)
    max_selections: int = Field(default=2, ge=1, le=10)

    @model_validator(mode="after")
    def validate_selection_range(self) -> MultipleChoiceMultipleConfig:
        if self.min_selections != self.max_selections:
            raise ValueError("IELTS multiple-choice groups require an exact selection count")
        if self.max_selections > len(self.options):
            raise ValueError("Maximum selections cannot exceed the option count")
        return self


class TextCompletionConfig(BaseModel):
    max_words: int | None = Field(default=None, ge=1, le=20)
    max_numbers: int | None = Field(default=None, ge=0, le=20)


class TextCompletionSegment(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["TEXT", "GAP"]
    text: str = Field(default="", max_length=10_000)
    question_id: str | None = Field(default=None, max_length=80)

    @field_validator("id", "question_id")
    @classmethod
    def validate_uuid_identity(cls, value: str | None) -> str | None:
        if value is not None:
            uuid.UUID(value)
        return value

    @model_validator(mode="after")
    def validate_segment(self) -> TextCompletionSegment:
        if self.type == "GAP" and not self.question_id:
            raise ValueError("Text completion gaps must reference a question")
        if self.type == "TEXT" and self.question_id is not None:
            raise ValueError("Text segments cannot reference a question")
        return self


class TextCompletionBlock(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    segments: list[TextCompletionSegment] = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def validate_uuid_identity(cls, value: str) -> str:
        uuid.UUID(value)
        return value


class TextCompletionGroupConfig(BaseModel):
    mode: Literal["SENTENCE", "PASSAGE"] = "SENTENCE"
    blocks: list[TextCompletionBlock] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> TextCompletionGroupConfig:
        block_ids = [block.id for block in self.blocks]
        segment_ids = [segment.id for block in self.blocks for segment in block.segments]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("Text completion block IDs must be unique")
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("Text completion segment IDs must be unique")
        gap_ids = [
            segment.question_id
            for block in self.blocks
            for segment in block.segments
            if segment.type == "GAP"
        ]
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("Each text completion question may be referenced by only one gap")
        return self


class MatchingHeadingsGroupConfig(BaseModel):
    options: list[Option] = Field(min_length=2)
    allow_option_reuse: bool = False

    @model_validator(mode="after")
    def validate_options(self) -> MatchingHeadingsGroupConfig:
        _validate_option_identity(self.options)
        return self


class MatchingGroupConfig(MatchingHeadingsGroupConfig):
    pass


class MatchingInformationGroupConfig(BaseModel):
    allow_option_reuse: bool = True


class WordListCompletionGroupConfig(TextCompletionGroupConfig):
    options: list[Option] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_options(self) -> WordListCompletionGroupConfig:
        _validate_option_identity(self.options)
        return self


class VisualMarker(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    question_id: str = Field(min_length=1, max_length=80)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class VisualLabellingGroupConfig(BaseModel):
    options: list[Option] = Field(min_length=2)
    markers: list[VisualMarker] | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> VisualLabellingGroupConfig:
        _validate_option_identity(self.options)
        if self.markers is None:
            return self
        marker_ids = [marker.id for marker in self.markers]
        if len(marker_ids) != len(set(marker_ids)):
            raise ValueError("Marker IDs must be unique")
        question_ids = [marker.question_id for marker in self.markers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Each visual question must have exactly one marker")
        return self


class DiagramBoxGeometry(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=0.12, le=0.8)

    @model_validator(mode="after")
    def validate_horizontal_bounds(self) -> DiagramBoxGeometry:
        if self.x + self.width > 1:
            raise ValueError("Diagram label boxes must remain inside the canvas")
        return self


class DiagramArrowGeometry(BaseModel):
    start_x: float = Field(ge=0, le=1)
    start_y: float = Field(ge=0, le=1)
    end_x: float = Field(ge=0, le=1)
    end_y: float = Field(ge=0, le=1)


class DiagramCanvasItem(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    question_id: str = Field(min_length=1, max_length=80)
    box: DiagramBoxGeometry
    arrow: DiagramArrowGeometry

    @field_validator("id", "question_id")
    @classmethod
    def validate_uuid_identity(cls, value: str) -> str:
        uuid.UUID(value)
        return value


class DiagramLabellingGroupConfig(BaseModel):
    items: list[DiagramCanvasItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> DiagramLabellingGroupConfig:
        item_ids = [item.id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Diagram item IDs must be unique")
        question_ids = [item.question_id for item in self.items]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Each diagram question must have exactly one canvas item")
        return self


class TableCellSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    type: Literal["TEXT", "GAP"]
    text: str | None = Field(default=None, max_length=10_000)
    question_id: str | None = Field(default=None, max_length=80)

    @field_validator("id", "question_id")
    @classmethod
    def validate_uuid_identity(cls, value: str | None) -> str | None:
        if value is not None:
            uuid.UUID(value)
        return value

    @model_validator(mode="after")
    def validate_segment(self) -> TableCellSegment:
        if self.type == "GAP":
            if not self.question_id:
                raise ValueError("Table gap segments must reference a question")
            if self.text is not None:
                raise ValueError("Table gap segments cannot contain text")
        else:
            if self.text is None:
                raise ValueError("Table text segments require text, which may be empty")
            if self.question_id is not None:
                raise ValueError("Table text segments cannot reference a question")
        return self


class LayoutColumn(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=200)

    @field_validator("id")
    @classmethod
    def validate_uuid_identity(cls, value: str) -> str:
        uuid.UUID(value)
        return value


class TableCell(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    segments: list[TableCellSegment] = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def validate_uuid_identity(cls, value: str) -> str:
        uuid.UUID(value)
        return value


class TableRow(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    cells: list[TableCell] = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def validate_uuid_identity(cls, value: str) -> str:
        uuid.UUID(value)
        return value


class NoteSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    type: Literal["TEXT", "GAP"]
    text: str | None = Field(default=None, max_length=10_000)
    question_id: str | None = Field(default=None, max_length=80)

    @field_validator("id", "question_id")
    @classmethod
    def validate_uuid_identity(cls, value: str | None) -> str | None:
        if value is not None:
            uuid.UUID(value)
        return value

    @model_validator(mode="after")
    def validate_segment(self) -> NoteSegment:
        if self.type == "GAP":
            if not self.question_id:
                raise ValueError("Note gap segments must reference a question")
            if self.text is not None:
                raise ValueError("Note gap segments cannot contain text")
        else:
            if self.text is None:
                raise ValueError("Note text segments require text, which may be empty")
            if self.question_id is not None:
                raise ValueError("Note text segments cannot reference a question")
        return self


class NoteBlock(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    style: Literal["HEADING", "TEXT", "BULLET", "EXAMPLE"]
    indent: int = Field(default=0, ge=0, le=3)
    segments: list[NoteSegment] = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def validate_uuid_identity(cls, value: str) -> str:
        uuid.UUID(value)
        return value

    @model_validator(mode="after")
    def validate_content(self) -> NoteBlock:
        if not any(
            segment.type == "GAP" or bool((segment.text or "").strip()) for segment in self.segments
        ):
            raise ValueError("Persisted note blocks cannot be empty")
        segment_ids = [segment.id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("Note segment IDs must be unique")
        return self


class LayoutNode(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["TEXT", "GAP"]
    text: str = Field(default="", max_length=2000)
    question_id: str | None = Field(default=None, max_length=80)
    level: int = Field(default=0, ge=0, le=4)

    @model_validator(mode="after")
    def validate_node(self) -> LayoutNode:
        if self.type == "GAP" and not self.question_id:
            raise ValueError("Gap nodes must reference a question")
        if self.type == "TEXT" and not self.text.strip():
            raise ValueError("Text nodes cannot be empty")
        return self


class StructuredLayout(BaseModel):
    kind: Literal["FORM", "NOTE", "TABLE", "FLOW_CHART", "SUMMARY", "SENTENCE"]
    title: str | None = Field(default=None, max_length=300)
    columns: list[LayoutColumn] = Field(default_factory=list)
    rows: list[TableRow] = Field(default_factory=list)
    nodes: list[LayoutNode] = Field(default_factory=list)
    blocks: list[NoteBlock] = Field(default_factory=list)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value).strip()

    @model_validator(mode="after")
    def validate_shape(self) -> StructuredLayout:
        if self.kind == "TABLE":
            if not self.columns or not self.rows:
                raise ValueError("Table layouts require columns and rows")
            if any(len(row.cells) != len(self.columns) for row in self.rows):
                raise ValueError("Every table row must match the column count")
            column_ids = [column.id for column in self.columns]
            row_ids = [row.id for row in self.rows]
            cell_ids = [cell.id for row in self.rows for cell in row.cells]
            segment_ids = [
                segment.id for row in self.rows for cell in row.cells for segment in cell.segments
            ]
            gap_ids = [
                segment.question_id
                for row in self.rows
                for cell in row.cells
                for segment in cell.segments
                if segment.type == "GAP"
            ]
            for label, identities in (
                ("column", column_ids),
                ("row", row_ids),
                ("cell", cell_ids),
                ("segment", segment_ids),
            ):
                if len(identities) != len(set(identities)):
                    raise ValueError(f"Table {label} IDs must be unique")
            if len(gap_ids) != len(set(gap_ids)):
                raise ValueError("Each table question may be referenced by only one gap")
            if self.nodes:
                raise ValueError("Table layouts cannot contain completion nodes")
        elif self.kind == "NOTE" and self.blocks:
            block_ids = [block.id for block in self.blocks]
            segment_ids = [segment.id for block in self.blocks for segment in block.segments]
            gap_ids = [
                segment.question_id
                for block in self.blocks
                for segment in block.segments
                if segment.type == "GAP"
            ]
            if len(block_ids) != len(set(block_ids)):
                raise ValueError("Note block IDs must be unique")
            if len(segment_ids) != len(set(segment_ids)):
                raise ValueError("Note segment IDs must be unique")
            if len(gap_ids) != len(set(gap_ids)):
                raise ValueError("Each note question must be referenced by exactly one gap")
            if self.nodes:
                raise ValueError("Modern note layouts cannot contain legacy completion nodes")
        elif not self.nodes:
            raise ValueError("This completion layout requires at least one node")
        return self


class StructuredCompletionGroupConfig(BaseModel):
    layout: StructuredLayout


class MatchingTargetConfig(BaseModel):
    target_block_id: str = Field(min_length=1, max_length=80)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_target(cls, value: Any) -> Any:
        if isinstance(value, dict) and "target_block_id" not in value:
            return {"target_block_id": value.get("target_label")}
        return value


class SingleOptionAnswerKey(BaseModel):
    kind: Literal["SINGLE_OPTION"] = "SINGLE_OPTION"
    value: str = Field(min_length=1, max_length=80)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_key(cls, value: Any) -> Any:
        if isinstance(value, dict) and "value" not in value:
            accepted = value.get("accepted")
            return {
                "kind": "SINGLE_OPTION",
                "value": accepted[0] if isinstance(accepted, list) and accepted else "",
            }
        return value


class TrueFalseNotGivenAnswerKey(SingleOptionAnswerKey):
    value: Literal["TRUE", "FALSE", "NOT_GIVEN"]


class YesNoNotGivenAnswerKey(SingleOptionAnswerKey):
    value: Literal["YES", "NO", "NOT_GIVEN"]


class TextAnswerKey(BaseModel):
    kind: Literal["TEXT"] = "TEXT"
    accepted: list[str] = Field(min_length=1)
    case_sensitive: bool = False

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_key(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("kind") != "TEXT":
            return {**value, "kind": "TEXT"}
        return value

    @field_validator("accepted")
    @classmethod
    def normalize_accepted(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for candidate in value:
            trimmed = candidate.strip()
            if not trimmed:
                continue
            cleaned.append(trimmed)
        if not cleaned:
            raise ValueError("A primary accepted answer is required")
        return cleaned

    @model_validator(mode="after")
    def reject_duplicate_accepted(self) -> TextAnswerKey:
        normalized = [
            " ".join(candidate.split())
            if self.case_sensitive
            else " ".join(candidate.split()).casefold()
            for candidate in self.accepted
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Accepted answers must be unique after grading normalization")
        return self


class MultipleOptionsAnswerKey(BaseModel):
    kind: Literal["MULTIPLE_OPTIONS"] = "MULTIPLE_OPTIONS"
    values: list[str] = Field(min_length=1)
    order_matters: bool = False

    @field_validator("values")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Multiple option answer keys cannot contain duplicates")
        return value


class StringResponse(RootModel[str]):
    pass


class TrueFalseNotGivenResponse(RootModel[Literal["TRUE", "FALSE", "NOT_GIVEN"]]):
    pass


class YesNoNotGivenResponse(RootModel[Literal["YES", "NO", "NOT_GIVEN"]]):
    pass


class StringListResponse(RootModel[list[str]]):
    @field_validator("root")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Responses cannot contain duplicate options")
        return value


def _validate_option_identity(options: list[Option]) -> None:
    ids = [item.id for item in options]
    if len(ids) != len(set(ids)):
        raise ValueError("Option IDs must be unique")
    labels = [item.label.casefold() for item in options]
    if len(labels) != len(set(labels)):
        raise ValueError("Option labels must be unique")


Evaluator = Callable[[BaseModel, Any, BaseModel], bool]


class RegisteredQuestionType:
    def __init__(
        self,
        *,
        group_config_model: type[BaseModel],
        question_config_model: type[BaseModel],
        response_model: type[BaseModel],
        answer_key_model: type[BaseModel],
        evaluator: Evaluator,
    ) -> None:
        self.group_config_model = group_config_model
        self.question_config_model = question_config_model
        self.response_model = response_model
        self.answer_key_model = answer_key_model
        self._evaluator = evaluator

    def evaluate(self, answer_key: BaseModel, value: Any, config: BaseModel) -> bool:
        return self._evaluator(answer_key, value, config)


def _choice_evaluator(key: BaseModel, value: Any, _: BaseModel) -> bool:
    parsed = SingleOptionAnswerKey.model_validate(key)
    return isinstance(value, str) and value == parsed.value


def _multiple_choice_evaluator(key: BaseModel, value: Any, _: BaseModel) -> bool:
    parsed = MultipleOptionsAnswerKey.model_validate(key)
    if not isinstance(value, list):
        return False
    return set(value) == set(parsed.values)


def normalize_text(value: str, *, case_sensitive: bool) -> str:
    normalized = " ".join(value.strip().split())
    return normalized if case_sensitive else normalized.casefold()


def _text_evaluator(key: BaseModel, value: Any, config: BaseModel) -> bool:
    parsed_key = TextAnswerKey.model_validate(key)
    parsed_config = TextCompletionConfig.model_validate(config)
    if not isinstance(value, str):
        return False
    word_count = len(re.findall(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", value, re.UNICODE))
    number_count = len(re.findall(r"(?<!\w)[+-]?(?:\d+(?:[.,]\d+)?)(?!\w)", value))
    if parsed_config.max_words is not None and word_count > parsed_config.max_words:
        return False
    if parsed_config.max_numbers is not None and number_count > parsed_config.max_numbers:
        return False
    answer = normalize_text(value, case_sensitive=parsed_key.case_sensitive)
    accepted = {
        normalize_text(candidate, case_sensitive=parsed_key.case_sensitive)
        for candidate in parsed_key.accepted
    }
    return answer in accepted


class QuestionRegistry:
    def __init__(self) -> None:
        self._types: dict[str, RegisteredQuestionType] = {}

    def register(self, name: str, definition: RegisteredQuestionType) -> None:
        if name in self._types:
            raise ValueError(f"Question type {name!r} is already registered")
        self._types[name] = definition

    def names(self) -> tuple[str, ...]:
        return tuple(self._types)

    def validate_group(self, name: str, config: dict[str, Any]) -> BaseModel:
        return self._types[name].group_config_model.model_validate(config)

    def validate_structure(
        self, name: str, group_config: dict[str, Any], question_config: dict[str, Any]
    ) -> None:
        definition = self._types[name]
        definition.group_config_model.model_validate(group_config)
        definition.question_config_model.model_validate(question_config)

    def validate_draft(
        self,
        name: str,
        group_config: dict[str, Any],
        question_config: dict[str, Any],
        answer_key: dict[str, Any],
    ) -> None:
        """Check draft persistence shape without requiring a complete grading key."""
        self.validate_structure(name, group_config, question_config)
        model = self._types[name].answer_key_model
        if model is MultipleOptionsAnswerKey:
            values = answer_key.get("values")
            if (
                answer_key.get("kind") != "MULTIPLE_OPTIONS"
                or not isinstance(values, list)
                or any(not isinstance(value, str) for value in values)
                or len(values) != len(set(values))
                or answer_key.get("order_matters") is not False
            ):
                raise ValueError("Multi-select draft keys must contain distinct unordered options")
        elif model is TextAnswerKey:
            accepted = answer_key.get("accepted")
            if (
                answer_key.get("kind") != "TEXT"
                or not isinstance(accepted, list)
                or any(not isinstance(value, str) for value in accepted)
                or not isinstance(answer_key.get("case_sensitive"), bool)
            ):
                raise ValueError("Text draft keys must contain a text answer list")
        else:
            value = answer_key.get("value")
            if (
                answer_key.get("kind") != "SINGLE_OPTION"
                or not isinstance(value, str)
                or len(value) > 80
            ):
                raise ValueError("Single-option draft keys must contain a text value")

    def validate(
        self,
        name: str,
        group_config: dict[str, Any],
        question_config: dict[str, Any],
        answer_key: dict[str, Any],
    ) -> None:
        definition = self._types[name]
        definition.group_config_model.model_validate(group_config)
        definition.question_config_model.model_validate(question_config)
        parsed_key = definition.answer_key_model.model_validate(answer_key)
        if name == "multiple_choice_multiple" and parsed_key.order_matters:
            raise ValueError("IELTS multiple-choice answers are unordered")

    def validate_response(
        self, name: str, value: Any, config: dict[str, Any] | None = None
    ) -> Any:
        parsed = self._types[name].response_model.model_validate(value).root
        if name == "multiple_choice_multiple" and config is not None:
            parsed_config = MultipleChoiceMultipleConfig.model_validate(config)
            option_ids = {option.id for option in parsed_config.options}
            if (
                len(parsed) != len(set(parsed))
                or len(parsed) > parsed_config.max_selections
                or not set(parsed).issubset(option_ids)
            ):
                raise ValueError("Select distinct available options within the selection limit")
        return parsed

    def score(self, name: str, answer_key: dict[str, Any], value: Any, config: dict[str, Any]) -> int:
        if name == "multiple_choice_multiple":
            key = MultipleOptionsAnswerKey.model_validate(answer_key)
            MultipleChoiceMultipleConfig.model_validate(config)
            if not isinstance(value, list):
                return 0
            return len(set(value).intersection(key.values))
        return int(self.evaluate(name, answer_key, value, config))

    def evaluate(
        self, name: str, answer_key: dict[str, Any], value: Any, config: dict[str, Any]
    ) -> bool:
        definition = self._types[name]
        parsed_key = definition.answer_key_model.model_validate(answer_key)
        parsed_config = definition.question_config_model.model_validate(config)
        parsed_value = definition.response_model.model_validate(value).root
        return definition.evaluate(parsed_key, parsed_value, parsed_config)

    def supports(self, name: str) -> bool:
        return name in self._types


question_registry = QuestionRegistry()
question_registry.register(
    "multiple_choice",
    RegisteredQuestionType(
        group_config_model=EmptyConfig,
        question_config_model=MultipleChoiceConfig,
        response_model=StringResponse,
        answer_key_model=SingleOptionAnswerKey,
        evaluator=_choice_evaluator,
    ),
)
question_registry.register(
    "true_false_not_given",
    RegisteredQuestionType(
        group_config_model=EmptyConfig,
        question_config_model=EmptyConfig,
        response_model=TrueFalseNotGivenResponse,
        answer_key_model=TrueFalseNotGivenAnswerKey,
        evaluator=_choice_evaluator,
    ),
)
question_registry.register(
    "yes_no_not_given",
    RegisteredQuestionType(
        group_config_model=EmptyConfig,
        question_config_model=EmptyConfig,
        response_model=YesNoNotGivenResponse,
        answer_key_model=YesNoNotGivenAnswerKey,
        evaluator=_choice_evaluator,
    ),
)
question_registry.register(
    "text_completion",
    RegisteredQuestionType(
        group_config_model=TextCompletionGroupConfig,
        question_config_model=TextCompletionConfig,
        response_model=StringResponse,
        answer_key_model=TextAnswerKey,
        evaluator=_text_evaluator,
    ),
)
question_registry.register(
    "matching_headings",
    RegisteredQuestionType(
        group_config_model=MatchingHeadingsGroupConfig,
        question_config_model=MatchingTargetConfig,
        response_model=StringResponse,
        answer_key_model=SingleOptionAnswerKey,
        evaluator=_choice_evaluator,
    ),
)

question_registry.register(
    "multiple_choice_multiple",
    RegisteredQuestionType(
        group_config_model=EmptyConfig,
        question_config_model=MultipleChoiceMultipleConfig,
        response_model=StringListResponse,
        answer_key_model=MultipleOptionsAnswerKey,
        evaluator=_multiple_choice_evaluator,
    ),
)
question_registry.register(
    "matching",
    RegisteredQuestionType(
        group_config_model=MatchingGroupConfig,
        question_config_model=EmptyConfig,
        response_model=StringResponse,
        answer_key_model=SingleOptionAnswerKey,
        evaluator=_choice_evaluator,
    ),
)

question_registry.register(
    "matching_information",
    RegisteredQuestionType(
        group_config_model=MatchingInformationGroupConfig,
        question_config_model=EmptyConfig,
        response_model=StringResponse,
        answer_key_model=SingleOptionAnswerKey,
        evaluator=_choice_evaluator,
    ),
)

for matching_type in ("matching_features", "matching_sentence_endings"):
    question_registry.register(
        matching_type,
        RegisteredQuestionType(
            group_config_model=MatchingGroupConfig,
            question_config_model=EmptyConfig,
            response_model=StringResponse,
            answer_key_model=SingleOptionAnswerKey,
            evaluator=_choice_evaluator,
        ),
    )

question_registry.register(
    "summary_completion_word_list",
    RegisteredQuestionType(
        group_config_model=WordListCompletionGroupConfig,
        question_config_model=EmptyConfig,
        response_model=StringResponse,
        answer_key_model=SingleOptionAnswerKey,
        evaluator=_choice_evaluator,
    ),
)

for visual_type in ("plan_labelling", "map_labelling"):
    question_registry.register(
        visual_type,
        RegisteredQuestionType(
            group_config_model=VisualLabellingGroupConfig,
            question_config_model=EmptyConfig,
            response_model=StringResponse,
            answer_key_model=SingleOptionAnswerKey,
            evaluator=_choice_evaluator,
        ),
    )

question_registry.register(
    "diagram_labelling",
    RegisteredQuestionType(
        group_config_model=DiagramLabellingGroupConfig,
        question_config_model=TextCompletionConfig,
        response_model=StringResponse,
        answer_key_model=TextAnswerKey,
        evaluator=_text_evaluator,
    ),
)

for completion_type in (
    "form_completion",
    "note_completion",
    "table_completion",
    "flow_chart_completion",
    "summary_completion",
    "sentence_completion",
):
    question_registry.register(
        completion_type,
        RegisteredQuestionType(
            group_config_model=StructuredCompletionGroupConfig,
            question_config_model=TextCompletionConfig,
            response_model=StringResponse,
            answer_key_model=TextAnswerKey,
            evaluator=_text_evaluator,
        ),
    )

question_registry.register(
    "short_answer",
    RegisteredQuestionType(
        group_config_model=EmptyConfig,
        question_config_model=TextCompletionConfig,
        response_model=StringResponse,
        answer_key_model=TextAnswerKey,
        evaluator=_text_evaluator,
    ),
)
