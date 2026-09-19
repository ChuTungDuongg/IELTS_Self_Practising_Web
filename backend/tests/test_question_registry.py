from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domains.questions.normalization import (
    normalize_passage_blocks,
    normalize_question_group_payload,
    normalize_response_value,
)
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


def test_legacy_matching_headings_normalizes_to_stable_ids() -> None:
    passage_id = uuid4()
    block_id = uuid4()
    blocks = normalize_passage_blocks(
        [{"id": str(block_id), "type": "paragraph", "text": "Fictional text"}], passage_id
    )
    config, questions = normalize_question_group_payload(
        question_type="matching_headings",
        group_config={
            "options": [
                {"id": "i", "label": "First heading"},
                {"id": "ii", "label": "Second heading"},
            ],
            "allow_option_reuse": False,
        },
        questions=[
            {
                "number": 1,
                "prompt": "Paragraph A",
                "config": {"target_label": "Paragraph A"},
                "answer_key": {"type": "single_choice", "accepted": ["ii"]},
                "order_index": 0,
            }
        ],
        group_id=uuid4(),
        passage_blocks=blocks,
    )
    assert config["options"][0]["label"] == "i"
    assert config["options"][0]["text"] == "First heading"
    assert questions[0]["config"]["target_block_id"] == str(block_id)
    assert questions[0]["answer_key"]["value"] == config["options"][1]["id"]
    submitted_value = normalize_response_value(
        question_type="matching_headings",
        value=config["options"][1]["id"],
        raw_group_config={
            "options": [
                {"id": "i", "label": "First heading"},
                {"id": "ii", "label": "Second heading"},
            ]
        },
        raw_question_config={"target_label": "Paragraph A"},
        normalized_group_config=config,
        normalized_question_config=questions[0]["config"],
    )
    assert question_registry.evaluate(
        "matching_headings",
        questions[0]["answer_key"],
        submitted_value,
        questions[0]["config"],
    )
    repeated_config, repeated = normalize_question_group_payload(
        question_type="matching_headings",
        group_config=config,
        questions=questions,
        group_id=uuid4(),
        passage_blocks=blocks,
    )
    assert repeated_config["options"] == config["options"]
    assert repeated[0]["answer_key"] == questions[0]["answer_key"]


def test_changing_paragraph_label_preserves_block_identity_and_mapping() -> None:
    passage_id = uuid4()
    block_id = uuid4()
    blocks = normalize_passage_blocks(
        [{"id": str(block_id), "type": "paragraph", "label": "A", "text": "Text"}],
        passage_id,
    )
    relabelled = normalize_passage_blocks(
        [{**blocks[0], "label": "B", "text": "Edited text"}], passage_id
    )
    assert relabelled[0]["id"] == str(block_id)
    assert relabelled[0]["label"] == "B"
    assert relabelled[0]["text"] == "Edited text"


def test_matching_schema_rejects_duplicate_labels_and_empty_text() -> None:
    option_a = str(uuid4())
    option_b = str(uuid4())
    with pytest.raises(ValidationError):
        question_registry.validate_group(
            "matching_headings",
            {
                "options": [
                    {"id": option_a, "label": "i", "text": "First"},
                    {"id": option_b, "label": "i", "text": "Second"},
                ]
            },
        )
    with pytest.raises(ValidationError):
        question_registry.validate_group(
            "matching_headings",
            {
                "options": [
                    {"id": option_a, "label": "i", "text": ""},
                    {"id": option_b, "label": "ii", "text": "Second"},
                ]
            },
        )


def test_modern_uuid_option_missing_text_is_not_guessed_as_legacy() -> None:
    with pytest.raises(ValidationError):
        question_registry.validate_group(
            "matching_headings",
            {
                "options": [
                    {"id": str(uuid4()), "label": "i"},
                    {"id": str(uuid4()), "label": "ii", "text": "Second"},
                ]
            },
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


@pytest.mark.parametrize("value", ["YES", "NO", "NOT_GIVEN"])
def test_yes_no_not_given_is_distinct_and_uses_canonical_values(value: str) -> None:
    assert question_registry.supports("yes_no_not_given")
    assert question_registry.evaluate(
        "yes_no_not_given",
        {"kind": "SINGLE_OPTION", "value": value},
        value,
        {},
    )
    assert not question_registry.evaluate(
        "yes_no_not_given",
        {"kind": "SINGLE_OPTION", "value": value},
        "YES" if value != "YES" else "NO",
        {},
    )


def test_yes_no_not_given_normalizes_visible_not_given_value() -> None:
    normalized = normalize_response_value(
        question_type="yes_no_not_given",
        value="not given",
        raw_group_config={},
        raw_question_config={},
        normalized_group_config={},
        normalized_question_config={},
    )
    assert normalized == "NOT_GIVEN"
