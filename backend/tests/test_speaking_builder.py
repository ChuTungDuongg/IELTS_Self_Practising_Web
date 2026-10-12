from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import UniqueConstraint

from app.core.exceptions import AppError
from app.models import SpeakingPart, SpeakingPrompt
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import ModuleType, SpeakingPromptType, VersionStatus
from app.schemas.content import BuilderModule, ModuleCreate
from app.schemas.speaking import (
    BuilderSpeakingPart,
    SpeakingPartUpdate,
    SpeakingPartWrite,
    SpeakingPromptCreate,
    SpeakingPromptOrderWrite,
    SpeakingPromptWrite,
)
from app.services.reading import ReadingService
from app.services.speaking_builder import SpeakingBuilderService, validate_speaking_module
from app.services.tests import TestService as ContentTestService


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


async def initialized_speaking(session):
    test = DomainTest(title="Fictional authored interview")
    version = DomainVersion(version_number=1, status=VersionStatus.DRAFT)
    test.versions.append(version)
    async with session.begin():
        session.add(test)
        await session.flush()
        version_id = version.id
        test_id = test.id
    module = await ReadingService(session).create_module(
        version_id, ModuleCreate(module_type="SPEAKING")
    )
    await session.rollback()
    return test_id, version_id, module


@pytest.mark.integration
async def test_module_defaults_append_reorder_timers_update_and_delete(db_session):
    _, _, module = await initialized_speaking(db_session)
    assert [part.part_number for part in module.speaking_parts] == [1, 2, 3]
    long_turn = module.speaking_parts[1].prompts[0]
    assert (long_turn.preparation_seconds, long_turn.response_seconds) == (60, 120)
    service = SpeakingBuilderService(db_session)
    part = module.speaking_parts[0]
    part = await service.create_prompt(
        part.id, SpeakingPromptCreate(expected_revision=part.revision, prompt_type="SHORT_ANSWER")
    )
    part = await service.create_prompt(
        part.id,
        SpeakingPromptCreate(
            expected_revision=part.revision,
            prompt_type="SHORT_ANSWER",
            prompt_text="Describe a fictional hobby.",
            response_seconds=45,
        ),
    )
    ids = [item.id for item in part.prompts]
    assert [item.order_index for item in part.prompts] == [0, 1]
    assert [item.response_seconds for item in part.prompts] == [60, 45]
    part = await service.reorder_prompts(
        part.id, SpeakingPromptOrderWrite(expected_revision=part.revision, prompt_ids=ids[::-1])
    )
    assert [item.id for item in part.prompts] == ids[::-1]
    assert [item.order_index for item in part.prompts] == [0, 1]
    payload = part.model_dump(exclude={"id", "revision", "order_index", "part_number"})
    payload["prompts"][0]["prompt_text"] = "Updated fictional question."
    part = await service.update_part(
        part.id, SpeakingPartUpdate(expected_revision=part.revision, **payload)
    )
    assert part.prompts[0].id == ids[1]
    assert part.prompts[0].prompt_text == "Updated fictional question."
    part = await service.delete_prompt(part.id, ids[1], expected_revision=part.revision)
    assert [item.id for item in part.prompts] == [ids[0]]
    assert part.prompts[0].order_index == 0


@pytest.mark.integration
async def test_part_two_cue_points_and_optional_followups(db_session):
    _, _, module = await initialized_speaking(db_session)
    part = module.speaking_parts[1]
    payload = part.model_dump(exclude={"id", "revision", "order_index", "part_number"})
    payload["prompts"][0].update(
        prompt_text="Describe a fictional tool.",
        config_json={"cue_points": ["What it does", "Why it helps"]},
        preparation_seconds=40,
        response_seconds=100,
    )
    service = SpeakingBuilderService(db_session)
    part = await service.update_part(
        part.id, SpeakingPartUpdate(expected_revision=part.revision, **payload)
    )
    part = await service.create_prompt(
        part.id,
        SpeakingPromptCreate(
            expected_revision=part.revision,
            prompt_type="FOLLOW_UP",
            prompt_text="Would you share it?",
        ),
    )
    assert part.prompts[0].config_json.cue_points == ["What it does", "Why it helps"]
    assert (part.prompts[0].preparation_seconds, part.prompts[0].response_seconds) == (40, 100)
    assert part.prompts[1].prompt_type == SpeakingPromptType.FOLLOW_UP


def complete_speaking():
    version, module = speaking_version()
    for number in (1, 2, 3):
        part = SpeakingPart(id=uuid4(), revision=1, part_number=number, order_index=number - 1)
        module.speaking_parts.append(part)
        part.prompts.append(
            SpeakingPrompt(
                id=uuid4(),
                prompt_type=SpeakingPromptType.LONG_TURN
                if number == 2
                else SpeakingPromptType.SHORT_ANSWER,
                prompt_text="Discuss a fictional object.",
                preparation_seconds=60 if number == 2 else 0,
                response_seconds=120 if number == 2 else 60,
                config_json={"cue_points": ["Its purpose"]} if number == 2 else {},
                order_index=0,
            )
        )
    return version, module


def test_complete_speaking_passes_shared_publish_validation():
    version, module = complete_speaking()
    assert validate_speaking_module(module) == []
    assert ContentTestService.validate_version(version).valid


@pytest.mark.parametrize(
    "malformation",
    [
        "missing_part",
        "duplicate_part",
        "missing_main",
        "duplicate_main",
        "illegal_type",
        "empty_text",
        "response_timer",
        "preparation_timer",
        "duplicate_order",
        "stale_order",
        "invalid_config",
        "empty_cue",
    ],
)
def test_complete_validation_rejects_malformed_speaking(malformation):
    version, module = complete_speaking()
    part = module.speaking_parts[1]
    main = part.prompts[0]
    if malformation == "missing_part":
        module.speaking_parts.pop()
    elif malformation == "duplicate_part":
        module.speaking_parts[2].part_number = 1
    elif malformation == "missing_main":
        part.prompts.clear()
    elif malformation == "duplicate_main":
        part.prompts.append(
            SpeakingPrompt(
                id=uuid4(),
                prompt_type="LONG_TURN",
                prompt_text="Another",
                preparation_seconds=60,
                response_seconds=120,
                config_json={},
                order_index=1,
            )
        )
    elif malformation == "illegal_type":
        module.speaking_parts[0].prompts[0].prompt_type = "FOLLOW_UP"
    elif malformation == "empty_text":
        main.prompt_text = "  "
    elif malformation == "response_timer":
        main.response_seconds = 0
    elif malformation == "preparation_timer":
        main.preparation_seconds = 0
    elif malformation == "duplicate_order":
        module.speaking_parts[2].order_index = 0
    elif malformation == "stale_order":
        main.order_index = 7
    elif malformation == "invalid_config":
        main.config_json = {"cue_points": "bad"}
    elif malformation == "empty_cue":
        main.config_json = {"cue_points": [""]}
    result = ContentTestService.validate_version(version)
    assert not result.valid
    assert any(issue.path.startswith("speaking") for issue in result.errors)


@pytest.mark.integration
async def test_draft_part_crud_and_revision_conflict(db_session):
    _, _, module = await initialized_speaking(db_session)
    service = SpeakingBuilderService(db_session)
    part = module.speaking_parts[2]
    await service.delete_part(part.id, expected_revision=part.revision)
    created = await service.create_part(module.id, SpeakingPartWrite(part_number=3))
    assert created.prompts == []
    with pytest.raises(AppError) as caught:
        await service.create_prompt(
            created.id, SpeakingPromptCreate(expected_revision=99, prompt_type="SHORT_ANSWER")
        )
    assert caught.value.code == "DRAFT_REVISION_CONFLICT"


@pytest.mark.integration
@pytest.mark.parametrize("restriction", ["other_teacher", "user", "published", "pending"])
async def test_speaking_mutations_reuse_governance(db_session, restriction):

    from app.models import TestVersionModeration, User
    from app.models.enums import ModerationScope, ModerationStatus, UserRole

    _, version_id, module = await initialized_speaking(db_session)
    part = module.speaking_parts[0]
    actor = db_session.info["current_user_identity"]
    async with db_session.begin():
        version = await db_session.get(DomainVersion, version_id)
        if restriction == "published":
            version.status = VersionStatus.PUBLISHED
        elif restriction == "pending":
            db_session.add(
                TestVersionModeration(
                    test_version_id=version_id,
                    scope=ModerationScope.PUBLIC,
                    status=ModerationStatus.PENDING,
                    submitted_by_user_id=actor.id,
                )
            )
        else:
            actor = User(
                id=uuid4(),
                email=f"speaking-{uuid4()}@example.com",
                display_name="Other actor",
                role=UserRole.TEACHER if restriction == "other_teacher" else UserRole.USER,
                is_active=True,
            )
            db_session.add(actor)
        await db_session.flush()
    with pytest.raises(AppError) as caught:
        await SpeakingBuilderService(db_session, actor=actor).create_prompt(
            part.id,
            SpeakingPromptCreate(expected_revision=part.revision, prompt_type="SHORT_ANSWER"),
        )
    assert (
        caught.value.code
        == {
            "other_teacher": "TEST_OWNERSHIP_REQUIRED",
            "user": "TEACHER_REQUIRED",
            "published": "TEST_VERSION_IMMUTABLE",
            "pending": "VERSION_MODERATION_PENDING",
        }[restriction]
    )


@pytest.mark.integration
async def test_owned_teacher_draft_is_editable_and_cannot_publish_directly(db_session):
    from app.models import User
    from app.models.enums import TestOrigin, UserRole

    _, version_id, module = await initialized_speaking(db_session)
    async with db_session.begin():
        teacher = User(
            email=f"speaking-owner-{uuid4()}@example.com",
            display_name="Owner",
            role=UserRole.TEACHER,
            is_active=True,
        )
        db_session.add(teacher)
        await db_session.flush()
        version = await db_session.get(DomainVersion, version_id)
        test = await db_session.get(DomainTest, version.test_id)
        test.owner_user_id = teacher.id
        test.origin = TestOrigin.TEACHER
    part = module.speaking_parts[0]
    saved = await SpeakingBuilderService(db_session, actor=teacher).create_prompt(
        part.id, SpeakingPromptCreate(expected_revision=part.revision, prompt_type="SHORT_ANSWER")
    )
    assert len(saved.prompts) == 1
    with pytest.raises(AppError, match="Administrator"):
        await ContentTestService(db_session, actor=teacher).publish(version_id)


@pytest.mark.integration
async def test_speaking_builder_routes_use_authenticated_mutations(db_session, authenticated_admin):
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_session
    from app.main import app

    _, _, module = await initialized_speaking(db_session)
    part = module.speaking_parts[0]

    async def session_override():
        yield db_session

    app.dependency_overrides[get_session] = session_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/speaking/parts/{part.id}/prompts",
                json={
                    "expected_revision": part.revision,
                    "prompt_type": "SHORT_ANSWER",
                    "prompt_text": "A fictional question",
                },
            )
            assert response.status_code == 201
            saved = response.json()
            assert saved["prompts"][0]["response_seconds"] == 60
            updated = await client.put(
                f"/api/v1/speaking/parts/{part.id}/prompts/{saved['prompts'][0]['id']}",
                json={
                    "expected_revision": saved["revision"],
                    "prompt_type": "SHORT_ANSWER",
                    "prompt_text": "Updated fictional question",
                    "response_seconds": 45,
                },
            )
            assert updated.status_code == 200
            saved = updated.json()
            assert saved["prompts"][0]["response_seconds"] == 45
            deleted = await client.delete(
                f"/api/v1/speaking/parts/{part.id}/prompts/{saved['prompts'][0]['id']}?expected_revision={saved['revision']}"
            )
            assert deleted.status_code == 200
            assert deleted.json()["prompts"] == []
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_speaking_attempt_and_assignment_require_prompt_timers():
    from app.schemas.attempts import AttemptCreate
    from app.schemas.classroom_assignments import AssignmentStart

    with pytest.raises(ValidationError):
        AttemptCreate(
            test_version_id=uuid4(),
            module="SPEAKING",
            timer={"mode": "COUNTDOWN", "duration_seconds": 600},
        )
    with pytest.raises(ValidationError):
        AssignmentStart(mode="MODULE", module="SPEAKING", timer={"mode": "COUNTDOWN", "duration_seconds": 600})
    attempt = AttemptCreate(test_version_id=uuid4(), module="SPEAKING", timer={"mode": "COUNT_UP"})
    assignment = AssignmentStart(mode="MODULE", module="SPEAKING", timer={"mode": "COUNT_UP"})
    assert attempt.speaking_mode == assignment.speaking_mode == "PRACTICE"


async def test_analytics_exposes_all_four_skills_after_speaking_integration():
    from unittest.mock import AsyncMock

    from app.services.analytics import AnalyticsService

    service = AnalyticsService(None, user_id=uuid4())
    service._attempts = AsyncMock(return_value=[])
    service._sessions = AsyncMock(return_value=[])
    dashboard = await service.dashboard()
    assert set(dashboard.bands) == {"READING", "LISTENING", "WRITING", "SPEAKING"}
