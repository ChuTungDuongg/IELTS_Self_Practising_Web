from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import AttemptAnswer, Question, QuestionGroup, ReadingPassage
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import ModuleType, VersionStatus
from app.schemas.content import HighlightCreate, QuestionGroupWrite
from app.services.attempts import AttemptService
from app.services.reading import ReadingService


@pytest.mark.asyncio
async def test_health_endpoint_reports_server_time() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "server_time" in response.json()


@pytest.mark.asyncio
async def test_openapi_exposes_phase_one_routes() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        document = (await client.get("/openapi.json")).json()
    paths = document["paths"]
    assert "/api/v1/tests" in paths
    assert "/api/v1/test-versions/{version_id}/publish" in paths
    assert "/api/v1/attempts/{attempt_id}/answers/{question_id}" in paths
    assert "delete" in paths["/api/v1/attempts/{attempt_id}"]
    assert "/api/v1/attempts/{attempt_id}/pause" in paths
    assert "/api/v1/attempts/{attempt_id}/resume" in paths
    assert "/api/v1/history" in paths
    assert "/api/v1/test-modules/{module_id}/question-groups/order" in paths
    assert "/api/v1/listening/modules/{module_id}/audio" in paths
    assert "/api/v1/writing/tasks/{task_id}" in paths
    assert "/api/v1/attempts/{attempt_id}/writing/{writing_task_id}" in paths
    assert "/api/v1/attempts/{attempt_id}/writing-review" in paths
    assert "/api/v1/attempts/{attempt_id}/writing-score" in paths
    exam_question = document["components"]["schemas"]["ExamQuestion"]
    assert "answer_key" not in exam_question["properties"]
    exam_writing_task = document["components"]["schemas"]["ExamWritingTask"]
    assert "answer_key" not in exam_writing_task["properties"]


def test_active_exam_normalizes_legacy_content_without_exposing_answer_keys() -> None:
    passage = ReadingPassage(
        id=uuid4(),
        title="Fictional passage",
        order_index=0,
        content_json=[{"id": "legacy-a", "type": "paragraph", "text": "Text"}],
        plain_text="Text",
    )
    group = QuestionGroup(
        id=uuid4(),
        question_type="matching_headings",
        instruction="Match",
        config={
            "options": [
                {"id": "i", "label": "First"},
                {"id": "ii", "label": "Second"},
            ]
        },
        order_index=0,
    )
    question = Question(
        id=uuid4(),
        number=1,
        prompt="Paragraph A",
        config={"target_label": "Paragraph A"},
        answer_key={"type": "single_choice", "accepted": ["ii"]},
        order_index=0,
    )
    group.questions.append(question)
    passage.question_groups.append(group)

    payload = AttemptService._present_exam_passage(
        passage, {question.id: "ii"}, {question.id: True}
    ).model_dump(mode="json")
    assert payload["blocks"][0]["label"] == "A"
    assert (
        payload["question_groups"][0]["questions"][0]["config"]["target_block_id"]
        == payload["blocks"][0]["id"]
    )
    assert "answer_key" not in payload["question_groups"][0]["questions"][0]
    assert payload["question_groups"][0]["config"]["options"][1]["label"] == "ii"
    assert (
        payload["question_groups"][0]["questions"][0]["value"]
        == payload["question_groups"][0]["config"]["options"][1]["id"]
    )
    assert payload["question_groups"][0]["questions"][0]["flagged"] is True
    AttemptService._validate_highlight(
        passage,
        HighlightCreate(
            passage_id=passage.id,
            start_block_id=payload["blocks"][0]["id"],
            start_offset=0,
            end_block_id=payload["blocks"][0]["id"],
            end_offset=4,
            selected_text="Text",
        ),
    )


def test_finalized_review_normalizes_legacy_heading_value_and_key() -> None:
    passage = ReadingPassage(
        id=uuid4(),
        title="Fictional passage",
        order_index=0,
        content_json=[{"id": "legacy-a", "type": "paragraph", "text": "Text"}],
        plain_text="Text",
    )
    group = QuestionGroup(
        id=uuid4(),
        question_type="matching_headings",
        instruction="Match",
        config={"options": [{"id": "i", "label": "First"}, {"id": "ii", "label": "Second"}]},
        order_index=0,
    )
    question = Question(
        id=uuid4(),
        number=1,
        prompt="Paragraph A",
        config={"target_label": "Paragraph A"},
        answer_key={"type": "single_choice", "accepted": ["ii"]},
        order_index=0,
    )
    group.questions.append(question)
    passage.question_groups.append(group)
    answer = AttemptAnswer(
        question_id=question.id,
        question=question,
        value="ii",
        is_correct=True,
    )

    payload = AttemptService._present_review_answer(answer).model_dump(mode="json")

    assert payload["value"] == payload["answer_key"]["value"]
    assert payload["answer_key"]["kind"] == "SINGLE_OPTION"
    assert payload["value"] != "ii"
    assert UUID(payload["value"])


def test_yes_no_not_given_round_trips_canonical_values_without_active_key_leak() -> None:
    group = QuestionGroup(
        id=uuid4(),
        question_type="yes_no_not_given",
        instruction="",
        config={},
        order_index=0,
    )
    question = Question(
        id=uuid4(),
        number=1,
        prompt="The writer supports the proposal.",
        config={},
        answer_key={"kind": "SINGLE_OPTION", "value": "NOT GIVEN"},
        order_index=0,
    )
    group.questions.append(question)

    active = AttemptService._present_exam_group(
        group, {question.id: "not given"}, {question.id: False}, []
    ).model_dump(mode="json")
    assert active["questions"][0]["value"] == "NOT_GIVEN"
    assert "answer_key" not in active["questions"][0]

    answer = AttemptAnswer(
        question_id=question.id,
        question=question,
        value="not given",
        is_correct=True,
    )
    review = AttemptService._present_review_answer(answer).model_dump(mode="json")
    assert review["value"] == "NOT_GIVEN"
    assert review["answer_key"]["value"] == "NOT_GIVEN"


@pytest.mark.integration
async def test_yes_no_not_given_persists_and_reloads_through_builder_service(
    db_session: AsyncSession,
) -> None:
    test = DomainTest(title="YNNG round trip")
    version = DomainVersion(id=uuid4(), version_number=1, status=VersionStatus.DRAFT)
    module = DomainModule(id=uuid4(), module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        id=uuid4(),
        title="Passage",
        order_index=0,
        content_json=[
            {"id": str(uuid4()), "type": "paragraph", "label": "A", "text": "Fictional text."}
        ],
        plain_text="Fictional text.",
    )
    test.versions.append(version)
    version.modules.append(module)
    module.passages.append(passage)
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()

    created = await ReadingService(db_session).create_group(
        passage.id,
        QuestionGroupWrite(
            question_type="yes_no_not_given",
            instruction="",
            config={},
            order_index=0,
            questions=[
                {
                    "id": uuid4(),
                    "number": 1,
                    "prompt": "Claim",
                    "config": {},
                    "answer_key": {"kind": "SINGLE_OPTION", "value": "NOT GIVEN"},
                    "order_index": 0,
                }
            ],
        ),
    )
    version_id = version.id
    await db_session.rollback()
    reloaded = await ReadingService(db_session).builder_version(version_id)
    reloaded_group = reloaded.modules[0].passages[0].question_groups[0]

    assert created.question_type == "yes_no_not_given"
    assert created.questions[0].answer_key["value"] == "NOT_GIVEN"
    assert reloaded_group.question_type == "yes_no_not_given"
    assert reloaded_group.questions[0].answer_key["value"] == "NOT_GIVEN"
