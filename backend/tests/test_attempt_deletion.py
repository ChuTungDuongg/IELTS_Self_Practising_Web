from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.main import app
from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptEvent,
    AttemptWritingResponse,
    AttemptWritingScore,
    Highlight,
    Question,
    QuestionFlag,
    QuestionGroup,
    ReadingPassage,
    WritingTask,
)
from app.models import Test as DomainTest
from app.models import TestModule as DomainModule
from app.models import TestVersion as DomainVersion
from app.models.enums import AttemptStatus, EventType, ModuleType, TimerMode, VersionStatus


async def _seed_attempt_with_owned_data(
    session: AsyncSession, status: AttemptStatus
) -> dict[str, UUID]:
    now = datetime.now(UTC)
    version_id = uuid4()
    passage_id = uuid4()
    question_id = uuid4()
    writing_task_id = uuid4()
    attempt_id = uuid4()
    sibling_id = uuid4()

    test = DomainTest(title="Fictional deletion test")
    version = DomainVersion(
        id=version_id,
        version_number=1,
        status=VersionStatus.PUBLISHED,
        published_at=now,
    )
    reading_module = DomainModule(module_type=ModuleType.READING, order_index=0)
    writing_module = DomainModule(module_type=ModuleType.WRITING, order_index=1)
    passage = ReadingPassage(
        id=passage_id,
        title="Fictional passage",
        order_index=0,
        content_json=[{"id": str(uuid4()), "type": "paragraph", "text": "Sample text."}],
        plain_text="Sample text.",
    )
    group = QuestionGroup(
        question_type="short_answer",
        instruction="Answer briefly.",
        config={},
        order_index=0,
    )
    question = Question(
        id=question_id,
        number=1,
        prompt="Sample question",
        config={},
        answer_key={"kind": "TEXT", "accepted": ["sample"]},
        order_index=0,
    )
    writing_task = WritingTask(
        id=writing_task_id,
        task_number=1,
        prompt="Write about a fictional topic.",
        order_index=0,
    )
    test.versions.append(version)
    version.modules.extend([reading_module, writing_module])
    reading_module.passages.append(passage)
    reading_module.question_groups.append(group)
    group.passage = passage
    group.questions.append(question)
    writing_module.writing_tasks.append(writing_task)

    attempt = Attempt(
        id=attempt_id,
        test_version=version,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=now,
        last_active_at=now,
        status=status,
    )
    sibling = Attempt(
        id=sibling_id,
        test_version=version,
        module_type=ModuleType.READING,
        timer_mode=TimerMode.COUNT_UP,
        started_at=now,
        last_active_at=now,
        status=AttemptStatus.IN_PROGRESS,
    )
    async with session.begin():
        session.add(test)
        await session.flush()
        session.add_all([attempt, sibling])
        await session.flush()
        session.add_all(
            [
                AttemptAnswer(
                    attempt_id=attempt_id,
                    question_id=question_id,
                    value="sample",
                    is_correct=True,
                ),
                AttemptWritingResponse(
                    attempt_id=attempt_id,
                    writing_task_id=writing_task_id,
                    content="Fictional response.",
                    word_count=2,
                ),
                AttemptWritingScore(
                    attempt_id=attempt_id,
                    writing_task_id=writing_task_id,
                    ta=Decimal("7.0"),
                    cc=Decimal("7.0"),
                    lr=Decimal("7.0"),
                    gra=Decimal("7.0"),
                ),
                Highlight(
                    attempt_id=attempt_id,
                    target_kind="PASSAGE",
                    target_id=passage_id,
                    passage_id=passage_id,
                    start_offset=0,
                    end_offset=6,
                    selected_text="Sample",
                ),
                QuestionFlag(
                    attempt_id=attempt_id,
                    question_id=question_id,
                    flagged=True,
                ),
                AttemptEvent(
                    attempt_id=attempt_id,
                    event_type=EventType.ANSWER_CHANGED,
                    question_id=question_id,
                    event_metadata={"source": "test"},
                ),
            ]
        )
        await session.flush()

    return {
        "attempt_id": attempt_id,
        "sibling_id": sibling_id,
        "version_id": version_id,
        "question_id": question_id,
    }


async def _delete(session: AsyncSession, attempt_id: UUID) -> httpx.Response:
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.delete(f"/api/v1/attempts/{attempt_id}")
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.integration
@pytest.mark.parametrize(
    "attempt_status",
    [
        AttemptStatus.IN_PROGRESS,
        AttemptStatus.PAUSED,
        AttemptStatus.SUBMITTED,
        AttemptStatus.AUTO_SUBMITTED,
        AttemptStatus.INTERRUPTED,
        AttemptStatus.ABANDONED,
    ],
)
async def test_delete_attempt_removes_owned_data_but_preserves_shared_content(
    db_session: AsyncSession, attempt_status: AttemptStatus, authenticated_admin
) -> None:
    seeded = await _seed_attempt_with_owned_data(db_session, attempt_status)

    response = await _delete(db_session, seeded["attempt_id"])

    assert response.status_code == 204
    assert response.content == b""
    assert await db_session.get(Attempt, seeded["attempt_id"]) is None
    assert await db_session.get(Attempt, seeded["sibling_id"]) is not None
    assert await db_session.get(DomainVersion, seeded["version_id"]) is not None
    assert await db_session.get(Question, seeded["question_id"]) is not None

    for model in (
        AttemptAnswer,
        AttemptWritingResponse,
        AttemptWritingScore,
        Highlight,
        QuestionFlag,
        AttemptEvent,
    ):
        remaining = await db_session.scalar(
            select(func.count()).select_from(model).where(model.attempt_id == seeded["attempt_id"])
        )
        assert remaining == 0


@pytest.mark.integration
async def test_delete_attempt_returns_normal_not_found_error(
    db_session: AsyncSession, authenticated_admin
) -> None:
    response = await _delete(db_session, uuid4())

    assert response.status_code == 404
    assert response.json() == {
        "code": "ATTEMPT_NOT_FOUND",
        "message": "The requested attempt does not exist.",
    }
