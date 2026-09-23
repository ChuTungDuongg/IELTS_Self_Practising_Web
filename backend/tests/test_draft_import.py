import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models import Asset
from app.models import Test as ExamTest
from app.models.enums import VersionStatus
from app.schemas.content import PassageWrite, QuestionGroupWrite
from app.schemas.draft_import import DraftImportManifest
from app.services.draft_import import DraftImportService, load_manifest
from app.services.reading import ReadingService


def reading(groups=None, title="Passage 1"):
    return {
        "type": "READING",
        "passages": [
            {
                "title": title,
                "blocks": [
                    {"type": "heading", "text": "Fictional ecosystems"},
                    {
                        "type": "paragraph",
                        "label": "A",
                        "text": "An invented species lives near the river.",
                    },
                    {"type": "paragraph", "label": "B", "text": "It moves at night."},
                ],
                "question_groups": groups
                or [
                    {
                        "question_type": "true_false_not_given",
                        "questions": [
                            {"prompt": "The species lives by a river.", "answer": "TRUE"},
                        ],
                    }
                ],
            }
        ],
    }


def manifest(*modules):
    return DraftImportManifest.model_validate(
        {"format": "ielts-draft-import-v1", "title": "Fictional test", "modules": list(modules)}
    )


@pytest.mark.asyncio
async def test_simple_reading_import_builder_round_trip(db_session):
    result = await DraftImportService(db_session).import_manifest(manifest(reading()), Path.cwd())
    assert result.counts["READING"] == (1, 1, 1)
    builder = await ReadingService(db_session).builder_version(result.version_id)
    assert builder.status == VersionStatus.DRAFT
    passage = builder.modules[0].passages[0]
    assert passage.blocks[1].label == "A"
    group = passage.question_groups[0]
    assert group.questions[0].answer_key["value"] == "TRUE"
    original_ids = (passage.id, group.id, group.questions[0].id, passage.blocks[0].id)
    await db_session.rollback()
    await ReadingService(db_session).update_passage(
        passage.id,
        PassageWrite(
            title=passage.title,
            order_index=passage.order_index,
            blocks=passage.blocks,
        ),
    )
    updated = (
        (await ReadingService(db_session).builder_version(result.version_id)).modules[0].passages[0]
    )
    assert (
        updated.id,
        updated.question_groups[0].id,
        updated.question_groups[0].questions[0].id,
        updated.blocks[0].id,
    ) == original_ids


@pytest.mark.asyncio
async def test_multiple_passages_and_mixed_modules(db_session):
    second = reading()["passages"][0]
    second["title"] = "Passage 2"
    second["question_groups"][0]["questions"][0]["answer"] = "FALSE"
    reading_module = reading()
    reading_module["passages"].append(second)
    listening = {
        "type": "LISTENING",
        "sections": [
            {
                "title": "Section 1",
                "question_groups": [
                    {
                        "question_type": "short_answer",
                        "questions": [
                            {"prompt": "Name the fictional location", "answer": "River Park"}
                        ],
                    }
                ],
            },
            {
                "title": "Section 2",
                "question_groups": [
                    {
                        "question_type": "yes_no_not_given",
                        "questions": [{"prompt": "The speaker approves.", "answer": "YES"}],
                    }
                ],
            },
        ],
    }
    writing = {
        "type": "WRITING",
        "tasks": [
            {"task_number": 1, "prompt": "Describe an invented chart."},
            {"task_number": 2, "prompt": "Discuss a fictional policy."},
        ],
    }
    result = await DraftImportService(db_session).import_manifest(
        manifest(reading_module, listening, writing), Path.cwd()
    )
    builder = await ReadingService(db_session).builder_version(result.version_id)
    assert [module.module_type.value for module in builder.modules] == [
        "READING",
        "LISTENING",
        "WRITING",
    ]
    assert [
        q.number
        for p in builder.modules[0].passages
        for g in p.question_groups
        for q in g.questions
    ] == [1, 2]
    assert [
        q.number
        for p in builder.modules[1].listening_parts
        for g in p.question_groups
        for q in g.questions
    ] == [1, 2]
    assert len(builder.modules[2].writing_tasks) == 2
    assert builder.modules[1].audio_asset is None
    assert any("audio" in warning.lower() for warning in result.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "text_completion",
        "note_completion",
        "summary_completion",
        "sentence_completion",
        "form_completion",
        "flow_chart_completion",
    ],
)
async def test_gap_shapes_and_save_round_trip(db_session, kind):
    group = {
        "question_type": kind,
        "content": ["{{gap}} before {{gap}}{{gap}} after {{gap}}"],
        "answers": ["one", "two", "three", "four"],
    }
    result = await DraftImportService(db_session).import_manifest(
        manifest(reading([group])), Path.cwd()
    )
    initial = await ReadingService(db_session).builder_version(result.version_id)
    item = initial.modules[0].passages[0].question_groups[0]
    assert len(item.questions) == 4
    assert [q.number for q in item.questions] == [1, 2, 3, 4]
    config = item.config
    assert "{{gap}}" not in json.dumps(config)
    if kind == "text_completion":
        segments = config["blocks"][0]["segments"]
        assert segments[0]["type"] == "TEXT" and segments[0]["text"] == ""
        assert segments[-1]["type"] == "TEXT" and segments[-1]["text"] == ""
        assert [segment["type"] for segment in segments].count("GAP") == 4
    await db_session.rollback()
    await ReadingService(db_session).update_group(
        item.id,
        QuestionGroupWrite(
            question_type=item.question_type,
            instruction=item.instruction,
            config=item.config,
            order_index=item.order_index,
            questions=[question.model_dump() for question in item.questions],
        ),
    )
    after = (
        (await ReadingService(db_session).builder_version(result.version_id))
        .modules[0]
        .passages[0]
        .question_groups[0]
    )
    assert after.config == config
    assert [q.id for q in after.questions] == [q.id for q in item.questions]


@pytest.mark.asyncio
async def test_matching_and_generated_numbering(db_session):
    groups = [
        {
            "question_type": "multiple_choice",
            "questions": [
                {
                    "number": 1,
                    "prompt": "Where?",
                    "options": [{"key": "A", "text": "River"}, {"key": "B", "text": "Hill"}],
                    "answer": "A",
                }
            ],
        },
        {
            "question_type": "matching_headings",
            "options": [{"key": "i", "text": "River"}, {"key": "ii", "text": "Night"}],
            "questions": [
                {"target": "Paragraph A", "answer": "i"},
                {"target": "Paragraph B", "answer": "ii"},
            ],
        },
    ]
    result = await DraftImportService(db_session).import_manifest(
        manifest(reading(groups)), Path.cwd()
    )
    passage = (
        (await ReadingService(db_session).builder_version(result.version_id)).modules[0].passages[0]
    )
    assert [q.number for g in passage.question_groups for q in g.questions] == [1, 2, 3]
    matching = passage.question_groups[1]
    assert matching.questions[0].config["target_block_id"] == str(passage.blocks[1].id)
    assert matching.questions[0].answer_key["value"] == matching.config["options"][0]["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "group",
    [
        {"question_type": "not_registered", "questions": [{"prompt": "x", "answer": "x"}]},
        {
            "question_type": "true_false_not_given",
            "questions": [{"prompt": "x", "answer": "MAYBE"}],
        },
        {"question_type": "note_completion", "content": ["{{gap}}{{gap}}"], "answers": ["one"]},
        {
            "question_type": "true_false_not_given",
            "questions": [
                {"number": 1, "prompt": "x", "answer": "TRUE"},
                {"number": 1, "prompt": "y", "answer": "FALSE"},
            ],
        },
        {
            "question_type": "yes_no_not_given",
            "questions": [{"number": 2, "prompt": "x", "answer": "YES"}],
        },
    ],
)
async def test_invalid_import_rolls_back(db_session, group):
    before = await db_session.scalar(select(func.count(ExamTest.id)))
    await db_session.rollback()
    with pytest.raises(AppError):
        await DraftImportService(db_session).import_manifest(manifest(reading([group])), Path.cwd())
    assert await db_session.scalar(select(func.count(ExamTest.id))) == before


@pytest.mark.asyncio
async def test_asset_traversal_and_cleanup(db_session, tmp_path, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path / "stored", raising=False)
    before = await db_session.scalar(select(func.count(Asset.id)))
    await db_session.rollback()
    with pytest.raises(AppError, match="relative"):
        await DraftImportService(db_session).import_manifest(
            manifest({"type": "LISTENING", "audio": "../escape.mp3", "sections": []}), tmp_path
        )
    assert await db_session.scalar(select(func.count(Asset.id))) == before


@pytest.mark.asyncio
async def test_malformed_asset_is_rejected(db_session, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_root", tmp_path / "stored", raising=False)
    (tmp_path / "map.png").write_text("not a PNG", encoding="utf-8")
    group = {
        "question_type": "map_labelling",
        "image": "map.png",
        "options": [{"key": "A", "text": "River"}, {"key": "B", "text": "Hill"}],
        "questions": [{"prompt": "Find the river", "answer": "A", "x": 0.2, "y": 0.5}],
    }
    with pytest.raises(AppError, match="do not match"):
        await DraftImportService(db_session).import_manifest(manifest(reading([group])), tmp_path)
    assert not (tmp_path / "stored").exists()


@pytest.mark.asyncio
async def test_image_and_audio_assets_and_failed_copy_cleanup(db_session, tmp_path, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path / "stored", raising=False)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "map.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"fictional-image")
    (tmp_path / "assets" / "audio.mp3").write_bytes(b"ID3" + b"fictional-audio")
    group = {
        "question_type": "map_labelling",
        "image": "assets/map.png",
        "options": [{"key": "A", "text": "River"}, {"key": "B", "text": "Hill"}],
        "questions": [{"prompt": "Find the river", "answer": "A", "x": 0.25, "y": 0.5}],
    }
    listening = {
        "type": "LISTENING",
        "audio": "assets/audio.mp3",
        "sections": [
            {
                "title": "Section 1",
                "question_groups": [
                    {
                        "question_type": "short_answer",
                        "questions": [{"prompt": "Where?", "answer": "River"}],
                    }
                ],
            }
        ],
    }
    result = await DraftImportService(db_session).import_manifest(
        manifest(reading([group]), listening), tmp_path
    )
    builder = await ReadingService(db_session).builder_version(result.version_id)
    assert builder.modules[0].passages[0].question_groups[0].image_asset_id
    assert builder.modules[1].audio_asset is not None
    saved_group = builder.modules[0].passages[0].question_groups[0]
    await db_session.rollback()
    await ReadingService(db_session).update_group(
        saved_group.id,
        QuestionGroupWrite(
            question_type=saved_group.question_type,
            instruction=saved_group.instruction,
            config=saved_group.config,
            order_index=saved_group.order_index,
            questions=[question.model_dump() for question in saved_group.questions],
            image_asset_id=saved_group.image_asset_id,
        ),
    )
    refetched = await ReadingService(db_session).builder_version(result.version_id)
    assert (
        refetched.modules[0].passages[0].question_groups[0].image_asset_id
        == saved_group.image_asset_id
    )
    await db_session.rollback()
    before = set((tmp_path / "stored").rglob("*"))
    bad = {
        "type": "LISTENING",
        "sections": [
            {
                "title": "Section 1",
                "question_groups": [
                    {"question_type": "unknown", "questions": [{"prompt": "x", "answer": "x"}]}
                ],
            }
        ],
    }
    with pytest.raises(AppError):
        await DraftImportService(db_session).import_manifest(
            manifest(reading([group]), bad), tmp_path
        )
    assert set((tmp_path / "stored").rglob("*")) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "matching",
        "matching_features",
        "matching_sentence_endings",
        "summary_completion_word_list",
        "plan_labelling",
        "map_labelling",
        "matching_information",
        "multiple_choice_multiple",
        "table_completion",
    ],
)
async def test_other_registered_types(db_session, kind, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_root", tmp_path / "stored", raising=False)
    (tmp_path / "map.png").write_bytes(b"\x89PNG\r\n\x1a\nfiction")
    options = [{"key": "A", "text": "River"}, {"key": "B", "text": "Hill"}]
    if kind == "matching_information":
        group = {
            "question_type": kind,
            "questions": [{"prompt": "Where does it live?", "answer": "A"}],
        }
    elif kind == "multiple_choice_multiple":
        group = {
            "question_type": kind,
            "questions": [{"prompt": "Select two", "options": options, "answer": ["A", "B"]}],
        }
    elif kind == "table_completion":
        group = {
            "question_type": kind,
            "columns": ["Place", "Feature"],
            "content": [["River", "{{gap}}{{gap}}"]],
            "answers": ["water", "fish"],
        }
    elif kind == "summary_completion_word_list":
        group = {
            "question_type": kind,
            "options": options,
            "content": ["The {{gap}} is nearby."],
            "answers": ["A"],
        }
    else:
        group = {
            "question_type": kind,
            "options": options,
            "questions": [{"prompt": "Where?", "answer": "A", "x": 0.5, "y": 0.5}],
        }
        if kind in {"plan_labelling", "map_labelling"}:
            group["image"] = "map.png"
    result = await DraftImportService(db_session).import_manifest(
        manifest(reading([group])), tmp_path
    )
    saved = (
        (await ReadingService(db_session).builder_version(result.version_id))
        .modules[0]
        .passages[0]
        .question_groups[0]
    )
    assert saved.question_type == kind
    assert saved.questions[0].number == 1


@pytest.mark.asyncio
async def test_diagram_labelling_and_writing_image(db_session, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_root", tmp_path / "stored", raising=False)
    (tmp_path / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\nfiction")
    group = {
        "question_type": "diagram_labelling",
        "image": "figure.png",
        "questions": [
            {
                "prompt": "River source",
                "answer": "spring",
                "box": {"x": 0.1, "y": 0.1, "width": 0.3},
                "arrow": {"start_x": 0.4, "start_y": 0.2, "end_x": 0.7, "end_y": 0.7},
            }
        ],
    }
    writing = {
        "type": "WRITING",
        "tasks": [
            {"task_number": 1, "prompt": "Describe an invented diagram.", "image": "figure.png"}
        ],
    }
    result = await DraftImportService(db_session).import_manifest(
        manifest(reading([group]), writing), tmp_path
    )
    builder = await ReadingService(db_session).builder_version(result.version_id)
    assert builder.modules[0].passages[0].question_groups[0].config["items"][0]["question_id"]
    assert builder.modules[2 - 1].writing_tasks[0].image_asset_id


def test_manifest_schema(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {"format": "ielts-draft-import-v1", "title": "Fictional", "modules": [reading()]}
        ),
        encoding="utf-8",
    )
    assert load_manifest(path).title == "Fictional"


@pytest.mark.asyncio
async def test_documented_sample_and_incomplete_draft(db_session):
    sample = Path(__file__).parents[2] / "docs" / "examples" / "draft-import-manifest.json"
    parsed = load_manifest(sample)
    result = await DraftImportService(db_session).import_manifest(parsed, sample.parent)
    assert result.counts["READING"] == (1, 3, 6)
    assert any("audio" in warning.lower() for warning in result.warnings)
    empty = manifest({"type": "LISTENING", "sections": []})
    result2 = await DraftImportService(db_session).import_manifest(empty, sample.parent)
    assert result2.counts["LISTENING"] == (0, 0, 0)
    assert any("usable module" in warning for warning in result2.warnings)
