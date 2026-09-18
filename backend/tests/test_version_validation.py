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
