from uuid import UUID, uuid4

import httpx
import pytest

from app.main import app
from app.models import AttemptAnswer, Question, QuestionGroup, ReadingPassage
from app.schemas.content import HighlightCreate
from app.services.attempts import AttemptService


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
    assert "/api/v1/history" in paths
    assert "/api/v1/test-modules/{module_id}/question-groups/order" in paths
    exam_question = document["components"]["schemas"]["ExamQuestion"]
    assert "answer_key" not in exam_question["properties"]


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
