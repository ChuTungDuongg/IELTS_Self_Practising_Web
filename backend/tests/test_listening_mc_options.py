from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ListeningPart
from app.models import Test as DomainTest
from app.models import TestModule as ModuleRecord
from app.models import TestVersion as VersionRecord
from app.models.enums import ModuleType, VersionStatus
from app.schemas.content import QuestionGroupWrite
from app.services.listening import ListeningService


@pytest.mark.integration
async def test_listening_multiple_choice_option_deletion_round_trips_through_update(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="Listening MC option deletion")
    version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
    module = ModuleRecord(module_type=ModuleType.LISTENING, order_index=0)
    part = ListeningPart(title="Section 1", order_index=0)
    test.versions.append(version)
    version.modules.append(module)
    module.listening_parts.append(part)
    option_ids = [str(uuid4()) for _ in range(3)]
    question_id = uuid4()
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()

    service = ListeningService(db_session)
    created = await service.create_group(
        part.id,
        QuestionGroupWrite.model_validate(
            {
                "question_type": "multiple_choice",
                "instruction": "Choose one answer.",
                "config": {},
                "order_index": 0,
                "questions": [
                    {
                        "id": question_id,
                        "number": 1,
                        "prompt": "Fictional prompt",
                        "config": {
                            "options": [
                                {"id": option_ids[0], "label": "A", "text": "Alpha"},
                                {"id": option_ids[1], "label": "B", "text": "Beta"},
                                {"id": option_ids[2], "label": "C", "text": "Gamma"},
                            ]
                        },
                        "answer_key": {"kind": "SINGLE_OPTION", "value": option_ids[1]},
                        "order_index": 0,
                    }
                ],
            }
        ),
    )
    group_id = created.id
    await db_session.rollback()

    persisted = await service.get_group(group_id)
    update = QuestionGroupWrite.model_validate(persisted.model_dump(mode="json"))
    update.questions[0].config["options"] = [
        update.questions[0].config["options"][0],
        update.questions[0].config["options"][1],
    ]
    update.questions[0].config["options"][1]["label"] = "B"
    await db_session.rollback()

    updated = await service.update_group(group_id, update)
    await db_session.rollback()
    reloaded = await service.get_group(group_id)

    assert updated.id == group_id
    assert updated.questions[0].id == question_id
    assert [option["id"] for option in reloaded.questions[0].config["options"]] == option_ids[:2]
    assert [option["label"] for option in reloaded.questions[0].config["options"]] == ["A", "B"]
    assert reloaded.questions[0].answer_key["value"] == option_ids[1]
