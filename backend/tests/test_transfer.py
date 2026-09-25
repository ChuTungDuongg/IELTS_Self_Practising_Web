import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.domains.questions.numbering import group_slots
from app.models import Asset, ListeningPart, Question, QuestionGroup, ReadingPassage, WritingTask
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AssetType, ModuleType, VersionStatus
from app.repositories.tests import version_detail_query
from app.schemas.transfer import PortableWritingTask, TransferExportRequest
from app.services.reading import ReadingService
from app.services.tests import TestService as LifecycleService
from app.services.transfer import TransferService


def _settings(storage_root: Path, **overrides: int) -> Settings:
    return Settings(
        database_url=get_settings().database_url,
        storage_root=storage_root,
        **overrides,
    )


def test_older_portable_writing_task_without_type_remains_importable() -> None:
    task = PortableWritingTask.model_validate(
        {"id": str(uuid4()), "task_number": 1, "prompt": "Fictional prompt", "order_index": 0}
    )
    assert task.task_type is None
    with pytest.raises(ValidationError):
        PortableWritingTask.model_validate(
            {
                "id": str(uuid4()),
                "task_number": 1,
                "task_type": "OPINION",
                "prompt": "Fictional prompt",
                "order_index": 0,
            }
        )


def _asset(
    root: Path, version: DomainVersion, asset_type: AssetType, name: str, content: bytes
) -> Asset:
    category = "audio" if asset_type == AssetType.LISTENING_AUDIO else "images"
    path = root / category / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    mime = "audio/mpeg" if category == "audio" else "image/png"
    asset = Asset(
        asset_type=asset_type,
        relative_path=f"{category}/{name}",
        mime_type=mime,
        original_name=name,
        file_size=len(content),
    )
    version.assets.append(asset)
    return asset


async def _portable_fixture(
    session: AsyncSession, root: Path
) -> tuple[DomainTest, DomainVersion, dict[str, Asset]]:
    test = DomainTest(title="Fictional portable IELTS test", description="Portable content only")
    version = DomainVersion(
        version_number=1,
        status=VersionStatus.PUBLISHED,
        published_at=datetime.now(UTC),
    )
    test.versions.append(version)
    audio = _asset(root, version, AssetType.LISTENING_AUDIO, "fictional.mp3", b"ID3fictional-audio")
    question_image = _asset(
        root, version, AssetType.QUESTION_IMAGE, "map.png", b"\x89PNG\r\n\x1a\nfictional-map"
    )
    writing_image = _asset(
        root,
        version,
        AssetType.WRITING_TASK_IMAGE,
        "chart.png",
        b"\x89PNG\r\n\x1a\nfictional-chart",
    )

    reading = DomainModule(module_type=ModuleType.READING, title="Reading", order_index=0)
    paragraph_id = uuid4()
    passage = ReadingPassage(
        title="Fictional passage",
        order_index=0,
        content_json=[
            {
                "id": str(paragraph_id),
                "type": "paragraph",
                "label": "A",
                "text": "A fictional paragraph.",
            }
        ],
        plain_text="A fictional paragraph.",
    )
    reading.passages.append(passage)
    heading_id = uuid4()
    heading_question = Question(
        id=uuid4(),
        number=1,
        prompt="Choose a heading.",
        config={"target_block_id": str(paragraph_id)},
        answer_key={"kind": "SINGLE_OPTION", "value": str(heading_id)},
        order_index=0,
    )
    heading_group = QuestionGroup(
        question_type="matching_headings",
        instruction="Choose a heading.",
        config={
            "options": [
                {"id": str(heading_id), "label": "i", "text": "A heading"},
                {"id": str(uuid4()), "label": "ii", "text": "Another"},
            ],
            "allow_option_reuse": False,
        },
        order_index=0,
        passage=passage,
    )
    heading_group.questions.append(heading_question)
    completion_question = Question(
        id=uuid4(),
        number=2,
        prompt="Complete the form.",
        config={"max_words": 2, "max_numbers": 1},
        answer_key={"kind": "TEXT", "accepted": ["fictional answer"], "case_sensitive": False},
        order_index=0,
    )
    completion_group = QuestionGroup(
        question_type="form_completion",
        instruction="Complete the form.",
        config={
            "layout": {
                "kind": "FORM",
                "nodes": [
                    {"id": "label", "type": "TEXT", "text": "Name"},
                    {
                        "id": "gap",
                        "type": "GAP",
                        "text": "",
                        "question_id": str(completion_question.id),
                        "level": 0,
                    },
                ],
            }
        },
        order_index=1,
        passage=passage,
    )
    completion_group.questions.append(completion_question)
    reading.question_groups.extend([heading_group, completion_group])

    listening = DomainModule(
        module_type=ModuleType.LISTENING, title="Listening", order_index=1, audio_asset=audio
    )
    part = ListeningPart(title="Section 1", order_index=0)
    listening.listening_parts.append(part)
    map_question = Question(
        id=uuid4(),
        number=1,
        prompt="Label the map.",
        config={},
        answer_key={"kind": "SINGLE_OPTION", "value": "a"},
        order_index=0,
    )
    map_group = QuestionGroup(
        question_type="map_labelling",
        instruction="Label the map.",
        image_asset=question_image,
        config={
            "options": [
                {"id": "a", "label": "A", "text": "Library"},
                {"id": "b", "label": "B", "text": "Cafe"},
            ],
            "markers": [{"id": "marker", "question_id": str(map_question.id), "x": 0.5, "y": 0.5}],
        },
        order_index=2,
        listening_part=part,
    )
    map_group.questions.append(map_question)
    listening.question_groups.append(map_group)

    writing = DomainModule(module_type=ModuleType.WRITING, title="Writing", order_index=2)
    writing.writing_tasks.extend(
        [
            WritingTask(
                task_number=1,
                prompt="Describe the fictional chart.",
                image_asset=writing_image,
                minimum_recommended_words=150,
                recommended_duration_seconds=1200,
                order_index=0,
            ),
            WritingTask(
                task_number=2,
                prompt="Discuss a fictional proposition.",
                minimum_recommended_words=250,
                recommended_duration_seconds=2400,
                order_index=1,
            ),
        ]
    )
    version.modules.extend([reading, listening, writing])
    async with session.begin():
        session.add(test)
        await session.flush()
    return (
        test,
        version,
        {"audio": audio, "question_image": question_image, "writing_image": writing_image},
    )


@pytest.mark.integration
async def test_transfer_export_rejects_empty_and_unknown_selection(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    with pytest.raises(ValidationError):
        TransferExportRequest(test_ids=[])
    with pytest.raises(AppError) as error:
        await TransferService(db_session, _settings(tmp_path / "storage")).export(
            [uuid4()], tmp_path / "missing.zip"
        )
    assert error.value.code == "TRANSFER_TEST_NOT_FOUND"


@pytest.mark.integration
async def test_transfer_exports_multiple_tests_and_imported_draft_loads_in_builder(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    settings = _settings(tmp_path / "storage")
    source, _, _ = await _portable_fixture(db_session, settings.resolved_storage_root)
    draft_test = DomainTest(title="Fictional portable draft")
    draft = DomainVersion(version_number=3, status=VersionStatus.DRAFT)
    writing = DomainModule(module_type=ModuleType.WRITING, title="Writing", order_index=0)
    writing.writing_tasks.extend(
        [
            WritingTask(
                task_number=1, task_type="MIXED_CHARTS", prompt="Draft task one.", order_index=0
            ),
            WritingTask(
                task_number=2, task_type="PROBLEM_SOLUTION", prompt="Draft task two.", order_index=1
            ),
        ]
    )
    draft.modules.append(writing)
    draft_test.versions.append(draft)
    async with db_session.begin():
        db_session.add(draft_test)
        await db_session.flush()
    source_id = source.id
    draft_test_id = draft_test.id
    archive = tmp_path / "multiple.zip"
    await TransferService(db_session, settings).export([source_id, draft_test_id], archive)
    await db_session.rollback()

    with tempfile.TemporaryDirectory(dir=tmp_path) as staging:
        package = TransferService(db_session, settings).validate_archive(archive, Path(staging))
        assert len(package.manifest.tests) == 2
        result = await TransferService(db_session, settings).import_package(package)
    assert len(result.imported_tests) == 2
    imported_draft_test = next(
        item for item in result.imported_tests if item.title == "Fictional portable draft"
    )
    imported_draft = await db_session.scalar(
        select(DomainVersion).where(
            DomainVersion.test_id == imported_draft_test.test_id,
            DomainVersion.status == VersionStatus.DRAFT,
        )
    )
    assert imported_draft is not None
    builder = await ReadingService(db_session).builder_version(imported_draft.id)
    assert builder.status == VersionStatus.DRAFT
    assert builder.modules[0].recommended_duration_seconds == 3600
    assert builder.modules[0].writing_tasks[0].prompt == "Draft task one."
    assert [task.task_type for task in builder.modules[0].writing_tasks] == [
        "MIXED_CHARTS",
        "PROBLEM_SOLUTION",
    ]


@pytest.mark.integration
async def test_transfer_round_trip_preserves_shared_multi_select_question_span(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    settings = _settings(tmp_path / "storage")
    test = DomainTest(title="Fictional grouped draft")
    version = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    module = DomainModule(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional passage",
        order_index=0,
        content_json=[
            {"id": str(uuid4()), "type": "paragraph", "label": "A", "text": "Fictional content."}
        ],
        plain_text="Fictional content.",
    )
    version.modules.append(module)
    module.passages.append(passage)
    test.versions.append(version)
    filler = QuestionGroup(
        question_type="true_false_not_given",
        instruction="Decide.",
        config={},
        order_index=0,
        passage=passage,
    )
    filler.questions.extend(
        Question(
            number=number,
            prompt=f"Statement {number}",
            config={},
            answer_key={},
            order_index=number - 1,
        )
        for number in range(1, 13)
    )
    options = [
        {"id": str(uuid4()), "label": letter, "text": f"Fictional option {letter}"}
        for letter in "ABCDE"
    ]
    multi = QuestionGroup(
        question_type="multiple_choice_multiple",
        instruction="Choose two.",
        config={},
        order_index=1,
        passage=passage,
    )
    multi.questions.append(
        Question(
            number=13,
            prompt="Choose fictional options",
            config={"options": options, "min_selections": 2, "max_selections": 2},
            answer_key={},
            order_index=0,
        )
    )
    following = QuestionGroup(
        question_type="true_false_not_given",
        instruction="Decide.",
        config={},
        order_index=2,
        passage=passage,
    )
    following.questions.append(
        Question(number=15, prompt="Following statement", config={}, answer_key={}, order_index=0)
    )
    module.question_groups.extend([filler, multi, following])
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
    test_id = test.id
    archive = tmp_path / "grouped.zip"
    await TransferService(db_session, settings).export([test_id], archive)
    await db_session.rollback()

    with tempfile.TemporaryDirectory(dir=tmp_path) as staging:
        package = TransferService(db_session, settings).validate_archive(archive, Path(staging))
        result = await TransferService(db_session, settings).import_package(package)
    imported = await db_session.scalar(
        version_detail_query().where(DomainVersion.test_id == result.imported_tests[0].test_id)
    )
    assert imported is not None
    groups = imported.modules[0].passages[0].question_groups
    shared = next(group for group in groups if group.question_type == "multiple_choice_multiple")
    assert group_slots(shared.question_type, shared.questions) == [13, 14]
    assert shared.questions[0].config["min_selections"] == 2
    assert not shared.questions[0].answer_key.get("values")
    assert sorted(
        slot for group in groups for slot in group_slots(group.question_type, group.questions)
    ) == list(range(1, 16))


@pytest.mark.integration
async def test_transfer_round_trip_preserves_completion_titles_and_static_diagram_annotations(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    settings = _settings(tmp_path / "storage")
    source, version, assets = await _portable_fixture(db_session, settings.resolved_storage_root)
    passage = version.modules[0].passages[0]
    text_question = Question(
        id=uuid4(),
        number=3,
        prompt="Fictional gap",
        config={"max_words": 2, "max_numbers": 1},
        answer_key={"kind": "TEXT", "accepted": ["fictional"], "case_sensitive": False},
        order_index=0,
    )
    text_group = QuestionGroup(
        question_type="text_completion",
        instruction="Complete the fictional text.",
        config={
            "mode": "PASSAGE",
            "title": "Fictional passage headline",
            "blocks": [
                {
                    "id": str(uuid4()),
                    "segments": [
                        {"id": str(uuid4()), "type": "TEXT", "text": "A "},
                        {"id": str(uuid4()), "type": "GAP", "question_id": str(text_question.id)},
                    ],
                }
            ],
        },
        order_index=2,
        module=version.modules[0],
        passage=passage,
    )
    text_group.questions.append(text_question)
    annotations = [
        {
            "id": str(uuid4()),
            "kind": "ARROW_LABEL" if index < 2 else "NOTE",
            "text": f"Static feature {index}",
            "label_x": index / 10,
            "label_y": 0.2,
            **({"target_x": 0.6, "target_y": 0.7} if index < 2 else {}),
        }
        for index in range(1, 5)
    ]
    diagram_group = QuestionGroup(
        question_type="diagram_labelling",
        instruction="Label the fictional diagram.",
        image_asset=assets["question_image"],
        config={
            "title": "Fictional diagram headline",
            "items": [],
            "annotations": annotations,
        },
        order_index=3,
        module=version.modules[0],
        passage=passage,
    )
    for index in range(5):
        question = Question(
            id=uuid4(),
            number=index + 4,
            prompt=f"Fictional component {index} {{{{gap}}}}",
            config={"max_words": 2, "max_numbers": 1},
            answer_key={
                "kind": "TEXT",
                "accepted": [f"component {index}"],
                "case_sensitive": False,
            },
            order_index=index,
        )
        diagram_group.questions.append(question)
        diagram_group.config["items"].append(
            {
                "id": str(uuid4()),
                "question_id": str(question.id),
                "box": {"x": 0.05, "y": index / 10, "width": 0.3},
                "arrow": {"start_x": 0.35, "start_y": index / 10, "end_x": 0.5, "end_y": 0.5},
            }
        )
    db_session.add_all([text_group, diagram_group])
    await db_session.flush()
    await db_session.commit()
    archive = tmp_path / "completion-titles.zip"
    await TransferService(db_session, settings).export([source.id], archive)
    await db_session.rollback()

    with tempfile.TemporaryDirectory(dir=tmp_path) as staging:
        package = TransferService(db_session, settings).validate_archive(archive, Path(staging))
        result = await TransferService(db_session, settings).import_package(package)
    imported = await db_session.scalar(
        version_detail_query().where(DomainVersion.test_id == result.imported_tests[0].test_id)
    )
    assert imported is not None
    groups = imported.modules[0].passages[0].question_groups
    text_copy = next(group for group in groups if group.question_type == "text_completion")
    diagram_copy = next(group for group in groups if group.question_type == "diagram_labelling")
    assert text_copy.config["title"] == "Fictional passage headline"
    assert diagram_copy.config["title"] == "Fictional diagram headline"
    assert diagram_copy.config["annotations"] == annotations
    assert len(diagram_copy.questions) == len(diagram_copy.config["items"]) == 5
    assert [question.number for question in diagram_copy.questions] == [4, 5, 6, 7, 8]


@pytest.mark.integration
async def test_transfer_round_trip_remaps_ids_assets_and_can_import_twice(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    settings = _settings(tmp_path / "storage")
    source_test, source_version, _ = await _portable_fixture(
        db_session, settings.resolved_storage_root
    )
    source_test_id = source_test.id
    source_test_title = source_test.title
    source_version_id = source_version.id
    source_loaded = await db_session.scalar(
        version_detail_query().where(DomainVersion.id == source_version_id)
    )
    assert source_loaded is not None
    source_question_ids = {
        question.id
        for module in source_loaded.modules
        for group in module.question_groups
        for question in group.questions
    }
    source_asset_data = {
        asset.asset_type: (
            asset.id,
            asset.relative_path,
            (settings.resolved_storage_root / asset.relative_path).read_bytes(),
        )
        for asset in source_loaded.assets
    }
    archive = tmp_path / "bundle.zip"
    await TransferService(db_session, settings).export([source_test_id], archive)
    await db_session.rollback()

    with tempfile.TemporaryDirectory(dir=tmp_path) as staging:
        package = TransferService(db_session, settings).validate_archive(archive, Path(staging))
        first = await TransferService(db_session, settings).import_package(package)
    assert first.version_count == 1
    assert first.asset_count == 3
    assert first.imported_tests[0].test_id != source_test_id

    imported = await db_session.scalar(
        version_detail_query().where(DomainVersion.test_id == first.imported_tests[0].test_id)
    )
    assert imported is not None
    assert imported.id != source_version_id
    assert imported.status == VersionStatus.PUBLISHED
    with pytest.raises(AppError) as immutable:
        await LifecycleService(db_session).ensure_draft(imported.id)
    assert immutable.value.code == "TEST_VERSION_IMMUTABLE"
    imported = await db_session.scalar(
        version_detail_query()
        .where(DomainVersion.id == imported.id)
        .execution_options(populate_existing=True)
    )
    assert imported is not None
    assert [module.module_type for module in imported.modules] == [
        ModuleType.READING,
        ModuleType.LISTENING,
        ModuleType.WRITING,
    ]
    imported_questions = [
        question
        for module in imported.modules
        for group in module.question_groups
        for question in group.questions
    ]
    assert not source_question_ids.intersection({question.id for question in imported_questions})
    completion = next(
        group
        for module in imported.modules
        for group in module.question_groups
        if group.question_type == "form_completion"
    )
    assert completion.config["layout"]["nodes"][1]["question_id"] == str(completion.questions[0].id)
    map_group = next(
        group
        for module in imported.modules
        for group in module.question_groups
        if group.question_type == "map_labelling"
    )
    map_options = map_group.config["options"]
    assert [{"label": option["label"], "text": option["text"]} for option in map_options] == [
        {"label": "A", "text": "Library"},
        {"label": "B", "text": "Cafe"},
    ]
    assert all(UUID(option["id"]) for option in map_options)
    assert map_group.questions[0].answer_key["value"] == map_options[0]["id"]
    imported_assets = {asset.asset_type: asset for asset in imported.assets}
    for asset_type, (source_id, source_path, source_bytes) in source_asset_data.items():
        restored = imported_assets[asset_type]
        assert restored.id != source_id
        assert restored.relative_path != source_path
        assert (
            settings.resolved_storage_root / restored.relative_path
        ).read_bytes() == source_bytes
    await db_session.rollback()

    with tempfile.TemporaryDirectory(dir=tmp_path) as staging:
        package = TransferService(db_session, settings).validate_archive(archive, Path(staging))
        second = await TransferService(db_session, settings).import_package(package)
    assert second.imported_tests[0].test_id not in {source_test_id, first.imported_tests[0].test_id}
    count = await db_session.scalar(
        select(func.count()).select_from(DomainTest).where(DomainTest.title == source_test_title)
    )
    assert count == 3


def _rewrite(source: Path, target: Path, mutate) -> None:
    with zipfile.ZipFile(source) as archive:
        entries = {item.filename: archive.read(item.filename) for item in archive.infolist()}
    mutate(entries)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


@pytest.mark.integration
async def test_transfer_rejects_malicious_and_invalid_archives_without_creating_tests(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    settings = _settings(tmp_path / "storage")
    source_test, _, _ = await _portable_fixture(db_session, settings.resolved_storage_root)
    valid = tmp_path / "valid.zip"
    await TransferService(db_session, settings).export([source_test.id], valid)
    await db_session.rollback()
    initial_count = await db_session.scalar(select(func.count()).select_from(DomainTest))
    await db_session.rollback()

    cases = []
    cases.append(("no-manifest", lambda entries: entries.pop("manifest.json")))
    cases.append(
        (
            "malformed-json",
            lambda entries: entries.update(
                {next(name for name in entries if name.startswith("tests/")): b"{"}
            ),
        )
    )
    cases.append(
        (
            "missing-asset",
            lambda entries: entries.pop(
                next(name for name in entries if name.startswith("assets/"))
            ),
        )
    )
    cases.append(
        (
            "checksum",
            lambda entries: entries.update(
                {next(name for name in entries if name.startswith("assets/")): b"changed"}
            ),
        )
    )
    cases.append(("traversal", lambda entries: entries.update({"../evil.txt": b"evil"})))
    cases.append(("absolute", lambda entries: entries.update({"/evil.txt": b"evil"})))

    def wrong_format(entries):
        manifest = json.loads(entries["manifest.json"])
        manifest["format"] = "wrong"
        entries["manifest.json"] = json.dumps(manifest).encode()

    cases.append(("wrong-format", wrong_format))

    def wrong_version(entries):
        manifest = json.loads(entries["manifest.json"])
        manifest["schema_version"] = 2
        entries["manifest.json"] = json.dumps(manifest).encode()

    cases.append(("wrong-version", wrong_version))

    def invalid_asset_type(entries):
        manifest = json.loads(entries["manifest.json"])
        audio = next(
            asset for asset in manifest["assets"] if asset["asset_type"] == "LISTENING_AUDIO"
        )
        audio["asset_type"] = "QUESTION_IMAGE"
        entries["manifest.json"] = json.dumps(manifest).encode()

    cases.append(("invalid-asset-type", invalid_asset_type))

    def invalid_mime(entries):
        manifest = json.loads(entries["manifest.json"])
        manifest["assets"][0]["mime_type"] = "application/octet-stream"
        entries["manifest.json"] = json.dumps(manifest).encode()

    cases.append(("invalid-mime", invalid_mime))

    def broken_reference(entries):
        name = next(name for name in entries if name.startswith("tests/"))
        payload = json.loads(entries[name])
        group = next(
            group
            for module in payload["versions"][0]["modules"]
            for group in module["question_groups"]
            if group["question_type"] == "form_completion"
        )
        group["config"]["layout"]["nodes"][1]["question_id"] = str(uuid4())
        entries[name] = json.dumps(payload).encode()

    cases.append(("broken-reference", broken_reference))

    def duplicate_published(entries):
        name = next(name for name in entries if name.startswith("tests/"))
        payload = json.loads(entries[name])
        duplicate = dict(payload["versions"][0])
        duplicate["id"] = str(uuid4())
        duplicate["version_number"] = 2
        duplicate["modules"] = []
        payload["versions"].append(duplicate)
        entries[name] = json.dumps(payload).encode()

    cases.append(("duplicate-published", duplicate_published))

    def duplicate_draft(entries):
        name = next(name for name in entries if name.startswith("tests/"))
        payload = json.loads(entries[name])
        payload["versions"][0]["status"] = "DRAFT"
        payload["versions"][0]["published_at"] = None
        duplicate = dict(payload["versions"][0])
        duplicate["id"] = str(uuid4())
        duplicate["version_number"] = 2
        duplicate["modules"] = []
        payload["versions"].append(duplicate)
        entries[name] = json.dumps(payload).encode()

    cases.append(("duplicate-draft", duplicate_draft))

    def invalid_published_history(entries):
        name = next(name for name in entries if name.startswith("tests/"))
        payload = json.loads(entries[name])
        payload["versions"][0]["published_at"] = None
        entries[name] = json.dumps(payload).encode()

    cases.append(("invalid-published-history", invalid_published_history))

    for label, mutate in cases:
        candidate = tmp_path / f"{label}.zip"
        _rewrite(valid, candidate, mutate)
        with tempfile.TemporaryDirectory(dir=tmp_path) as staging:
            with pytest.raises(AppError):
                package = TransferService(db_session, settings).validate_archive(
                    candidate, Path(staging)
                )
                await TransferService(db_session, settings).import_package(package)
        current_count = await db_session.scalar(select(func.count()).select_from(DomainTest))
        assert current_count == initial_count
        await db_session.rollback()

    too_many = _settings(tmp_path / "storage", max_transfer_files=1)
    with tempfile.TemporaryDirectory(dir=tmp_path) as staging, pytest.raises(AppError):
        TransferService(db_session, too_many).validate_archive(valid, Path(staging))

    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(valid) as source, zipfile.ZipFile(duplicate, "w") as target:
        for item in source.infolist():
            target.writestr(item.filename, source.read(item.filename))
        with pytest.warns(UserWarning, match="Duplicate name"):
            target.writestr("manifest.json", source.read("manifest.json"))
    with tempfile.TemporaryDirectory(dir=tmp_path) as staging, pytest.raises(AppError):
        TransferService(db_session, settings).validate_archive(duplicate, Path(staging))

    too_large = _settings(tmp_path / "storage", max_transfer_uncompressed_mb=1)
    oversized = tmp_path / "oversized.zip"
    with zipfile.ZipFile(oversized, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", b"{}")
        archive.writestr("assets/large.bin", b"x" * (1024 * 1024 + 1))
    with tempfile.TemporaryDirectory(dir=tmp_path) as staging, pytest.raises(AppError):
        TransferService(db_session, too_large).validate_archive(oversized, Path(staging))
