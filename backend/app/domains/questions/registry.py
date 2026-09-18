from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel


class EmptyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Option(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=500)


class MultipleChoiceConfig(BaseModel):
    options: list[Option] = Field(min_length=2)


class TextCompletionConfig(BaseModel):
    max_words: int | None = Field(default=None, ge=1, le=20)
    max_numbers: int | None = Field(default=None, ge=0, le=20)


class MatchingHeadingsGroupConfig(BaseModel):
    options: list[Option] = Field(min_length=2)
    allow_option_reuse: bool = False


class MatchingTargetConfig(BaseModel):
    target_label: str = Field(min_length=1, max_length=80)


class ChoiceAnswerKey(BaseModel):
    type: str = "single_choice"
    accepted: list[str] = Field(min_length=1, max_length=1)


class TextAnswerKey(BaseModel):
    type: str = "text"
    accepted: list[str] = Field(min_length=1)
    case_sensitive: bool = False


class StringResponse(RootModel[str]):
    pass


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
    parsed = ChoiceAnswerKey.model_validate(key)
    return isinstance(value, str) and value == parsed.accepted[0]


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
        definition.answer_key_model.model_validate(answer_key)

    def validate_response(self, name: str, value: Any) -> Any:
        return self._types[name].response_model.model_validate(value).root

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
        answer_key_model=ChoiceAnswerKey,
        evaluator=_choice_evaluator,
    ),
)
question_registry.register(
    "true_false_not_given",
    RegisteredQuestionType(
        group_config_model=EmptyConfig,
        question_config_model=EmptyConfig,
        response_model=StringResponse,
        answer_key_model=ChoiceAnswerKey,
        evaluator=_choice_evaluator,
    ),
)
question_registry.register(
    "text_completion",
    RegisteredQuestionType(
        group_config_model=EmptyConfig,
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
        answer_key_model=ChoiceAnswerKey,
        evaluator=_choice_evaluator,
    ),
)
