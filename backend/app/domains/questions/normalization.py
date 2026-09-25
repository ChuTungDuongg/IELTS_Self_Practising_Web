from __future__ import annotations

import re
import uuid
from collections import defaultdict
from copy import deepcopy
from typing import Any

LEGACY_ID_NAMESPACE = uuid.UUID("c02491e7-e7dd-4d64-93fe-3182600cc8cc")


def _stable_uuid(scope: str, value: object, index: int) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return str(uuid.uuid5(LEGACY_ID_NAMESPACE, f"{scope}:{value!s}:{index}"))


def alphabetic_label(index: int) -> str:
    """Return spreadsheet-style labels: A..Z, AA..AZ, BA..."""
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def normalize_passage_blocks(
    blocks: list[dict[str, Any]], passage_id: uuid.UUID | str
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    paragraph_index = 0
    for index, raw in enumerate(blocks):
        block = deepcopy(raw)
        block["id"] = _stable_uuid(f"passage:{passage_id}:block", raw.get("id"), index)
        block_type = block.get("type", "paragraph")
        block["type"] = block_type
        if block_type == "paragraph":
            label = str(block.get("label") or "").strip()
            block["label"] = label or alphabetic_label(paragraph_index)
            paragraph_index += 1
        elif block.get("label") is None:
            block["label"] = None
        normalized.append(block)
    return normalized


def _normalize_options(
    options: list[dict[str, Any]], scope: str
) -> tuple[list[dict[str, str]], dict[str, list[str]]]:
    normalized: list[dict[str, str]] = []
    legacy_ids: dict[str, list[str]] = defaultdict(list)
    for index, raw in enumerate(options):
        legacy_id = str(raw.get("id") or "").strip()
        option_id = _stable_uuid(scope, legacy_id, index)
        if "text" in raw:
            label = str(raw.get("label") or "").strip()
            text = str(raw.get("text") or "")
        else:
            try:
                uuid.UUID(legacy_id)
            except ValueError:
                # Legacy options used a visible label (A, i, ii...) as their ID.
                label = legacy_id
                text = str(raw.get("label") or "")
            else:
                # A UUID already denotes modern identity; preserve malformed content
                # so schema validation reports the missing text instead of guessing.
                normalized.append({"id": option_id, "label": str(raw.get("label") or "")})
                legacy_ids[legacy_id].append(option_id)
                legacy_ids[option_id].append(option_id)
                continue
        normalized.append({"id": option_id, "label": label, "text": text})
        legacy_ids[legacy_id].append(option_id)
        legacy_ids[option_id].append(option_id)
    return normalized, legacy_ids


def _normalize_single_option_key(
    answer_key: dict[str, Any], option_ids: dict[str, list[str]] | None = None
) -> dict[str, Any]:
    if answer_key.get("kind") == "SINGLE_OPTION":
        value = answer_key.get("value", "")
    else:
        accepted = answer_key.get("accepted")
        value = accepted[0] if isinstance(accepted, list) and accepted else ""
    value_string = str(value)
    matches = option_ids.get(value_string, []) if option_ids is not None else []
    if len(set(matches)) == 1:
        value_string = matches[0]
    return {"kind": "SINGLE_OPTION", "value": value_string}


def _normalize_multiple_options_key(
    answer_key: dict[str, Any], option_ids: dict[str, list[str]]
) -> dict[str, Any]:
    raw_values = answer_key.get("values", answer_key.get("accepted", []))
    values: list[str] = []
    for raw in raw_values if isinstance(raw_values, list) else []:
        value = str(raw)
        matches = option_ids.get(value, [])
        values.append(matches[0] if len(set(matches)) == 1 else value)
    return {
        "kind": "MULTIPLE_OPTIONS",
        "values": values,
        "order_matters": bool(answer_key.get("order_matters", False)),
    }


def _normalize_text_key(answer_key: dict[str, Any]) -> dict[str, Any]:
    accepted = [
        str(candidate).strip()
        for candidate in answer_key.get("accepted", [])
        if str(candidate).strip()
    ]
    return {
        "kind": "TEXT",
        "accepted": accepted,
        "case_sensitive": bool(answer_key.get("case_sensitive", False)),
    }


def _diagram_prompt(prompt: str) -> str:
    if prompt.count("{{gap}}"):
        return prompt
    marker = re.search(r"_{2,}", prompt)
    if marker:
        return f"{prompt[: marker.start()]}{{{{gap}}}}{prompt[marker.end() :]}"
    return f"{prompt.rstrip()} {{{{gap}}}}".strip()


def _legacy_diagram_answer(
    answer_key: dict[str, Any],
    raw_options: list[dict[str, Any]],
    normalized_options: list[dict[str, str]],
) -> dict[str, Any]:
    if answer_key.get("kind") == "TEXT" or isinstance(answer_key.get("accepted"), list):
        if answer_key.get("kind") == "TEXT":
            return _normalize_text_key(answer_key)
    value = answer_key.get("value")
    if value is None:
        accepted = answer_key.get("accepted")
        value = accepted[0] if isinstance(accepted, list) and accepted else ""
    selected = str(value)
    matches = {
        str(normalized.get("text") or "").strip()
        for raw, normalized in zip(raw_options, normalized_options, strict=False)
        if selected
        in {
            str(raw.get("id") or ""),
            str(raw.get("label") or ""),
            str(normalized.get("id") or ""),
        }
        and str(normalized.get("text") or "").strip()
    }
    return {
        "kind": "TEXT",
        "accepted": [next(iter(matches))] if len(matches) == 1 else [],
        "case_sensitive": False,
    }


def _legacy_diagram_items(
    *,
    group_id: uuid.UUID | str,
    questions: list[dict[str, Any]],
    markers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    markers_by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for marker in markers:
        markers_by_question[str(marker.get("question_id") or "")].append(marker)
    positional_fallback = len(markers) == len(questions)
    for index, question in enumerate(questions):
        question_id = str(question["id"])
        matches = markers_by_question.get(question_id, [])
        marker = matches[0] if len(matches) == 1 else markers[index] if positional_fallback else {}
        end_x = _legacy_coordinate(marker.get("x"))
        end_y = _legacy_coordinate(marker.get("y"))
        width = 0.3
        box_x = 0.04 if end_x >= 0.5 else 1 - width - 0.04
        box_y = min(0.84, 0.06 + (index % 7) * 0.12)
        marker_id = marker.get("id") or question_id
        items.append(
            {
                "id": _stable_uuid(f"group:{group_id}:diagram-item", marker_id, index),
                "question_id": question_id,
                "box": {"x": box_x, "y": box_y, "width": width},
                "arrow": {
                    "start_x": box_x + width if box_x < end_x else box_x,
                    "start_y": min(1.0, box_y + 0.05),
                    "end_x": end_x,
                    "end_y": end_y,
                },
            }
        )
    return items


def _legacy_coordinate(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _normalize_table_layout(config: dict[str, Any], group_id: uuid.UUID | str) -> dict[str, Any]:
    layout = dict(config.get("layout") or {})
    columns: list[dict[str, Any]] = []
    for column_index, raw_column in enumerate(layout.get("columns") or []):
        column = dict(raw_column or {})
        columns.append(
            {
                "id": _stable_uuid(
                    f"group:{group_id}:table-column", column.get("id"), column_index
                ),
                "label": str(column.get("label") or ""),
            }
        )

    rows: list[dict[str, Any]] = []
    for row_index, raw_row in enumerate(layout.get("rows") or []):
        row = dict(raw_row or {})
        row_id = _stable_uuid(f"group:{group_id}:table-row", row.get("id"), row_index)
        cells: list[dict[str, Any]] = []
        for cell_index, raw_cell in enumerate(row.get("cells") or []):
            cell = dict(raw_cell or {})
            cell_id = _stable_uuid(
                f"group:{group_id}:table-row:{row_id}:cell", cell.get("id"), cell_index
            )
            raw_segments = cell.get("segments")
            if not isinstance(raw_segments, list) or not raw_segments:
                legacy_type = cell.get("type", "TEXT")
                legacy_segment: dict[str, Any] = {
                    "id": _stable_uuid(
                        f"group:{group_id}:table-cell:{cell_id}:segment",
                        f"legacy-{legacy_type}",
                        0,
                    ),
                    "type": legacy_type,
                }
                if legacy_type == "GAP":
                    legacy_segment["question_id"] = cell.get("question_id")
                else:
                    legacy_segment["text"] = str(cell.get("text") or "")
                raw_segments = [legacy_segment]

            segments: list[dict[str, Any]] = []
            for segment_index, raw_segment in enumerate(raw_segments):
                segment = dict(raw_segment or {})
                segment_type = segment.get("type", "TEXT")
                normalized_segment: dict[str, Any] = {
                    "id": _stable_uuid(
                        f"group:{group_id}:table-cell:{cell_id}:segment",
                        segment.get("id"),
                        segment_index,
                    ),
                    "type": segment_type,
                }
                if segment_type == "GAP":
                    question_id = segment.get("question_id")
                    normalized_segment["question_id"] = (
                        str(question_id) if question_id is not None else None
                    )
                else:
                    normalized_segment["text"] = str(segment.get("text") or "")
                    if segment.get("question_id") is not None:
                        normalized_segment["question_id"] = str(segment["question_id"])
                segments.append(normalized_segment)
            cells.append({"id": cell_id, "segments": segments})
        rows.append({"id": row_id, "cells": cells})

    normalized_layout: dict[str, Any] = {
        "kind": layout.get("kind", "TABLE"),
        "columns": columns,
        "rows": rows,
        "nodes": list(layout.get("nodes") or []),
    }
    if "title" in layout:
        normalized_layout["title"] = str(layout.get("title") or "").strip()
    return {**config, "layout": normalized_layout}


def _normalize_note_layout(config: dict[str, Any], group_id: uuid.UUID | str) -> dict[str, Any]:
    layout = dict(config.get("layout") or {})
    raw_blocks = layout.get("blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:

        def legacy_indent(value: Any) -> int:
            try:
                return min(3, max(0, int(value)))
            except (TypeError, ValueError):
                return 0

        raw_blocks = [
            {
                "id": node.get("id"),
                "style": "TEXT",
                "indent": legacy_indent(node.get("level", 0)),
                "segments": [
                    {
                        "id": node.get("id"),
                        "type": node.get("type", "TEXT"),
                        "text": node.get("text", ""),
                        "question_id": node.get("question_id"),
                    }
                ],
            }
            for node in layout.get("nodes") or []
            if isinstance(node, dict)
        ]

    blocks: list[dict[str, Any]] = []
    for block_index, raw_block in enumerate(raw_blocks):
        block = dict(raw_block or {})
        block_id = _stable_uuid(f"group:{group_id}:note-block", block.get("id"), block_index)
        segments: list[dict[str, Any]] = []
        for segment_index, raw_segment in enumerate(block.get("segments") or []):
            segment = dict(raw_segment or {})
            segment_type = segment.get("type", "TEXT")
            normalized_segment: dict[str, Any] = {
                "id": _stable_uuid(
                    f"group:{group_id}:note-block:{block_id}:segment",
                    segment.get("id"),
                    segment_index,
                ),
                "type": segment_type,
            }
            if segment_type == "GAP":
                question_id = segment.get("question_id")
                normalized_segment["question_id"] = (
                    str(question_id) if question_id is not None else None
                )
            else:
                normalized_segment["text"] = str(segment.get("text") or "")
                if segment.get("question_id") is not None:
                    normalized_segment["question_id"] = str(segment["question_id"])
            segments.append(normalized_segment)
        blocks.append(
            {
                "id": block_id,
                "style": block.get("style", "TEXT"),
                "indent": block.get("indent", 0),
                "segments": segments,
            }
        )

    normalized_layout = {
        "kind": "NOTE",
        "title": str(layout.get("title") or "").strip(),
        "columns": [],
        "rows": [],
        "nodes": [],
        "blocks": blocks,
    }
    return {**config, "layout": normalized_layout}


def normalize_question_group_payload(
    *,
    question_type: str,
    group_config: dict[str, Any],
    questions: list[dict[str, Any]],
    group_id: uuid.UUID | str,
    passage_blocks: list[dict[str, Any]],
    module_type: object | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize legacy draft JSON without guessing ambiguous references.

    UUIDv5 makes legacy identities stable across repeated Builder loads. References are
    rewritten only when their legacy value resolves to exactly one target; ambiguous or
    missing values remain invalid so validation can surface them.
    """
    config = deepcopy(group_config)
    normalized_questions = deepcopy(questions)

    for index, question in enumerate(normalized_questions):
        question["id"] = str(
            question.get("id")
            or _stable_uuid(f"group:{group_id}:question", question.get("number"), index)
        )

    if question_type == "table_completion":
        config = _normalize_table_layout(config, group_id)
    if question_type == "note_completion":
        config = _normalize_note_layout(config, group_id)

    if (
        question_type in {"text_completion", "summary_completion_word_list"}
        and "blocks" not in config
    ):
        blocks: list[dict[str, Any]] = []
        for index, question in enumerate(normalized_questions):
            question_id = str(question["id"])
            prompt = str(question.get("prompt") or "")
            marker = re.search(r"_{2,}", prompt)
            before = prompt[: marker.start()] if marker else prompt
            after = prompt[marker.end() :] if marker else ""
            segments: list[dict[str, Any]] = []
            if before:
                segments.append(
                    {
                        "id": _stable_uuid(f"group:{group_id}:block:{index}:segment", "before", 0),
                        "type": "TEXT",
                        "text": before,
                    }
                )
            segments.append(
                {
                    "id": _stable_uuid(f"group:{group_id}:block:{index}:segment", "gap", 1),
                    "type": "GAP",
                    "text": "",
                    "question_id": question_id,
                }
            )
            if after:
                segments.append(
                    {
                        "id": _stable_uuid(f"group:{group_id}:block:{index}:segment", "after", 2),
                        "type": "TEXT",
                        "text": after,
                    }
                )
            blocks.append(
                {
                    "id": _stable_uuid(f"group:{group_id}:block", question_id, index),
                    "segments": segments,
                }
            )
        config = {"mode": "SENTENCE", "blocks": blocks}

    if question_type == "diagram_labelling" and "items" not in config:
        raw_options = list(config.get("options") or [])
        normalized_options, _ = _normalize_options(raw_options, f"group:{group_id}:diagram-option")
        config = {
            "items": _legacy_diagram_items(
                group_id=group_id,
                questions=normalized_questions,
                markers=list(config.get("markers") or []),
            )
        }
        for question in normalized_questions:
            question["prompt"] = _diagram_prompt(str(question.get("prompt") or ""))
            question["answer_key"] = _legacy_diagram_answer(
                dict(question.get("answer_key") or {}), raw_options, normalized_options
            )
    elif question_type == "diagram_labelling":
        config = {"items": list(config.get("items") or [])}

    group_option_ids: dict[str, list[str]] | None = None
    if question_type in {
        "matching_headings",
        "matching",
        "matching_features",
        "matching_sentence_endings",
        "summary_completion_word_list",
        "plan_labelling",
        "map_labelling",
    }:
        options, group_option_ids = _normalize_options(
            list(config.get("options") or []), f"group:{group_id}:heading"
        )
        listening_plan_or_map = getattr(
            module_type, "value", module_type
        ) == "LISTENING" and question_type in {"plan_labelling", "map_labelling"}
        config = {"options": options} if listening_plan_or_map else {**config, "options": options}

    block_ids: dict[str, list[str]] = defaultdict(list)
    for block in passage_blocks:
        if block.get("type") != "paragraph":
            continue
        block_id = str(block.get("id") or "")
        label = str(block.get("label") or "").strip()
        block_ids[block_id].append(block_id)
        if label:
            block_ids[label].append(block_id)
            block_ids[f"Paragraph {label}"].append(block_id)

    for index, question in enumerate(normalized_questions):
        question_id = question.get("id") or _stable_uuid(
            f"group:{group_id}:question", question.get("number"), index
        )
        question["id"] = str(question_id)

        if question_type == "multiple_choice":
            question_config = dict(question.get("config") or {})
            options, option_ids = _normalize_options(
                list(question_config.get("options") or []),
                f"question:{question_id}:option",
            )
            question_config["options"] = options
            question["config"] = question_config
            question["answer_key"] = _normalize_single_option_key(
                dict(question.get("answer_key") or {}), option_ids
            )
        elif question_type in {
            "matching_headings",
            "matching",
            "matching_features",
            "matching_sentence_endings",
            "summary_completion_word_list",
            "plan_labelling",
            "map_labelling",
        }:
            question_config = dict(question.get("config") or {})
            if question_type == "matching_headings":
                target = question_config.get(
                    "target_block_id", question_config.get("target_label", "")
                )
                matches = block_ids.get(str(target), [])
                target_id = next(iter(set(matches))) if len(set(matches)) == 1 else str(target)
                question["config"] = {"target_block_id": target_id}
            question["answer_key"] = _normalize_single_option_key(
                dict(question.get("answer_key") or {}), group_option_ids
            )
        elif question_type == "matching_information":
            question["config"] = {}
            question["answer_key"] = _normalize_single_option_key(
                dict(question.get("answer_key") or {})
            )
        elif question_type == "multiple_choice_multiple":
            question_config = dict(question.get("config") or {})
            options, option_ids = _normalize_options(
                list(question_config.get("options") or []),
                f"question:{question_id}:option",
            )
            question_config["options"] = options
            question["config"] = question_config
            question["answer_key"] = _normalize_multiple_options_key(
                dict(question.get("answer_key") or {}), option_ids
            )
        elif question_type in {"true_false_not_given", "yes_no_not_given"}:
            normalized_key = _normalize_single_option_key(dict(question.get("answer_key") or {}))
            normalized_key["value"] = _normalize_agreement_value(normalized_key["value"])
            question["answer_key"] = normalized_key
        elif question_type in {
            "text_completion",
            "diagram_labelling",
            "table_completion",
            "note_completion",
            "form_completion",
            "flow_chart_completion",
            "summary_completion",
            "sentence_completion",
            "short_answer",
        }:
            question["answer_key"] = _normalize_text_key(dict(question.get("answer_key") or {}))

    return config, normalized_questions


def normalize_response_value(
    *,
    question_type: str,
    value: Any,
    raw_group_config: dict[str, Any],
    raw_question_config: dict[str, Any],
    normalized_group_config: dict[str, Any],
    normalized_question_config: dict[str, Any],
) -> Any:
    """Translate a legacy visible option value to its normalized stable ID."""
    if question_type == "multiple_choice_multiple" and isinstance(value, list):
        pass
    elif not isinstance(value, str):
        return value
    if question_type in {"true_false_not_given", "yes_no_not_given"}:
        return _normalize_agreement_value(value)
    if question_type in {"multiple_choice", "multiple_choice_multiple"}:
        raw_options = list(raw_question_config.get("options") or [])
        normalized_options = list(normalized_question_config.get("options") or [])
    elif question_type in {
        "matching_headings",
        "matching",
        "matching_features",
        "matching_sentence_endings",
        "summary_completion_word_list",
        "plan_labelling",
        "map_labelling",
    }:
        raw_options = list(raw_group_config.get("options") or [])
        normalized_options = list(normalized_group_config.get("options") or [])
    else:
        return value
    if question_type == "multiple_choice_multiple" and isinstance(value, list):
        normalized_values: list[str] = []
        for selected in value:
            selected_matches = {
                str(normalized.get("id"))
                for raw, normalized in zip(raw_options, normalized_options, strict=False)
                if isinstance(raw, dict)
                and isinstance(normalized, dict)
                and selected in {str(raw.get("id") or ""), str(normalized.get("id") or "")}
            }
            normalized_values.append(
                next(iter(selected_matches)) if len(selected_matches) == 1 else selected
            )
        return normalized_values
    matches = {
        str(normalized.get("id"))
        for raw, normalized in zip(raw_options, normalized_options, strict=False)
        if isinstance(raw, dict)
        and isinstance(normalized, dict)
        and value in {str(raw.get("id") or ""), str(normalized.get("id") or "")}
    }
    return next(iter(matches)) if len(matches) == 1 else value


def _normalize_agreement_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = "_".join(value.strip().upper().replace("/", " ").split())
    return normalized


def remap_question_references(value: Any, question_ids: dict[str, str]) -> Any:
    """Copy structured config when cloning to a new version, remapping explicit links only."""
    if isinstance(value, list):
        return [remap_question_references(item, question_ids) for item in value]
    if isinstance(value, dict):
        return {
            key: question_ids.get(str(item), item)
            if key == "question_id"
            else remap_question_references(item, question_ids)
            for key, item in value.items()
        }
    return value
