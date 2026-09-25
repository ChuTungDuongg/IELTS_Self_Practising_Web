"""Convert OCR-ready JSON into a validated, atomic Builder draft."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.domains.questions import question_registry
from app.domains.questions.normalization import normalize_passage_blocks
from app.domains.questions.numbering import question_span
from app.models import (
    Asset,
    ListeningPart,
    QuestionGroup,
    ReadingPassage,
    Test,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.models.enums import AssetType, ModuleType, VersionStatus
from app.repositories.tests import TestRepository
from app.schemas.content import QuestionGroupWrite, QuestionWrite, TextBlock
from app.schemas.draft_import import DraftImportManifest, ImportGroup, ImportOption, ImportQuestion
from app.services.reading import ReadingService
from app.services.tests import TestService
from app.storage import LocalAssetStorage

GAP = "{{gap}}"
TEXT_TYPES = {
    "text_completion",
    "note_completion",
    "table_completion",
    "form_completion",
    "flow_chart_completion",
    "summary_completion",
    "sentence_completion",
    "short_answer",
    "diagram_labelling",
}
GAP_TYPES = TEXT_TYPES - {"short_answer", "diagram_labelling"} | {"summary_completion_word_list"}
OPTION_TYPES = {
    "matching_headings",
    "matching",
    "matching_features",
    "matching_sentence_endings",
    "summary_completion_word_list",
    "plan_labelling",
    "map_labelling",
}
VISUAL_TYPES = {"plan_labelling", "map_labelling", "diagram_labelling"}
KIND = {
    "form_completion": "FORM",
    "flow_chart_completion": "FLOW_CHART",
    "summary_completion": "SUMMARY",
    "sentence_completion": "SENTENCE",
}
MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
}


@dataclass(frozen=True)
class DraftImportResult:
    test_id: uuid.UUID
    version_id: uuid.UUID
    title: str
    counts: dict[str, tuple[int, int, int]]
    warnings: list[str]


def load_manifest(path: Path) -> DraftImportManifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DraftImportManifest.model_validate(data)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise AppError("DRAFT_IMPORT_INVALID", f"Manifest is invalid: {exc}", 422) from exc


def _invalid(path: str, message: str) -> AppError:
    return AppError("DRAFT_IMPORT_INVALID", f"{path}: {message}", 422)


def _uuid() -> str:
    return str(uuid.uuid4())


def _options(options: list[ImportOption] | None, path: str) -> list[dict[str, str]]:
    if not options:
        raise _invalid(path, "At least two options are required")
    keys = [item.key for item in options]
    if len(keys) != len(set(keys)):
        raise _invalid(path, "Option keys must be unique")
    return [{"id": item.key, "label": item.text} for item in options]


def _answer_key(
    question_type: str, answer: str | list[str] | None, path: str, *, allow_incomplete: bool
) -> dict[str, Any]:
    if answer is None or answer == "" or answer == []:
        if allow_incomplete:
            return {}
        raise _invalid(path, "An answer is required")
    if question_type == "multiple_choice_multiple":
        if not isinstance(answer, list):
            raise _invalid(path, "Multiple-answer questions require an answer array")
        return {"kind": "MULTIPLE_OPTIONS", "values": answer}
    if question_type in TEXT_TYPES:
        values = answer if isinstance(answer, list) else [answer]
        return {"kind": "TEXT", "accepted": values, "case_sensitive": False}
    if isinstance(answer, list):
        raise _invalid(path, "This question type requires one answer")
    return {"kind": "SINGLE_OPTION", "value": answer}


def _segments(
    line: str, question_ids: list[str], position: list[int], *, text_gap: bool
) -> list[dict[str, Any]]:
    parts = line.split(GAP)
    segments: list[dict[str, Any]] = []
    for index, part in enumerate(parts):
        segments.append({"id": _uuid(), "type": "TEXT", "text": part})
        if index < len(parts) - 1:
            question_id = question_ids[position[0]]
            position[0] += 1
            segment: dict[str, Any] = {"id": _uuid(), "type": "GAP", "question_id": question_id}
            if text_gap:
                segment["text"] = ""
            segments.append(segment)
    return segments


def _simple_content(group: ImportGroup, ids: list[str], path: str) -> dict[str, Any]:
    content = group.content
    if not content:
        raise _invalid(path, "Completion content is required")
    position = [0]
    if group.question_type == "table_completion":
        if not all(
            isinstance(row, list) and all(isinstance(cell, str) for cell in row) for row in content
        ):
            raise _invalid(path, "Table content must be an array of string rows")
        rows_content = content
        width = len(rows_content[0])
        if width == 0 or any(len(row) != width for row in rows_content):
            raise _invalid(path, "Every table row must have the same nonzero number of cells")
        columns = group.columns or [f"Column {index + 1}" for index in range(width)]
        if len(columns) != width:
            raise _invalid(path, "Column labels must match table width")
        rows = [
            {
                "id": _uuid(),
                "cells": [
                    {"id": _uuid(), "segments": _segments(cell, ids, position, text_gap=False)}
                    for cell in row
                ],
            }
            for row in rows_content
        ]
        return {
            "layout": {
                "kind": "TABLE",
                "title": group.title,
                "columns": [{"id": _uuid(), "label": label} for label in columns],
                "rows": rows,
            }
        }
    if not all(isinstance(line, str) for line in content):
        raise _invalid(path, "Content must be an array of strings")
    if group.question_type in {"text_completion", "summary_completion_word_list"}:
        return {
            "mode": group.mode,
            "blocks": [
                {"id": _uuid(), "segments": _segments(line, ids, position, text_gap=True)}
                for line in content
            ],
        }
    if group.question_type == "note_completion":
        return {
            "layout": {
                "kind": "NOTE",
                "title": group.title,
                "blocks": [
                    {
                        "id": _uuid(),
                        "style": "TEXT",
                        "indent": 0,
                        "segments": _segments(line, ids, position, text_gap=False),
                    }
                    for line in content
                ],
            }
        }
    nodes: list[dict[str, Any]] = []
    for line in content:
        for segment in _segments(line, ids, position, text_gap=False):
            if segment["type"] == "TEXT" and not segment["text"]:
                continue
            nodes.append(
                {
                    "id": segment["id"],
                    "type": segment["type"],
                    **(
                        {"text": segment["text"]}
                        if segment["type"] == "TEXT"
                        else {"question_id": segment["question_id"]}
                    ),
                }
            )
    return {"layout": {"kind": KIND[group.question_type], "title": group.title, "nodes": nodes}}


def _compile_group(
    source: ImportGroup,
    path: str,
    next_number: int,
    passage_blocks: list[dict[str, Any]],
    module_type: ModuleType,
    image_asset_id: uuid.UUID | None,
    group_id: uuid.UUID,
    allow_incomplete: bool = False,
) -> tuple[QuestionGroupWrite, int]:
    kind = source.question_type
    if not question_registry.supports(kind):
        raise _invalid(path, f"Unknown question type: {kind}")
    if image_asset_id is not None and kind not in VISUAL_TYPES:
        raise _invalid(path, "Only visual labelling groups can attach an image")
    if kind in GAP_TYPES:
        if source.content is None:
            raise _invalid(path, "{{gap}} content is required")
        gap_count = sum(
            cell.count(GAP)
            for row in source.content
            for cell in (row if isinstance(row, list) else [row])
        )
        supplied = source.questions
        if source.answers is not None and supplied is not None:
            raise _invalid(path, "Use answers or questions, not both")
        if supplied is None:
            answers = source.answers or []
            supplied = [ImportQuestion(answer=value) for value in answers]
        if gap_count == 0 or gap_count != len(supplied):
            raise _invalid(path, f"Found {gap_count} gaps but {len(supplied)} linked answers")
        if source.numbers is not None:
            if len(source.numbers) != gap_count or any(
                item.number is not None for item in supplied
            ):
                raise _invalid(
                    path, "numbers must match gaps and must not duplicate question numbers"
                )
            supplied = [
                item.model_copy(update={"number": number})
                for item, number in zip(supplied, source.numbers, strict=True)
            ]
    else:
        supplied = source.questions or []
        if not supplied:
            raise _invalid(path, "At least one question is required")
        if source.answers is not None or source.numbers is not None or source.content is not None:
            raise _invalid(path, "content, answers and numbers are only for {{gap}} groups")
    questions: list[QuestionWrite] = []
    for index, item in enumerate(supplied):
        number = item.number if item.number is not None else next_number
        if number < 1 or number > 40:
            raise _invalid(f"{path}.questions[{index}]", "Question number must be 1–40")
        question_path = f"{path}.questions[{index}]"
        config: dict[str, Any] = {}
        if kind in {"multiple_choice", "multiple_choice_multiple"}:
            config["options"] = _options(item.options or source.options, question_path)
            if kind == "multiple_choice_multiple":
                count = (
                    len(item.answer)
                    if isinstance(item.answer, list)
                    else item.end_number - number + 1
                    if item.end_number is not None
                    else 2
                )
                required = item.min_selections or item.max_selections or count
                config.update(
                    min_selections=item.min_selections or required,
                    max_selections=item.max_selections or required,
                )
                if item.end_number is not None and item.end_number != number + config["max_selections"] - 1:
                    raise _invalid(question_path, "Explicit range does not match the required selection count")
            elif item.end_number is not None and item.end_number != number:
                raise _invalid(question_path, "Only a multi-select question may span multiple numbers")
        elif item.end_number is not None and item.end_number != number:
            raise _invalid(question_path, "Only a multi-select question may span multiple numbers")
        next_number = number + question_span(kind, config)
        if next_number > 41:
            raise _invalid(question_path, "Question range must end by 40")
        elif kind == "matching_headings":
            if not item.target:
                raise _invalid(question_path, "A paragraph target is required")
            config["target_label"] = item.target
        elif kind in TEXT_TYPES:
            if item.max_words is not None:
                config["max_words"] = item.max_words
            if item.max_numbers is not None:
                config["max_numbers"] = item.max_numbers
        prompt = item.prompt or item.target or (f"Gap {number}" if kind in GAP_TYPES else "")
        if kind == "diagram_labelling" and prompt.count(GAP) == 0:
            prompt = f"{prompt} {GAP}".strip()
        if not prompt:
            raise _invalid(question_path, "A prompt or target is required")
        answer = item.answer
        if kind == "matching_information" and isinstance(answer, str):
            matches = [
                str(block["id"])
                for block in passage_blocks
                if block.get("type") == "paragraph"
                and answer in {str(block.get("label")), f"Paragraph {block.get('label')}"}
            ]
            if len(matches) != 1:
                raise _invalid(question_path, "Answer must identify exactly one passage paragraph")
            answer = matches[0]
        questions.append(
            QuestionWrite(
                id=uuid.uuid4(),
                number=number,
                prompt=prompt,
                config=config,
                answer_key=_answer_key(
                    kind, answer, question_path, allow_incomplete=allow_incomplete
                ),
                explanation=item.explanation,
                order_index=index,
            )
        )
    config = {}
    if kind in OPTION_TYPES:
        config["options"] = _options(source.options, path)
        if kind in {
            "matching_headings",
            "matching",
            "matching_features",
            "matching_sentence_endings",
        }:
            config["allow_option_reuse"] = bool(source.allow_option_reuse)
    if kind == "matching_information":
        config["allow_option_reuse"] = (
            source.allow_option_reuse if source.allow_option_reuse is not None else True
        )
    if kind in GAP_TYPES:
        ids = [str(item.id) for item in questions]
        config.update(_simple_content(source, ids, path))
    if kind in {"plan_labelling", "map_labelling"} and module_type == ModuleType.READING:
        if any(item.x is None or item.y is None for item in supplied):
            raise _invalid(path, "Reading visual labels require x and y for each question")
        config["markers"] = [
            {"id": _uuid(), "question_id": str(question.id), "x": item.x, "y": item.y}
            for item, question in zip(supplied, questions, strict=True)
        ]
    if kind == "diagram_labelling":
        items = []
        for item, question in zip(supplied, questions, strict=True):
            if item.box is None or item.arrow is None:
                raise _invalid(path, "Diagram labels require box and arrow coordinates")
            items.append(
                {
                    "id": _uuid(),
                    "question_id": str(question.id),
                    "box": item.box,
                    "arrow": item.arrow,
                }
            )
        config = {"items": items}
    body = QuestionGroupWrite(
        question_type=kind,
        instruction=source.instruction,
        config=config,
        order_index=0,
        questions=questions,
        image_asset_id=image_asset_id,
    )
    body = ReadingService._normalize_group_body(
        body, group_id, passage_blocks, module_type=module_type
    )
    ReadingService._validate_local_question_numbers(body)
    ReadingService._validate_group_body(
        body,
        passage_blocks,
        module_type=module_type,
        allow_missing_answers=allow_incomplete,
    )
    return body, next_number


class DraftImportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.storage = LocalAssetStorage(self.settings.resolved_storage_root)

    def _asset(
        self,
        root: Path,
        relative: str,
        version: TestVersion,
        asset_type: AssetType,
        created: list[str],
    ) -> Asset:
        normalized = relative.replace("\\", "/")
        if (
            normalized.startswith("/")
            or re.match(r"^[A-Za-z]:", normalized)
            or ".." in Path(normalized).parts
        ):
            raise _invalid(relative, "Asset path must be relative and stay inside the import root")
        source = (root / normalized).resolve()
        if root != source.parent and root not in source.parents:
            raise _invalid(relative, "Asset path leaves the import root")
        if not source.is_file():
            raise _invalid(relative, "Asset file does not exist")
        mime = MIME_BY_SUFFIX.get(source.suffix.lower())
        audio = asset_type == AssetType.LISTENING_AUDIO
        if mime not in (LocalAssetStorage.AUDIO_TYPES if audio else LocalAssetStorage.IMAGE_TYPES):
            raise _invalid(relative, "Unsupported asset file type")
        try:
            with source.open("rb") as input_file:
                head = input_file.read(16)
        except OSError as exc:
            raise _invalid(relative, "Asset file could not be read") from exc
        signatures = {
            "image/png": head.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": head.startswith(b"\xff\xd8\xff"),
            "image/webp": head.startswith(b"RIFF") and head[8:12] == b"WEBP",
            "audio/mpeg": head.startswith(b"ID3")
            or (len(head) > 1 and head[0] == 255 and head[1] & 224 == 224),
            "audio/mp4": head[4:8] == b"ftyp",
            "audio/aac": len(head) > 1 and head[0] == 255 and head[1] & 246 == 240,
            "audio/wav": head.startswith(b"RIFF") and head[8:12] == b"WAVE",
            "audio/ogg": head.startswith(b"OggS"),
        }
        if not signatures[mime]:
            raise _invalid(relative, "Asset bytes do not match the file type")
        try:
            stored = self.storage.store_file(
                category="audio" if audio else "images",
                mime_type=mime,
                original_name=source.name,
                source=source,
                max_bytes=(
                    self.settings.max_audio_upload_mb
                    if audio
                    else self.settings.max_image_upload_mb
                )
                * 1024
                * 1024,
            )
        except OSError as exc:
            raise _invalid(relative, "Asset file could not be copied") from exc
        created.append(stored.relative_path)
        asset = Asset(
            id=uuid.uuid4(),
            asset_type=asset_type,
            relative_path=stored.relative_path,
            mime_type=mime,
            original_name=source.name,
            file_size=stored.size,
        )
        version.assets.append(asset)
        return asset

    async def import_manifest(
        self, manifest: DraftImportManifest, import_root: Path
    ) -> DraftImportResult:
        root = import_root.resolve()  # noqa: ASYNC240
        created: list[str] = []
        counts: dict[str, tuple[int, int, int]] = {}
        extra_warnings: list[str] = []
        missing_modules = {"READING", "LISTENING", "WRITING"} - {
            item.type for item in manifest.modules
        }
        if missing_modules:
            extra_warnings.append(
                "Incomplete test composition: missing " + ", ".join(sorted(missing_modules))
            )
        test = Test(id=uuid.uuid4(), title=manifest.title.strip(), description=manifest.description)
        version = TestVersion(id=uuid.uuid4(), version_number=1, status=VersionStatus.DRAFT)
        test.versions.append(version)
        try:
            async with self.session.begin():
                self.session.add(test)
                for module_index, source in enumerate(manifest.modules):
                    module_type = ModuleType(source.type)
                    module = TestModule(
                        id=uuid.uuid4(),
                        module_type=module_type,
                        title=source.title or source.type.title(),
                        order_index=module_index,
                    )
                    version.modules.append(module)
                    next_number = 1
                    question_total = 0
                    group_order = 0
                    unit_count = 0
                    if source.type == "LISTENING" and source.audio:
                        module.audio_asset = self._asset(
                            root, source.audio, version, AssetType.LISTENING_AUDIO, created
                        )
                    if source.type == "READING":
                        units = source.passages or []
                    elif source.type == "LISTENING":
                        units = source.sections or []
                    else:
                        units = []
                    for unit_index, unit in enumerate(units):
                        unit_count += 1
                        if source.type == "READING":
                            passage = ReadingPassage(
                                id=uuid.uuid4(),
                                title=unit.title,
                                order_index=unit_index,
                                content_json=[],
                                plain_text="",
                            )
                            raw_blocks = [
                                block.model_dump(exclude_none=True) for block in unit.blocks
                            ]
                            blocks = normalize_passage_blocks(raw_blocks, passage.id)
                            passage.content_json = [
                                TextBlock.model_validate(block).model_dump(mode="json")
                                for block in blocks
                            ]
                            passage.plain_text = "\n\n".join(block["text"] for block in blocks)
                            module.passages.append(passage)
                            part = None
                        else:
                            passage = None
                            blocks = []
                            part = ListeningPart(
                                id=uuid.uuid4(), title=unit.title, order_index=unit_index
                            )
                            module.listening_parts.append(part)
                        for local_index, group_source in enumerate(unit.question_groups):
                            path = f"modules[{module_index}].{source.type.lower()}[{unit_index}].question_groups[{local_index}]"
                            image = (
                                self._asset(
                                    root,
                                    group_source.image,
                                    version,
                                    AssetType.QUESTION_IMAGE,
                                    created,
                                )
                                if group_source.image
                                else None
                            )
                            group_id = uuid.uuid4()
                            body, next_number = _compile_group(
                                group_source,
                                path,
                                next_number,
                                blocks,
                                module_type,
                                image.id if image else None,
                                group_id,
                                allow_incomplete=manifest.allow_incomplete,
                            )
                            question_total += sum(question_span(body.question_type, item.config) for item in body.questions)
                            if not body.instruction.strip():
                                extra_warnings.append(f"{path}: instruction is missing")
                            group = QuestionGroup(
                                id=group_id,
                                passage=passage,
                                listening_part=part,
                                image_asset=image,
                                question_type=body.question_type,
                                instruction=body.instruction,
                                config=body.config,
                                order_index=group_order,
                            )
                            group_order += 1
                            ReadingService._apply_questions(group, body)
                            module.question_groups.append(group)
                    if source.type == "WRITING":
                        supplied = {task.task_number: task for task in source.tasks or []}
                        if len(supplied) != len(source.tasks or []):
                            raise _invalid(
                                f"modules[{module_index}].tasks",
                                "Writing task numbers must be unique",
                            )
                        for task_number, word_count, seconds in ((1, 150, 1200), (2, 250, 2400)):
                            item = supplied.get(task_number)
                            image = (
                                self._asset(
                                    root, item.image, version, AssetType.WRITING_TASK_IMAGE, created
                                )
                                if item and item.image
                                else None
                            )
                            if task_number == 2 and image is not None:
                                raise _invalid(
                                    f"modules[{module_index}].tasks",
                                    "Writing Task 2 cannot have an image",
                                )
                            module.writing_tasks.append(
                                WritingTask(
                                    id=uuid.uuid4(),
                                    task_number=task_number,
                                    order_index=task_number - 1,
                                    prompt=item.prompt if item else "",
                                    image_asset=image,
                                    minimum_recommended_words=item.minimum_recommended_words
                                    if item and item.minimum_recommended_words
                                    else word_count,
                                    recommended_duration_seconds=seconds,
                                )
                            )
                            if task_number == 1 and image is None:
                                extra_warnings.append(
                                    "Writing Task 1 has no image attached; review whether the source needs one"
                                )
                        unit_count = len(supplied)
                    counts[source.type] = (unit_count, group_order, question_total)
                await self.session.flush()
                loaded = await TestRepository(self.session).get_version(version.id)
                assert loaded is not None
                validation = TestService.validate_version(loaded)
                readiness_errors = [
                    issue
                    for issue in validation.errors
                    if issue.path == "modules"
                    and issue.message
                    == "Add at least one usable module with valid question content."
                ]
                incomplete_key_paths = {
                    f"{module.module_type.value.lower()}.questions.{question.number}"
                    for module in loaded.modules
                    for group in module.question_groups
                    for question in group.questions
                    if not any(
                        question.answer_key.get(field)
                        for field in ("value", "values", "accepted")
                    )
                    or (
                        group.question_type == "multiple_choice_multiple"
                        and len(question.answer_key.get("values", []))
                        < question.config.get("min_selections", 2)
                    )
                }
                incomplete_number_paths = {
                    f"{module.module_type.value.lower()}.questions"
                    for module in loaded.modules
                    if module.module_type in {ModuleType.READING, ModuleType.LISTENING}
                }
                expected_incomplete = [
                    issue
                    for issue in validation.errors
                    if manifest.allow_incomplete
                    and (
                        (
                            issue.path in incomplete_key_paths
                            and (
                                issue.message == "Answer key is incomplete."
                                or issue.message.startswith("Select exactly ")
                            )
                        )
                        or (
                            issue.path in incomplete_number_paths
                            and issue.message
                            == "Question numbers must form the canonical sequence 1 through N."
                        )
                    )
                ]
                fatal_errors = [
                    issue
                    for issue in validation.errors
                    if issue not in readiness_errors and issue not in expected_incomplete
                ]
                if fatal_errors:
                    raise _invalid(
                        "Builder validation",
                        "; ".join(f"{issue.path}: {issue.message}" for issue in fatal_errors),
                    )
                warnings = [
                    issue.message for issue in validation.warnings + readiness_errors
                ] + extra_warnings
                if expected_incomplete:
                    details: list[str] = []
                    if incomplete_key_paths:
                        details.append(f"{len(incomplete_key_paths)} questions have incomplete answer keys")
                    if any(issue.path in incomplete_number_paths for issue in expected_incomplete):
                        details.append("question-number gaps require review")
                    warnings.append("Incomplete draft: " + "; ".join(details) + " before publishing.")
        except BaseException:
            for relative_path in created:
                self.storage.delete(relative_path)
            raise
        return DraftImportResult(test.id, version.id, test.title, counts, warnings)
