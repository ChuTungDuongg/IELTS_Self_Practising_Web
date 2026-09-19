from __future__ import annotations

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


def normalize_question_group_payload(
    *,
    question_type: str,
    group_config: dict[str, Any],
    questions: list[dict[str, Any]],
    group_id: uuid.UUID | str,
    passage_blocks: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize legacy draft JSON without guessing ambiguous references.

    UUIDv5 makes legacy identities stable across repeated Builder loads. References are
    rewritten only when their legacy value resolves to exactly one target; ambiguous or
    missing values remain invalid so validation can surface them.
    """
    config = deepcopy(group_config)
    normalized_questions = deepcopy(questions)

    group_option_ids: dict[str, list[str]] | None = None
    if question_type in {
        "matching_headings",
        "matching",
        "plan_labelling",
        "map_labelling",
        "diagram_labelling",
    }:
        options, group_option_ids = _normalize_options(
            list(config.get("options") or []), f"group:{group_id}:heading"
        )
        config["options"] = options

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
            "plan_labelling",
            "map_labelling",
            "diagram_labelling",
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
        elif question_type == "true_false_not_given":
            question["answer_key"] = _normalize_single_option_key(
                dict(question.get("answer_key") or {})
            )

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
    if question_type in {"multiple_choice", "multiple_choice_multiple"}:
        raw_options = list(raw_question_config.get("options") or [])
        normalized_options = list(normalized_question_config.get("options") or [])
    elif question_type in {
        "matching_headings",
        "matching",
        "plan_labelling",
        "map_labelling",
        "diagram_labelling",
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
