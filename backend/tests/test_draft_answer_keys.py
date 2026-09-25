from pathlib import Path
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.schemas.content import QuestionGroupUpdate
from app.schemas.draft_import import DraftImportManifest
from app.services.draft_import import DraftImportService
from app.services.reading import ReadingService
from app.services.tests import TestService as LifecycleService


async def import_group(session, group):
    source = DraftImportManifest.model_validate(
        {
            "format": "ielts-draft-import-v1",
            "title": "Fictional unfinished draft",
            "allow_incomplete": True,
            "modules": [
                {
                    "type": "READING",
                    "passages": [
                        {
                            "title": "Fictional passage",
                            "blocks": [
                                {"type": "paragraph", "label": "A", "text": "Fictional content."}
                            ],
                            "question_groups": [group],
                        }
                    ],
                }
            ],
        }
    )
    result = await DraftImportService(session).import_manifest(source, Path.cwd())
    builder = await ReadingService(session).builder_version(result.version_id)
    return result.version_id, builder.modules[0].passages[0].question_groups[0]


async def save_group(session, group, *, keys=None, instruction=None):
    body = group.model_dump()
    if keys is not None:
        for question, key in zip(body["questions"], keys, strict=True):
            question["answer_key"] = key
    if instruction is not None:
        body["instruction"] = instruction
    await session.rollback()
    return await ReadingService(session).update_group(
        group.id, QuestionGroupUpdate.model_validate({**body, "expected_revision": group.revision})
    )


@pytest.mark.integration
async def test_empty_and_incremental_single_option_keys_remain_draft_saveable(db_session):
    version_id, group = await import_group(
        db_session,
        {
            "question_type": "multiple_choice",
            "questions": [
                {
                    "prompt": "Fictional question one",
                    "options": [{"key": "A", "text": "River"}, {"key": "B", "text": "Hill"}],
                },
                {
                    "prompt": "Fictional question two",
                    "options": [{"key": "A", "text": "River"}, {"key": "B", "text": "Hill"}],
                },
            ],
        },
    )
    ids = [question.id for question in group.questions]
    assert all(
        question.answer_key == {"kind": "SINGLE_OPTION", "value": ""}
        for question in group.questions
    )
    group = await save_group(db_session, group, instruction="Revised draft instruction")
    assert group.instruction == "Revised draft instruction"
    first_option = group.questions[0].config["options"][0]["id"]
    group = await save_group(
        db_session,
        group,
        keys=[
            {"kind": "SINGLE_OPTION", "value": first_option},
            {"kind": "SINGLE_OPTION", "value": ""},
        ],
    )
    assert [question.id for question in group.questions] == ids
    assert group.questions[0].answer_key["value"] == first_option
    assert group.questions[1].answer_key["value"] == ""
    validation = await LifecycleService(db_session).validate(version_id)
    assert not validation.valid
    assert any(
        issue.path == "reading.questions.2" and issue.message == "Answer key is incomplete."
        for issue in validation.errors
    )
    await db_session.rollback()
    with pytest.raises(AppError) as caught:
        await LifecycleService(db_session).publish(version_id)
    assert caught.value.code == "VALIDATION_FAILED"


@pytest.mark.integration
async def test_matching_q8_key_persists_and_clears_its_publish_validation_issue(db_session):
    version_id, group = await import_group(
        db_session,
        {
            "question_type": "matching",
            "options": [
                {"key": "A", "text": "Fictional date one"},
                {"key": "B", "text": "Fictional date two"},
            ],
            "questions": [
                {"prompt": f"Fictional event {number}", **({"answer": "A"} if number < 8 else {})}
                for number in range(1, 9)
            ],
        },
    )
    assert group.questions[7].answer_key == {"kind": "SINGLE_OPTION", "value": ""}
    before = await LifecycleService(db_session).validate(version_id)
    assert any(
        issue.path == "reading.questions.8" and issue.message == "Answer key is incomplete."
        for issue in before.errors
    )
    option_id = group.config["options"][1]["id"]
    question_ids = [question.id for question in group.questions]
    saved = await save_group(
        db_session,
        group,
        keys=[
            *(question.answer_key for question in group.questions[:7]),
            {"kind": "SINGLE_OPTION", "value": option_id},
        ],
    )
    assert [question.id for question in saved.questions] == question_ids
    assert saved.questions[7].answer_key == {"kind": "SINGLE_OPTION", "value": option_id}
    await db_session.rollback()
    reopened = (
        (await ReadingService(db_session).builder_version(version_id))
        .modules[0]
        .passages[0]
        .question_groups[0]
    )
    assert reopened.questions[7].answer_key["value"] == option_id
    after = await LifecycleService(db_session).validate(version_id)
    assert not any(issue.path == "reading.questions.8" for issue in after.errors)
    stale = await save_group(
        db_session,
        reopened,
        keys=[
            *(question.answer_key for question in reopened.questions[:7]),
            {"kind": "SINGLE_OPTION", "value": str(uuid4())},
        ],
    )
    assert stale.questions[7].answer_key["value"] not in {
        option["id"] for option in stale.config["options"]
    }
    stale_validation = await LifecycleService(db_session).validate(version_id)
    assert any(issue.path == "reading.questions.8" for issue in stale_validation.errors)


@pytest.mark.integration
async def test_matching_q5_to_q8_keys_survive_update_reload_and_lifecycle_validation(db_session):
    version_id, group = await import_group(
        db_session,
        {
            "question_type": "matching",
            "options": [
                {"key": "A", "text": "Fictional first date"},
                {"key": "B", "text": "Fictional second date"},
            ],
            "questions": [
                {"number": number, "prompt": f"Fictional event {number}"} for number in range(5, 9)
            ],
        },
    )
    option_ids = [option["id"] for option in group.config["options"]]
    selected = [option_ids[index % 2] for index in range(4)]
    ids = [question.id for question in group.questions]
    saved = await save_group(
        db_session,
        group,
        keys=[{"kind": "SINGLE_OPTION", "value": option_id} for option_id in selected],
    )
    assert [question.id for question in saved.questions] == ids
    assert [question.answer_key["value"] for question in saved.questions] == selected
    await db_session.rollback()
    retrieved = await ReadingService(db_session).get_group(group.id)
    fresh = (
        (await ReadingService(db_session).builder_version(version_id))
        .modules[0]
        .passages[0]
        .question_groups[0]
    )
    assert [question.answer_key["value"] for question in retrieved.questions] == selected
    assert [question.answer_key["value"] for question in fresh.questions] == selected
    validation = await LifecycleService(db_session).validate(version_id)
    assert not any(
        issue.path in {f"reading.questions.{number}" for number in range(5, 9)}
        and issue.message == "Answer key is incomplete."
        for issue in validation.errors
    )


@pytest.mark.integration
async def test_empty_text_key_survives_draft_update(db_session):
    version_id, group = await import_group(
        db_session,
        {
            "question_type": "short_answer",
            "questions": [{"prompt": "Fictional place", "max_words": 2}],
        },
    )
    assert group.questions[0].answer_key == {
        "kind": "TEXT",
        "accepted": [],
        "case_sensitive": False,
    }
    saved = await save_group(db_session, group, instruction="Corrected formatting")
    assert saved.questions[0].id == group.questions[0].id
    assert saved.questions[0].answer_key["accepted"] == []
    assert not (await LifecycleService(db_session).validate(version_id)).valid


@pytest.mark.integration
async def test_grouped_multi_select_keys_save_at_zero_one_and_two_official_choices(db_session):
    version_id, group = await import_group(
        db_session,
        {
            "question_type": "multiple_choice_multiple",
            "questions": [
                {
                    "prompt": "Choose fictional places",
                    "options": [{"key": key, "text": f"Place {key}"} for key in "ABCDE"],
                    "min_selections": 2,
                    "max_selections": 2,
                }
            ],
        },
    )
    question_id = group.questions[0].id
    values = [option["id"] for option in group.questions[0].config["options"]]
    assert group.questions[0].answer_key == {
        "kind": "MULTIPLE_OPTIONS",
        "values": [],
        "order_matters": False,
    }
    zero = await LifecycleService(db_session).validate(version_id)
    assert any(
        issue.message == "Select exactly 2 official answers before publishing."
        for issue in zero.errors
    )
    group = await save_group(
        db_session,
        group,
        keys=[{"kind": "MULTIPLE_OPTIONS", "values": [values[0]], "order_matters": False}],
    )
    assert group.questions[0].answer_key["values"] == [values[0]]
    one = await LifecycleService(db_session).validate(version_id)
    assert any(
        issue.message == "Select exactly 2 official answers before publishing."
        for issue in one.errors
    )
    group = await save_group(
        db_session,
        group,
        keys=[{"kind": "MULTIPLE_OPTIONS", "values": values[:2], "order_matters": False}],
    )
    assert group.questions[0].id == question_id
    two = await LifecycleService(db_session).validate(version_id)
    assert two.valid, two.errors


@pytest.mark.integration
async def test_content_only_draft_edit_preserves_imported_reading_number_gap(db_session):
    source = DraftImportManifest.model_validate(
        {
            "format": "ielts-draft-import-v1",
            "title": "Fictional gapped draft",
            "allow_incomplete": True,
            "modules": [
                {
                    "type": "READING",
                    "passages": [
                        {
                            "title": "Fictional passage",
                            "blocks": [
                                {"type": "paragraph", "label": "A", "text": "Fictional content."}
                            ],
                            "question_groups": [
                                {
                                    "question_type": "short_answer",
                                    "questions": [{"number": 1, "prompt": "First place"}],
                                },
                                {
                                    "question_type": "short_answer",
                                    "questions": [{"number": 14, "prompt": "Later place"}],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )
    result = await DraftImportService(db_session).import_manifest(source, Path.cwd())
    groups = (
        (await ReadingService(db_session).builder_version(result.version_id))
        .modules[0]
        .passages[0]
        .question_groups
    )
    first_id, later_id = (groups[0].questions[0].id, groups[1].questions[0].id)
    saved = await save_group(db_session, groups[1], instruction="Clarified instruction")
    refreshed = (
        (await ReadingService(db_session).builder_version(result.version_id))
        .modules[0]
        .passages[0]
        .question_groups
    )
    assert saved.questions[0].number == 14
    assert [(group.questions[0].id, group.questions[0].number) for group in refreshed] == [
        (first_id, 1),
        (later_id, 14),
    ]
    assert saved.questions[0].answer_key == {
        "kind": "TEXT",
        "accepted": [],
        "case_sensitive": False,
    }
