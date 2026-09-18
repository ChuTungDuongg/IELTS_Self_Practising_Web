import pytest
from pydantic import ValidationError

from app.domains.questions.registry import normalize_text, question_registry


def test_text_evaluation_normalizes_case_and_whitespace() -> None:
    key = {"type": "text", "accepted": ["solar power", "solar energy"], "case_sensitive": False}
    assert question_registry.evaluate(
        "text_completion", key, " Solar    Power ", {"max_words": 2, "max_numbers": 0}
    )


def test_text_evaluation_does_not_correct_spelling() -> None:
    key = {"type": "text", "accepted": ["solar power"], "case_sensitive": False}
    assert not question_registry.evaluate("text_completion", key, "soler power", {})


def test_choice_and_matching_evaluation() -> None:
    assert question_registry.evaluate(
        "multiple_choice",
        {"type": "single_choice", "accepted": ["B"]},
        "B",
        {"options": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}]},
    )
    assert question_registry.evaluate(
        "matching_headings",
        {"type": "single_choice", "accepted": ["iv"]},
        "iv",
        {"target_label": "Paragraph A"},
    )


def test_registry_validates_question_configuration() -> None:
    with pytest.raises(ValidationError):
        question_registry.validate(
            "multiple_choice",
            {},
            {"options": [{"id": "A", "label": "Only one"}]},
            {"type": "single_choice", "accepted": ["A"]},
        )


def test_normalize_text_can_remain_case_sensitive() -> None:
    assert normalize_text(" A   B ", case_sensitive=True) == "A B"


def test_text_limits_are_enforced_without_changing_the_answer() -> None:
    key = {"type": "text", "accepted": ["the solar power"], "case_sensitive": False}
    assert not question_registry.evaluate(
        "text_completion", key, "the solar power", {"max_words": 2}
    )


def test_number_limit_is_enforced() -> None:
    key = {"type": "text", "accepted": ["12 and 14"], "case_sensitive": False}
    assert not question_registry.evaluate(
        "text_completion", key, "12 and 14", {"max_words": 1, "max_numbers": 1}
    )


@pytest.mark.parametrize("value", ["TRUE", "FALSE", "NOT_GIVEN"])
def test_true_false_not_given_values(value: str) -> None:
    assert question_registry.evaluate(
        "true_false_not_given",
        {"type": "single_choice", "accepted": [value]},
        value,
        {},
    )
    different = "FALSE" if value != "FALSE" else "NOT_GIVEN"
    assert not question_registry.evaluate(
        "true_false_not_given",
        {"type": "single_choice", "accepted": [value]},
        different,
        {},
    )
