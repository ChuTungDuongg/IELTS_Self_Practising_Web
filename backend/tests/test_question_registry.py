from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.domains.questions.normalization import (
    normalize_passage_blocks,
    normalize_question_group_payload,
    normalize_response_value,
    remap_question_references,
)
from app.domains.questions.registry import TextAnswerKey, normalize_text, question_registry
from app.models.enums import ModuleType
from app.schemas.content import QuestionGroupWrite
from app.services.reading import ReadingService


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


def test_reading_matching_aliases_and_word_list_use_stable_option_ids() -> None:
    option_a = str(uuid4())
    option_b = str(uuid4())
    options = [
        {"id": option_a, "label": "A", "text": "First"},
        {"id": option_b, "label": "B", "text": "Second"},
    ]
    for question_type in ("matching_features", "matching_sentence_endings"):
        question_registry.validate(
            question_type,
            {"options": options, "allow_option_reuse": True},
            {},
            {"kind": "SINGLE_OPTION", "value": option_b},
        )
        assert question_registry.evaluate(
            question_type, {"kind": "SINGLE_OPTION", "value": option_b}, option_b, {}
        )
    question_id = str(uuid4())
    question_registry.validate(
        "summary_completion_word_list",
        {
            "mode": "PASSAGE",
            "options": options,
            "blocks": [
                {
                    "id": str(uuid4()),
                    "segments": [
                        {"id": str(uuid4()), "type": "GAP", "question_id": question_id}
                    ],
                }
            ],
        },
        {},
        {"kind": "SINGLE_OPTION", "value": option_a},
    )
    assert not question_registry.evaluate(
        "summary_completion_word_list",
        {"kind": "SINGLE_OPTION", "value": option_a},
        option_b,
        {},
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


def test_legacy_text_completion_prompt_normalizes_to_structured_gap() -> None:
    question_id = uuid4()
    config, questions = normalize_question_group_payload(
        question_type="text_completion",
        group_config={},
        questions=[
            {
                "id": str(question_id),
                "number": 11,
                "prompt": "Tourism is the most important_______ in Greece.",
                "config": {"max_words": 3},
                "answer_key": {"kind": "TEXT", "accepted": ["source of income"]},
                "order_index": 0,
            }
        ],
        group_id=uuid4(),
        passage_blocks=[],
    )
    assert config["mode"] == "SENTENCE"
    assert [segment["type"] for segment in config["blocks"][0]["segments"]] == [
        "TEXT",
        "GAP",
        "TEXT",
    ]
    assert config["blocks"][0]["segments"][1]["question_id"] == str(question_id)
    assert questions[0]["id"] == str(question_id)
    assert questions[0]["answer_key"] == {
        "kind": "TEXT",
        "accepted": ["source of income"],
        "case_sensitive": False,
    }


def test_legacy_text_completion_without_marker_preserves_prompt_and_appends_gap() -> None:
    config, _ = normalize_question_group_payload(
        question_type="text_completion",
        group_config={},
        questions=[
            {
                "id": str(uuid4()),
                "number": 1,
                "prompt": "Complete this sentence.",
                "config": {},
                "answer_key": {"kind": "TEXT", "accepted": ["answer"]},
                "order_index": 0,
            }
        ],
        group_id=uuid4(),
        passage_blocks=[],
    )
    segments = config["blocks"][0]["segments"]
    assert segments[0]["text"] == "Complete this sentence."
    assert segments[-1]["type"] == "GAP"


def test_text_answer_key_trims_and_rejects_normalized_duplicates() -> None:
    parsed = TextAnswerKey.model_validate(
        {"kind": "TEXT", "accepted": [" source, income ", "alternative"]}
    )
    assert parsed.accepted == ["source, income", "alternative"]
    with pytest.raises(ValidationError):
        question_registry.validate(
            "text_completion",
            {
                "mode": "SENTENCE",
                "blocks": [
                    {
                        "id": str(uuid4()),
                        "segments": [
                            {"id": str(uuid4()), "type": "GAP", "question_id": str(uuid4())}
                        ],
                    }
                ],
            },
            {},
            {"kind": "TEXT", "accepted": ["Answer", " answer "]},
        )
    assert TextAnswerKey.model_validate(
        {"kind": "TEXT", "accepted": ["Answer", "answer"], "case_sensitive": True}
    ).accepted == ["Answer", "answer"]


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


def _diagram_config(question_id: str) -> dict:
    return {
        "items": [
            {
                "id": str(uuid4()),
                "question_id": question_id,
                "box": {"x": 0.08, "y": 0.12, "width": 0.3},
                "arrow": {
                    "start_x": 0.38,
                    "start_y": 0.18,
                    "end_x": 0.52,
                    "end_y": 0.47,
                },
            }
        ]
    }


def _diagram_body(*, prompt: str = "A pair of {{gap}} are lifted.", image: bool = True) -> QuestionGroupWrite:
    question_id = uuid4()
    return QuestionGroupWrite.model_validate(
        {
            "question_type": "diagram_labelling",
            "instruction": "",
            "config": _diagram_config(str(question_id)),
            "order_index": 0,
            "image_asset_id": str(uuid4()) if image else None,
            "questions": [
                {
                    "id": str(question_id),
                    "number": 20,
                    "prompt": prompt,
                    "config": {"max_words": 2, "max_numbers": 1},
                    "answer_key": {
                        "kind": "TEXT",
                        "accepted": ["gates"],
                        "case_sensitive": False,
                    },
                    "order_index": 0,
                }
            ],
        }
    )


def test_diagram_labelling_uses_text_config_key_and_evaluator() -> None:
    body = _diagram_body()
    ReadingService._validate_group_body(body, [])
    question = body.questions[0]
    assert question_registry.evaluate(
        "diagram_labelling", question.answer_key, " Gates ", question.config
    )
    assert not question_registry.evaluate(
        "diagram_labelling", question.answer_key, "locks", question.config
    )


def test_diagram_labelling_rejects_duplicate_or_missing_question_refs() -> None:
    body = _diagram_body()
    duplicate = body.model_copy(
        update={
            "config": {
                "items": [body.config["items"][0], {**body.config["items"][0], "id": str(uuid4())}]
            }
        }
    )
    with pytest.raises(AppError, match="exactly one"):
        ReadingService._validate_group_body(duplicate, [])
    missing = body.model_copy(update={"config": {"items": []}})
    with pytest.raises(AppError, match="at least 1 item"):
        ReadingService._validate_group_body(missing, [])


def test_diagram_labelling_rejects_invalid_geometry() -> None:
    body = _diagram_body()
    body.config["items"][0]["box"]["x"] = 0.9
    with pytest.raises(AppError, match="inside the canvas"):
        ReadingService._validate_group_body(body, [])


def test_diagram_labelling_requires_image_and_exactly_one_gap() -> None:
    with pytest.raises(AppError, match="require an image asset"):
        ReadingService._validate_group_body(_diagram_body(image=False), [])
    with pytest.raises(AppError, match="exactly one"):
        ReadingService._validate_group_body(_diagram_body(prompt="No answer gap here."), [])
    with pytest.raises(AppError, match="exactly one"):
        ReadingService._validate_group_body(
            _diagram_body(prompt="{{gap}} and another {{gap}}"), []
        )


def _table_completion_body() -> QuestionGroupWrite:
    question_id = str(uuid4())
    return QuestionGroupWrite.model_validate(
        {
            "question_type": "table_completion",
            "instruction": "Complete the table.",
            "config": {
                "layout": {
                    "kind": "TABLE",
                    "title": "GEO-ENGINEERING PROJECTS",
                    "columns": [
                        {"id": str(uuid4()), "label": "Procedure"},
                        {"id": str(uuid4()), "label": "Aim"},
                    ],
                    "rows": [
                        {
                            "id": str(uuid4()),
                            "cells": [
                                {
                                    "id": str(uuid4()),
                                    "segments": [
                                        {
                                            "id": str(uuid4()),
                                            "type": "TEXT",
                                            "text": "place material in the sea",
                                        }
                                    ],
                                },
                                {
                                    "id": str(uuid4()),
                                    "segments": [
                                        {
                                            "id": str(uuid4()),
                                            "type": "TEXT",
                                            "text": "to create a ",
                                        },
                                        {
                                            "id": str(uuid4()),
                                            "type": "GAP",
                                            "question_id": question_id,
                                        },
                                        {
                                            "id": str(uuid4()),
                                            "type": "TEXT",
                                            "text": " that reduces light",
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                    "nodes": [],
                }
            },
            "order_index": 0,
            "questions": [
                {
                    "id": question_id,
                    "number": 30,
                    "prompt": "Table gap",
                    "config": {"max_words": 1, "max_numbers": 0},
                    "answer_key": {
                        "kind": "TEXT",
                        "accepted": ["sunshade"],
                        "case_sensitive": False,
                    },
                    "order_index": 0,
                }
            ],
        }
    )


def test_table_completion_supports_title_mixed_segments_and_text_evaluation() -> None:
    body = _table_completion_body()
    ReadingService._validate_group_body(body, [])
    parsed = question_registry.validate_group("table_completion", body.config)

    assert parsed.layout.title == "GEO-ENGINEERING PROJECTS"
    assert [segment.type for segment in parsed.layout.rows[0].cells[1].segments] == [
        "TEXT",
        "GAP",
        "TEXT",
    ]
    assert question_registry.evaluate(
        "table_completion",
        body.questions[0].answer_key,
        " Sunshade ",
        body.questions[0].config,
    )


def test_legacy_table_cells_normalize_to_stable_segments_without_merging_rows() -> None:
    group_id = uuid4()
    question_id = str(uuid4())
    legacy = {
        "layout": {
            "kind": "TABLE",
            "title": "  Existing table  ",
            "columns": [
                {"id": "legacy-column-a", "label": "Item"},
                {"id": "legacy-column-b", "label": "Answer"},
            ],
            "rows": [
                {
                    "id": "fake-row-30",
                    "cells": [
                        {"id": "legacy-text", "type": "TEXT", "text": "Question 30"},
                        {
                            "id": "legacy-gap",
                            "type": "GAP",
                            "question_id": question_id,
                        },
                    ],
                },
                {
                    "id": "preserved-row",
                    "cells": [
                        {"id": "empty-a", "type": "TEXT", "text": "Another row"},
                        {"id": "empty-b", "type": "TEXT", "text": "kept intact"},
                    ],
                },
            ],
            "nodes": [],
        }
    }
    questions = [
        {
            "id": question_id,
            "number": 30,
            "prompt": "Table gap",
            "config": {},
            "answer_key": {"kind": "TEXT", "accepted": ["answer"]},
            "order_index": 0,
        }
    ]

    first, _ = normalize_question_group_payload(
        question_type="table_completion",
        group_config=legacy,
        questions=questions,
        group_id=group_id,
        passage_blocks=[],
    )
    second, _ = normalize_question_group_payload(
        question_type="table_completion",
        group_config=legacy,
        questions=questions,
        group_id=group_id,
        passage_blocks=[],
    )

    assert first == second
    assert first["layout"]["title"] == "Existing table"
    assert len(first["layout"]["rows"]) == 2
    assert first["layout"]["rows"][0]["cells"][0]["segments"][0]["text"] == "Question 30"
    assert first["layout"]["rows"][0]["cells"][1]["segments"][0]["question_id"] == question_id
    question_registry.validate_group("table_completion", first)


def test_table_completion_rejects_duplicate_unknown_and_orphan_question_refs() -> None:
    body = _table_completion_body()
    gap = body.config["layout"]["rows"][0]["cells"][1]["segments"][1]
    body.config["layout"]["rows"][0]["cells"][0]["segments"].append(
        {**gap, "id": str(uuid4())}
    )
    with pytest.raises(AppError, match="only one gap"):
        ReadingService._validate_group_body(body, [])

    orphan = _table_completion_body()
    orphan.questions.append(
        orphan.questions[0].model_copy(
            update={"id": uuid4(), "number": 31, "order_index": 1}
        )
    )
    with pytest.raises(AppError, match="exactly one gap"):
        ReadingService._validate_group_body(orphan, [])

    unknown = _table_completion_body()
    unknown.config["layout"]["rows"][0]["cells"][1]["segments"][1][
        "question_id"
    ] = str(uuid4())
    with pytest.raises(AppError, match="exactly one gap"):
        ReadingService._validate_group_body(unknown, [])


def test_table_completion_bounds_title_and_row_shape_without_affecting_note_layouts() -> None:
    body = _table_completion_body()
    body.config["layout"]["title"] = "x" * 301
    with pytest.raises(AppError, match="at most 300"):
        ReadingService._validate_group_body(body, [])

    mismatched = _table_completion_body()
    mismatched.config["layout"]["rows"][0]["cells"].pop()
    with pytest.raises(AppError, match="column count"):
        ReadingService._validate_group_body(mismatched, [])

    question_registry.validate_group(
        "note_completion",
        {
            "layout": {
                "kind": "NOTE",
                "columns": [],
                "rows": [],
                "nodes": [
                    {"id": str(uuid4()), "type": "TEXT", "text": "Existing note", "level": 0}
                ],
            }
        },
    )


def _note_completion_body() -> QuestionGroupWrite:
    question_id = str(uuid4())
    return QuestionGroupWrite.model_validate(
        {
            "question_type": "note_completion",
            "instruction": "Complete the notes.",
            "config": {
                "layout": {
                    "kind": "NOTE",
                    "title": "HIRING A PUBLIC ROOM",
                    "columns": [],
                    "rows": [],
                    "nodes": [],
                    "blocks": [
                        {
                            "id": str(uuid4()),
                            "style": "HEADING",
                            "indent": 0,
                            "segments": [
                                {"id": str(uuid4()), "type": "TEXT", "text": "Room and cost"}
                            ],
                        },
                        {
                            "id": str(uuid4()),
                            "style": "BULLET",
                            "indent": 1,
                            "segments": [
                                {"id": str(uuid4()), "type": "TEXT", "text": "the "},
                                {
                                    "id": str(uuid4()),
                                    "type": "GAP",
                                    "question_id": question_id,
                                },
                                {"id": str(uuid4()), "type": "TEXT", "text": " Room"},
                            ],
                        },
                    ],
                }
            },
            "order_index": 0,
            "questions": [
                {
                    "id": question_id,
                    "number": 11,
                    "prompt": "Note gap",
                    "config": {"max_words": 2, "max_numbers": 1},
                    "answer_key": {
                        "kind": "TEXT",
                        "accepted": ["small"],
                        "case_sensitive": False,
                    },
                    "order_index": 0,
                }
            ],
        }
    )


def test_note_completion_supports_title_semantic_blocks_and_inline_segments() -> None:
    body = _note_completion_body()
    ReadingService._validate_group_body(body, [])
    parsed = question_registry.validate_group("note_completion", body.config)

    assert parsed.layout.title == "HIRING A PUBLIC ROOM"
    assert [block.style for block in parsed.layout.blocks] == ["HEADING", "BULLET"]
    assert parsed.layout.blocks[1].indent == 1
    assert [segment.type for segment in parsed.layout.blocks[1].segments] == [
        "TEXT",
        "GAP",
        "TEXT",
    ]
    assert question_registry.evaluate(
        "note_completion",
        body.questions[0].answer_key,
        " Small ",
        body.questions[0].config,
    )


def test_note_completion_rejects_duplicate_unknown_and_orphan_question_refs() -> None:
    duplicate = _note_completion_body()
    gap = duplicate.config["layout"]["blocks"][1]["segments"][1]
    duplicate.config["layout"]["blocks"][0]["segments"].append(
        {**gap, "id": str(uuid4())}
    )
    with pytest.raises(AppError, match="exactly one gap"):
        ReadingService._validate_group_body(duplicate, [])

    unknown = _note_completion_body()
    unknown.config["layout"]["blocks"][1]["segments"][1]["question_id"] = str(uuid4())
    with pytest.raises(AppError, match="exactly one gap"):
        ReadingService._validate_group_body(unknown, [])

    orphan = _note_completion_body()
    orphan.questions.append(
        orphan.questions[0].model_copy(
            update={"id": uuid4(), "number": 12, "order_index": 1}
        )
    )
    with pytest.raises(AppError, match="exactly one gap"):
        ReadingService._validate_group_body(orphan, [])


def test_note_completion_validates_uuid_indent_style_and_non_empty_blocks() -> None:
    invalid_indent = _note_completion_body()
    invalid_indent.config["layout"]["blocks"][0]["indent"] = 4
    with pytest.raises(AppError, match="less than or equal to 3"):
        ReadingService._validate_group_body(invalid_indent, [])

    invalid_style = _note_completion_body()
    invalid_style.config["layout"]["blocks"][0]["style"] = "CALLOUT"
    with pytest.raises(AppError, match="HEADING"):
        ReadingService._validate_group_body(invalid_style, [])

    invalid_uuid = _note_completion_body()
    invalid_uuid.config["layout"]["blocks"][0]["segments"][0]["id"] = "segment-one"
    with pytest.raises(AppError, match="UUID"):
        ReadingService._validate_group_body(invalid_uuid, [])

    empty = _note_completion_body()
    empty.config["layout"]["blocks"][0]["segments"][0]["text"] = ""
    with pytest.raises(AppError, match="cannot be empty"):
        ReadingService._validate_group_body(empty, [])


def test_legacy_note_nodes_normalize_to_stable_separate_blocks() -> None:
    group_id = uuid4()
    question_id = str(uuid4())
    legacy = {
        "layout": {
            "kind": "NOTE",
            "title": "  Existing note  ",
            "columns": [],
            "rows": [],
            "nodes": [
                {"id": "legacy-text", "type": "TEXT", "text": "Context", "level": 0},
                {
                    "id": "legacy-gap",
                    "type": "GAP",
                    "text": "",
                    "question_id": question_id,
                    "level": 2,
                },
                {"id": "legacy-tail", "type": "TEXT", "text": "After", "level": 1},
                {"id": "legacy-deep", "type": "TEXT", "text": "Deep", "level": 4},
            ],
        }
    }
    questions = [
        {
            "id": question_id,
            "number": 11,
            "prompt": "Note gap",
            "config": {"max_words": 2, "max_numbers": 1},
            "answer_key": {"kind": "TEXT", "accepted": ["answer"]},
            "order_index": 0,
        }
    ]

    first, first_questions = normalize_question_group_payload(
        question_type="note_completion",
        group_config=legacy,
        questions=questions,
        group_id=group_id,
        passage_blocks=[],
    )
    second, _ = normalize_question_group_payload(
        question_type="note_completion",
        group_config=legacy,
        questions=questions,
        group_id=group_id,
        passage_blocks=[],
    )

    assert first == second
    assert first["layout"]["title"] == "Existing note"
    assert first["layout"]["nodes"] == []
    assert len(first["layout"]["blocks"]) == 4
    assert [block["indent"] for block in first["layout"]["blocks"]] == [0, 2, 1, 3]
    assert [block["segments"][0]["type"] for block in first["layout"]["blocks"]] == [
        "TEXT",
        "GAP",
        "TEXT",
        "TEXT",
    ]
    assert first_questions[0]["answer_key"] == {
        "kind": "TEXT",
        "accepted": ["answer"],
        "case_sensitive": False,
    }
    question_registry.validate_group("note_completion", first)


def test_legacy_diagram_options_and_markers_normalize_to_text_canvas() -> None:
    question_id = str(uuid4())
    marker_id = str(uuid4())
    config, questions = normalize_question_group_payload(
        question_type="diagram_labelling",
        group_config={
            "options": [
                {"id": "A", "label": "gates"},
                {"id": "B", "label": "locks"},
            ],
            "markers": [
                {"id": marker_id, "question_id": question_id, "x": 0.48, "y": 0.45}
            ],
        },
        questions=[
            {
                "id": question_id,
                "number": 20,
                "prompt": "A pair of ______ are lifted.",
                "config": {},
                "answer_key": {"kind": "SINGLE_OPTION", "value": "A"},
                "order_index": 0,
            }
        ],
        group_id=uuid4(),
        passage_blocks=[],
    )
    assert set(config) == {"items"}
    assert config["items"][0]["question_id"] == question_id
    assert config["items"][0]["arrow"]["end_x"] == 0.48
    assert questions[0]["prompt"] == "A pair of {{gap}} are lifted."
    assert questions[0]["answer_key"] == {
        "kind": "TEXT",
        "accepted": ["gates"],
        "case_sensitive": False,
    }


def test_plan_and_map_labelling_remain_option_based() -> None:
    question_id = str(uuid4())
    option_ids = [str(uuid4()), str(uuid4())]
    config = {
        "options": [
            {"id": option_ids[0], "label": "A", "text": "Entrance"},
            {"id": option_ids[1], "label": "B", "text": "Exit"},
        ],
        "markers": [
            {"id": str(uuid4()), "question_id": question_id, "x": 0.4, "y": 0.6}
        ],
    }
    for question_type in ("plan_labelling", "map_labelling"):
        question_registry.validate(
            question_type,
            config,
            {},
            {"kind": "SINGLE_OPTION", "value": option_ids[0]},
        )
        assert question_registry.evaluate(
            question_type,
            {"kind": "SINGLE_OPTION", "value": option_ids[0]},
            option_ids[0],
            {},
        )


def test_plan_and_map_normalization_drops_legacy_markers_idempotently() -> None:
    group_id = uuid4()
    question_id = str(uuid4())
    option_ids = [str(uuid4()), str(uuid4())]
    legacy_config = {
        "options": [
            {"id": option_ids[0], "label": "A", "text": "Entrance"},
            {"id": option_ids[1], "label": "B", "text": "Exit"},
        ],
        "markers": [
            {"id": str(uuid4()), "question_id": question_id, "x": 0.4, "y": 0.6}
        ],
    }
    raw_questions = [
        {
            "id": question_id,
            "number": 16,
            "prompt": "Scarecrow",
            "config": {},
            "answer_key": {"kind": "SINGLE_OPTION", "value": option_ids[1]},
            "order_index": 0,
        }
    ]

    for question_type in ("plan_labelling", "map_labelling"):
        first_config, first_questions = normalize_question_group_payload(
            question_type=question_type,
            group_config=legacy_config,
            questions=raw_questions,
            group_id=group_id,
            passage_blocks=[],
            module_type="LISTENING",
        )
        second_config, second_questions = normalize_question_group_payload(
            question_type=question_type,
            group_config=first_config,
            questions=first_questions,
            group_id=group_id,
            passage_blocks=[],
            module_type="LISTENING",
        )

        assert first_config == {"options": legacy_config["options"]}
        assert second_config == first_config
        assert second_questions == first_questions
        assert first_questions[0]["id"] == question_id
        assert first_questions[0]["answer_key"]["value"] == option_ids[1]
        question_registry.validate_group(question_type, first_config)


def test_reading_plan_and_map_normalization_and_marker_validation_are_preserved() -> None:
    question_id = str(uuid4())
    option_ids = [str(uuid4()), str(uuid4())]
    marker = {
        "id": str(uuid4()),
        "question_id": question_id,
        "x": 0.4,
        "y": 0.6,
    }
    config = {
        "options": [
            {"id": option_ids[0], "label": "A", "text": "Entrance"},
            {"id": option_ids[1], "label": "B", "text": "Exit"},
        ],
        "markers": [marker],
    }
    questions = [
        {
            "id": question_id,
            "number": 1,
            "prompt": "Gate",
            "config": {},
            "answer_key": {"kind": "SINGLE_OPTION", "value": option_ids[0]},
            "order_index": 0,
        }
    ]
    normalized, normalized_questions = normalize_question_group_payload(
        question_type="map_labelling",
        group_config=config,
        questions=questions,
        group_id=uuid4(),
        passage_blocks=[],
        module_type="READING",
    )

    assert normalized["markers"] == [marker]
    body = QuestionGroupWrite.model_validate(
        {
            "question_type": "map_labelling",
            "instruction": "Choose a letter.",
            "config": normalized,
            "order_index": 0,
            "questions": normalized_questions,
            "image_asset_id": uuid4(),
        }
    )
    ReadingService._validate_group_body(body, [], module_type=ModuleType.READING)

    without_marker = body.model_copy(update={"config": {"options": normalized["options"]}})
    with pytest.raises(AppError, match="Visual markers must reference"):
        ReadingService._validate_group_body(
            without_marker, [], module_type=ModuleType.READING
        )


def test_transfer_remapper_updates_diagram_item_question_ids() -> None:
    old_question_id = str(uuid4())
    new_question_id = str(uuid4())
    remapped = remap_question_references(
        _diagram_config(old_question_id), {old_question_id: new_question_id}
    )
    assert remapped["items"][0]["question_id"] == new_question_id
