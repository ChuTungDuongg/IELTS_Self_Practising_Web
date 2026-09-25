"""IELTS display-number slots consumed by one persisted response."""

from collections.abc import Iterable
from typing import Any


def question_span(question_type: str, config: dict[str, Any]) -> int:
    if question_type != "multiple_choice_multiple":
        return 1
    required = config.get("min_selections")
    maximum = config.get("max_selections")
    if isinstance(required, int) and not isinstance(required, bool) and required > 0 and required == maximum:
        return required
    return 1  # The registry reports malformed or inexact configurations separately.


def question_slots(question_type: str, number: int, config: dict[str, Any]) -> range:
    return range(number, number + question_span(question_type, config))


def group_slots(question_type: str, questions: Iterable[Any]) -> list[int]:
    return [slot for question in questions for slot in question_slots(question_type, question.number, question.config)]
