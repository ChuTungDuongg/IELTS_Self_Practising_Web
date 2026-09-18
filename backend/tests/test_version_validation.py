from uuid import uuid4

from app.models import Question, QuestionGroup, ReadingPassage
from app.models import TestModule as ModuleRecord
from app.models import TestVersion as VersionRecord
from app.models.enums import ModuleType, VersionStatus
from app.services.tests import TestService as VersionService


def test_empty_version_is_invalid() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    result = VersionService.validate_version(version)
    assert not result.valid
    assert result.errors[0].path == "modules"


def test_reading_module_requires_content() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    version.modules.append(ModuleRecord(module_type=ModuleType.READING, order_index=0))
    result = VersionService.validate_version(version)
    assert not result.valid
    assert result.errors[0].path == "reading"


def test_reading_passage_satisfies_phase_one_content_rule() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    module.passages.append(
        ReadingPassage(title="Fictional passage", order_index=0, content_json=[], plain_text="Text")
    )
    version.modules.append(module)
    assert VersionService.validate_version(version).valid


def test_publish_validation_rejects_answer_key_outside_mcq_options() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional passage", order_index=0, content_json=[], plain_text="Text"
    )
    group = QuestionGroup(
        question_type="multiple_choice", instruction="Choose one", config={}, order_index=0
    )
    group.questions.append(
        Question(
            number=1,
            prompt="Question",
            config={"options": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}]},
            answer_key={"type": "single_choice", "accepted": ["C"]},
            order_index=0,
        )
    )
    passage.question_groups.append(group)
    module.passages.append(passage)
    module.question_groups.append(group)
    version.modules.append(module)
    result = VersionService.validate_version(version)
    assert not result.valid
    assert "available option" in result.errors[0].message


def test_publish_validation_rejects_duplicate_numbers_across_groups() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional passage", order_index=0, content_json=[], plain_text="Text"
    )
    for order_index in range(2):
        group = QuestionGroup(
            question_type="true_false_not_given",
            instruction="Choose",
            config={},
            order_index=order_index,
        )
        group.questions.append(
            Question(
                number=1,
                prompt="Statement",
                config={},
                answer_key={"kind": "SINGLE_OPTION", "value": "TRUE"},
                order_index=0,
            )
        )
        passage.question_groups.append(group)
        module.question_groups.append(group)
    module.passages.append(passage)
    version.modules.append(module)
    result = VersionService.validate_version(version)
    assert not result.valid
    assert any("duplicates: 1" in issue.message for issue in result.errors)


def test_publish_validation_rejects_question_number_gaps() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional passage", order_index=0, content_json=[], plain_text="Text"
    )
    group = QuestionGroup(
        question_type="true_false_not_given", instruction="Choose", config={}, order_index=0
    )
    for order_index, number in enumerate([1, 3]):
        group.questions.append(
            Question(
                number=number,
                prompt="Statement",
                config={},
                answer_key={"kind": "SINGLE_OPTION", "value": "TRUE"},
                order_index=order_index,
            )
        )
    passage.question_groups.append(group)
    module.passages.append(passage)
    module.question_groups.append(group)
    version.modules.append(module)
    result = VersionService.validate_version(version)
    assert not result.valid
    assert any("canonical sequence" in issue.message for issue in result.errors)


def test_publish_validation_uses_passage_presentation_order_for_numbering() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    for passage_order, number in [(0, 2), (1, 1)]:
        passage = ReadingPassage(
            id=uuid4(),
            title=f"Fictional passage {passage_order + 1}",
            order_index=passage_order,
            content_json=[],
            plain_text="Text",
        )
        group = QuestionGroup(
            id=uuid4(),
            question_type="true_false_not_given",
            instruction="Choose",
            config={},
            order_index=passage_order,
        )
        group.questions.append(
            Question(
                number=number,
                prompt="Statement",
                config={},
                answer_key={"kind": "SINGLE_OPTION", "value": "TRUE"},
                order_index=0,
            )
        )
        passage.question_groups.append(group)
        module.passages.append(passage)
        module.question_groups.append(group)
    version.modules.append(module)

    result = VersionService.validate_version(version)

    assert not result.valid
    assert any("canonical sequence" in issue.message for issue in result.errors)


def test_publish_validation_rejects_orphaned_reading_group() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    module.passages.append(
        ReadingPassage(
            id=uuid4(),
            title="Fictional passage",
            order_index=0,
            content_json=[],
            plain_text="Text",
        )
    )
    group = QuestionGroup(
        id=uuid4(),
        passage_id=uuid4(),
        question_type="true_false_not_given",
        instruction="Choose",
        config={},
        order_index=0,
    )
    group.questions.append(
        Question(
            number=1,
            prompt="Statement",
            config={},
            answer_key={"kind": "SINGLE_OPTION", "value": "TRUE"},
            order_index=0,
        )
    )
    module.question_groups.append(group)
    version.modules.append(module)

    result = VersionService.validate_version(version)

    assert not result.valid
    assert any("available passage" in issue.message for issue in result.errors)


def test_publish_validation_rejects_duplicate_paragraph_labels() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    module.passages.append(
        ReadingPassage(
            title="Fictional passage",
            order_index=0,
            content_json=[
                {"id": str(uuid4()), "type": "paragraph", "label": "A", "text": "One"},
                {"id": str(uuid4()), "type": "paragraph", "label": "A", "text": "Two"},
            ],
            plain_text="One\n\nTwo",
        )
    )
    version.modules.append(module)
    result = VersionService.validate_version(version)
    assert not result.valid
    assert any("Paragraph labels must be unique" in issue.message for issue in result.errors)


def test_publish_validation_rejects_duplicate_block_ids() -> None:
    block_id = str(uuid4())
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    module.passages.append(
        ReadingPassage(
            title="Fictional passage",
            order_index=0,
            content_json=[
                {"id": block_id, "type": "paragraph", "label": "A", "text": "One"},
                {"id": block_id, "type": "paragraph", "label": "B", "text": "Two"},
            ],
            plain_text="One\n\nTwo",
        )
    )
    version.modules.append(module)
    result = VersionService.validate_version(version)
    assert not result.valid
    assert any("Passage block IDs must be unique" in issue.message for issue in result.errors)


def test_publish_validation_reports_malformed_legacy_block_instead_of_raising() -> None:
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    module.passages.append(
        ReadingPassage(
            title="Fictional passage",
            order_index=0,
            content_json=["not-a-block"],
            plain_text="Text",
        )
    )
    version.modules.append(module)
    result = VersionService.validate_version(version)
    assert not result.valid
    assert any("Invalid passage block configuration" in issue.message for issue in result.errors)


def _matching_version(*, target_block_id: str, heading_answer_id: str) -> VersionRecord:
    block_id = uuid4()
    heading_id = uuid4()
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional passage",
        order_index=0,
        content_json=[{"id": str(block_id), "type": "paragraph", "label": "A", "text": "Text"}],
        plain_text="Text",
    )
    group = QuestionGroup(
        question_type="matching_headings",
        instruction="Match",
        config={
            "options": [
                {"id": str(heading_id), "label": "i", "text": "First"},
                {"id": str(uuid4()), "label": "ii", "text": "Second"},
            ],
            "allow_option_reuse": False,
        },
        order_index=0,
    )
    group.questions.append(
        Question(
            number=1,
            prompt="Choose a heading",
            config={"target_block_id": target_block_id or str(block_id)},
            answer_key={"kind": "SINGLE_OPTION", "value": heading_answer_id or str(heading_id)},
            order_index=0,
        )
    )
    passage.question_groups.append(group)
    module.passages.append(passage)
    module.question_groups.append(group)
    version.modules.append(module)
    return version


def test_publish_validation_rejects_dangling_paragraph_reference() -> None:
    version = _matching_version(target_block_id=str(uuid4()), heading_answer_id="")
    result = VersionService.validate_version(version)
    assert not result.valid
    assert any("available block" in issue.message for issue in result.errors)


def test_publish_validation_rejects_dangling_heading_reference() -> None:
    version = _matching_version(target_block_id="", heading_answer_id=str(uuid4()))
    result = VersionService.validate_version(version)
    assert not result.valid
    assert any("available heading" in issue.message for issue in result.errors)
