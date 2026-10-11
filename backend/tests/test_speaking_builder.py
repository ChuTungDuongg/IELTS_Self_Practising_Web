from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import UniqueConstraint

from app.models import SpeakingPart, SpeakingPrompt
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import ModuleType, SpeakingPromptType, VersionStatus
from app.schemas.content import BuilderModule, ModuleCreate
from app.schemas.speaking import BuilderSpeakingPart, SpeakingPromptWrite
from app.services.reading import ReadingService


def speaking_version():
    version = DomainVersion(
        id=uuid4(),
        test_id=uuid4(),
        version_number=1,
        status=VersionStatus.DRAFT,
        test=DomainTest(title="Fictional Speaking Builder"),
    )
    module = DomainModule(
        id=uuid4(),
        revision=1,
        module_type=ModuleType.SPEAKING,
        order_index=0,
    )
    version.modules.append(module)
    return version, module


def test_speaking_is_an_authored_module_type():
    assert ModuleCreate(module_type="SPEAKING").module_type == ModuleType.SPEAKING


def test_speaking_representation_and_stable_prompt_ids_across_reorder():
    _, module = speaking_version()
    for number in (1, 2, 3):
        module.speaking_parts.append(
            SpeakingPart(
                id=uuid4(),
                revision=1,
                part_number=number,
                order_index=number - 1,
            )
        )
    part = module.speaking_parts[0]
    for index in range(2):
        part.prompts.append(
            SpeakingPrompt(
                id=uuid4(),
                prompt_type=SpeakingPromptType.SHORT_ANSWER,
                prompt_text="Fictional prompt",
                preparation_seconds=0,
                response_seconds=60,
                config_json={},
                order_index=index,
            )
        )
    original_ids = [prompt.id for prompt in part.prompts]
    part.prompts.reverse()
    for index, prompt in enumerate(part.prompts):
        prompt.order_index = index
    dto = BuilderSpeakingPart.model_validate(part, from_attributes=True)
    assert [prompt.id for prompt in dto.prompts] == original_ids[::-1]
    assert [item.part_number for item in module.speaking_parts] == [1, 2, 3]


def test_duplicate_logical_parts_are_constrained_in_database_and_builder():
    constraints = SpeakingPart.__table__.constraints
    assert any(
        isinstance(item, UniqueConstraint)
        and list(item.columns.keys()) == ["module_id", "part_number"]
        for item in constraints
    )
    data = dict(
        id=uuid4(),
        revision=1,
        module_type="SPEAKING",
        title=None,
        recommended_duration_seconds=None,
        passages=[],
        listening_parts=[],
    )
    part = dict(id=uuid4(), revision=1, part_number=1, order_index=0, prompts=[])
    with pytest.raises(ValidationError, match="part numbers"):
        BuilderModule(**data, speaking_parts=[part, {**part, "id": uuid4()}])


def test_incomplete_draft_is_serialized_in_existing_builder():
    version, module = speaking_version()
    module.speaking_parts.append(
        SpeakingPart(
            id=uuid4(),
            revision=1,
            part_number=2,
            order_index=0,
        )
    )
    result = ReadingService._present_version(version)
    assert result.modules[0].speaking_parts[0].part_number == 2
    assert result.modules[0].speaking_parts[0].prompts == []


@pytest.mark.parametrize("kind", ["READING", "LISTENING", "WRITING"])
def test_existing_module_serialization_remains_compatible(kind):
    module = BuilderModule(
        id=uuid4(),
        revision=1,
        module_type=kind,
        title=None,
        recommended_duration_seconds=None,
        passages=[],
        listening_parts=[],
    )
    assert module.speaking_parts == []
    assert module.writing_tasks == []
    assert module.model_dump()["module_type"] == kind


def test_prompt_config_is_bounded_and_draft_text_may_be_empty():
    draft = SpeakingPromptWrite(prompt_type="LONG_TURN", prompt_text="")
    assert draft.preparation_seconds == 60
    assert draft.response_seconds == 120
    with pytest.raises(ValidationError):
        SpeakingPromptWrite(prompt_type="LONG_TURN", config_json={"cue_points": ["x"] * 13})
    with pytest.raises(ValidationError):
        SpeakingPromptWrite(prompt_type="SHORT_ANSWER", config_json={"unexpected": "data"})


@pytest.mark.integration
async def test_authored_speaking_persists_and_builder_loads_incomplete_draft(db_session):
    version, module = speaking_version()
    version.test_id = None
    module.speaking_parts.append(SpeakingPart(part_number=1, order_index=0))
    async with db_session.begin():
        db_session.add(version)
        await db_session.flush()
        version_id = version.id
        part_id = module.speaking_parts[0].id
    loaded = await ReadingService(db_session).builder_version(version_id)
    assert loaded.modules[0].speaking_parts[0].id == part_id
    assert loaded.modules[0].speaking_parts[0].prompts == []


@pytest.mark.integration
async def test_database_rejects_duplicate_logical_speaking_part(db_session):
    from sqlalchemy.exc import IntegrityError

    version, module = speaking_version()
    version.test_id = None
    module.speaking_parts.extend(
        [
            SpeakingPart(part_number=1, order_index=0),
            SpeakingPart(part_number=1, order_index=1),
        ]
    )
    with pytest.raises(IntegrityError, match="speaking_parts_module_id_part_number"):
        async with db_session.begin():
            db_session.add(version)
            await db_session.flush()
