"""PostgreSQL response revisions across independent learner sessions."""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.exceptions import AppError
from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptWritingResponse,
    ListeningPart,
    Question,
    QuestionGroup,
    ReadingPassage,
    User,
    WritingTask,
)
from app.models import Test as DomainTest
from app.models import TestModule as ModuleRecord
from app.models import TestVersion as VersionRecord
from app.models.enums import AttemptStatus, ModuleType, TimerMode, UserRole, VersionStatus
from app.services.attempts import AttemptService


@dataclass
class ResponseContext:
    factory: async_sessionmaker[AsyncSession]
    owner_id: UUID
    other_id: UUID
    test_id: UUID
    reading_attempt_id: UUID
    listening_attempt_id: UUID
    writing_attempt_id: UUID
    reading_questions: tuple[UUID, UUID]
    listening_question_id: UUID
    writing_tasks: tuple[UUID, UUID]

    def session(self) -> AsyncSession:
        return self.factory()


@pytest_asyncio.fixture
async def response_context() -> AsyncIterator[ResponseContext]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
    if "test" not in (make_url(url).database or "").lower():
        raise RuntimeError("TEST_DATABASE_URL must name a test database")
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    owner = User(
        email=f"learner-{uuid4()}@example.com",
        display_name="Fictional learner",
        role=UserRole.USER,
        is_active=True,
    )
    other = User(
        email=f"other-{uuid4()}@example.com",
        display_name="Fictional other learner",
        role=UserRole.USER,
        is_active=True,
    )
    test = DomainTest(title="Fictional response concurrency")
    version = VersionRecord(version_number=1, status=VersionStatus.PUBLISHED, published_at=now)
    test.versions.append(version)

    reading = ModuleRecord(module_type=ModuleType.READING, order_index=0)
    passage = ReadingPassage(
        title="Fictional passage",
        order_index=0,
        content_json=[
            {"id": str(uuid4()), "type": "paragraph", "label": "A", "text": "Fictional text."}
        ],
        plain_text="Fictional text.",
    )
    reading_group = QuestionGroup(
        question_type="true_false_not_given",
        instruction="Choose TRUE, FALSE, or NOT GIVEN.",
        config={},
        order_index=0,
    )
    reading_questions = [
        Question(
            number=index + 1,
            prompt=f"Fictional statement {index + 1}",
            config={},
            answer_key={"kind": "SINGLE_OPTION", "value": "TRUE"},
            order_index=index,
        )
        for index in range(2)
    ]
    reading_group.questions.extend(reading_questions)
    passage.question_groups.append(reading_group)
    reading.passages.append(passage)
    reading.question_groups.append(reading_group)

    listening = ModuleRecord(module_type=ModuleType.LISTENING, order_index=1)
    part = ListeningPart(title="Fictional section", order_index=0)
    listening_group = QuestionGroup(
        question_type="true_false_not_given",
        instruction="Choose TRUE, FALSE, or NOT GIVEN.",
        config={},
        order_index=0,
    )
    listening_question = Question(
        number=1,
        prompt="Fictional audio statement",
        config={},
        answer_key={"kind": "SINGLE_OPTION", "value": "TRUE"},
        order_index=0,
    )
    listening_group.questions.append(listening_question)
    part.question_groups.append(listening_group)
    listening.listening_parts.append(part)
    listening.question_groups.append(listening_group)

    writing = ModuleRecord(module_type=ModuleType.WRITING, order_index=2)
    writing_tasks = [
        WritingTask(
            task_number=index + 1,
            prompt=f"Fictional Writing Task {index + 1}",
            minimum_recommended_words=150 if index == 0 else 250,
            recommended_duration_seconds=1200 if index == 0 else 2400,
            order_index=index,
        )
        for index in range(2)
    ]
    writing.writing_tasks.extend(writing_tasks)
    version.modules.extend([reading, listening, writing])
    async with factory() as session:
        async with session.begin():
            session.add_all([owner, other, test])
            await session.flush()
            attempts = {
                module: Attempt(
                    user_id=owner.id,
                    test_version_id=version.id,
                    module_type=module,
                    timer_mode=TimerMode.COUNT_UP,
                    started_at=now,
                    last_active_at=now,
                    status=AttemptStatus.IN_PROGRESS,
                )
                for module in ModuleType
            }
            session.add_all(attempts.values())
            await session.flush()
            context = ResponseContext(
                factory=factory,
                owner_id=owner.id,
                other_id=other.id,
                test_id=test.id,
                reading_attempt_id=attempts[ModuleType.READING].id,
                listening_attempt_id=attempts[ModuleType.LISTENING].id,
                writing_attempt_id=attempts[ModuleType.WRITING].id,
                reading_questions=(reading_questions[0].id, reading_questions[1].id),
                listening_question_id=listening_question.id,
                writing_tasks=(writing_tasks[0].id, writing_tasks[1].id),
            )
    try:
        yield context
    finally:
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    delete(Attempt).where(
                        Attempt.id.in_(
                            [
                                context.reading_attempt_id,
                                context.listening_attempt_id,
                                context.writing_attempt_id,
                            ]
                        )
                    )
                )
                await session.execute(delete(DomainTest).where(DomainTest.id == context.test_id))
                await session.execute(
                    delete(User).where(User.id.in_([context.owner_id, context.other_id]))
                )
        await engine.dispose()


def locks_attempt(statement: object) -> bool:
    return (
        getattr(statement, "_for_update_arg", None) is not None
        and statement.column_descriptions[0]["entity"] is Attempt
    )


@pytest.mark.integration
async def test_answer_revisions_reject_stale_changes_and_acknowledge_lost_response(
    response_context: ResponseContext,
) -> None:
    ctx = response_context
    question_id, other_question_id = ctx.reading_questions
    async with ctx.session() as initial:
        exam = await AttemptService(initial, ctx.owner_id).exam(ctx.reading_attempt_id)
        assert all(
            question.answer_revision == 0
            for passage in exam.passages
            for group in passage.question_groups
            for question in group.questions
        )
    async with ctx.session() as first_tab, ctx.session() as second_tab:
        with pytest.raises(AppError) as ownership_error:
            await AttemptService(second_tab, ctx.other_id).save_answer(
                ctx.reading_attempt_id, question_id, "FALSE", 0
            )
        assert ownership_error.value.status_code == 404
        first = await AttemptService(first_tab, ctx.owner_id).save_answer(
            ctx.reading_attempt_id, question_id, "TRUE", 0
        )
        assert (first.value, first.revision) == ("TRUE", 1)
        retry = await AttemptService(first_tab, ctx.owner_id).save_answer(
            ctx.reading_attempt_id, question_id, "TRUE", 0
        )
        assert (retry.value, retry.revision) == ("TRUE", 1)
        with pytest.raises(AppError) as error:
            await AttemptService(second_tab, ctx.owner_id).save_answer(
                ctx.reading_attempt_id, question_id, "FALSE", 0
            )
        assert (error.value.code, error.value.status_code) == ("ATTEMPT_RESPONSE_CONFLICT", 409)
        next_question = await AttemptService(second_tab, ctx.owner_id).save_answer(
            ctx.reading_attempt_id, other_question_id, "FALSE", 0
        )
        assert next_question.revision == 1
        changed = await AttemptService(first_tab, ctx.owner_id).save_answer(
            ctx.reading_attempt_id, question_id, "FALSE", 1
        )
        assert changed.revision == 2

    async with ctx.session() as verify:
        exam = await AttemptService(verify, ctx.owner_id).exam(ctx.reading_attempt_id)
        questions = {
            question.id: question
            for passage in exam.passages
            for group in passage.question_groups
            for question in group.questions
        }
        assert questions[question_id].answer_revision == 2
        assert questions[other_question_id].answer_revision == 1
        assert "answer_key" not in questions[question_id].model_dump()
        rows = (
            await verify.scalars(
                select(AttemptAnswer).where(AttemptAnswer.attempt_id == ctx.reading_attempt_id)
            )
        ).all()
        assert {(row.question_id, row.value, row.revision) for row in rows} == {
            (question_id, "FALSE", 2),
            (other_question_id, "FALSE", 1),
        }

    async with ctx.session() as listener:
        saved = await AttemptService(listener, ctx.owner_id).save_answer(
            ctx.listening_attempt_id, ctx.listening_question_id, "TRUE", 0
        )
        assert saved.revision == 1


@pytest.mark.integration
async def test_writing_revisions_are_per_task_and_lost_response_retry_is_safe(
    response_context: ResponseContext,
) -> None:
    ctx = response_context
    first_task, second_task = ctx.writing_tasks
    async with ctx.session() as initial:
        exam = await AttemptService(initial, ctx.owner_id).exam(ctx.writing_attempt_id)
        assert all(task.response_revision == 0 for task in exam.writing_tasks)
    async with ctx.session() as first_tab, ctx.session() as second_tab:
        first = await AttemptService(first_tab, ctx.owner_id).save_writing_response(
            ctx.writing_attempt_id, first_task, "Fictional first answer", 0
        )
        assert first.revision == 1
        retry = await AttemptService(second_tab, ctx.owner_id).save_writing_response(
            ctx.writing_attempt_id, first_task, "Fictional first answer", 0
        )
        assert retry.revision == 1
        with pytest.raises(AppError) as error:
            await AttemptService(second_tab, ctx.owner_id).save_writing_response(
                ctx.writing_attempt_id, first_task, "Stale different answer", 0
            )
        assert (error.value.code, error.value.status_code) == ("ATTEMPT_RESPONSE_CONFLICT", 409)
        independent = await AttemptService(second_tab, ctx.owner_id).save_writing_response(
            ctx.writing_attempt_id, second_task, "Fictional second task", 0
        )
        assert independent.revision == 1
        changed = await AttemptService(first_tab, ctx.owner_id).save_writing_response(
            ctx.writing_attempt_id, first_task, "Changed first task", 1
        )
        assert changed.revision == 2

    async with ctx.session() as verify:
        exam = await AttemptService(verify, ctx.owner_id).exam(ctx.writing_attempt_id)
        assert {task.id: task.response_revision for task in exam.writing_tasks} == {
            first_task: 2,
            second_task: 1,
        }
        rows = (
            await verify.scalars(
                select(AttemptWritingResponse).where(
                    AttemptWritingResponse.attempt_id == ctx.writing_attempt_id
                )
            )
        ).all()
        assert {(row.writing_task_id, row.content, row.revision) for row in rows} == {
            (first_task, "Changed first task", 2),
            (second_task, "Fictional second task", 1),
        }


@pytest.mark.integration
async def test_overlapping_answer_writes_have_one_winner(
    response_context: ResponseContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = response_context
    question_id = ctx.reading_questions[0]
    async with ctx.session() as setup:
        await AttemptService(setup, ctx.owner_id).save_answer(
            ctx.reading_attempt_id, question_id, "TRUE", 0
        )

    first_locked = asyncio.Event()
    second_waiting = asyncio.Event()
    release_first = asyncio.Event()
    async with ctx.session() as first_tab, ctx.session() as second_tab:
        first_scalar = first_tab.scalar
        second_scalar = second_tab.scalar

        async def hold_first(statement, *args, **kwargs):
            result = await first_scalar(statement, *args, **kwargs)
            if locks_attempt(statement):
                first_locked.set()
                await release_first.wait()
            return result

        async def observe_second(statement, *args, **kwargs):
            if locks_attempt(statement):
                second_waiting.set()
            return await second_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(first_tab, "scalar", hold_first)
        monkeypatch.setattr(second_tab, "scalar", observe_second)
        first_job = asyncio.create_task(
            AttemptService(first_tab, ctx.owner_id).save_answer(
                ctx.reading_attempt_id, question_id, "FALSE", 1
            )
        )
        second_job = None
        try:
            await asyncio.wait_for(first_locked.wait(), 10)
            second_job = asyncio.create_task(
                AttemptService(second_tab, ctx.owner_id).save_answer(
                    ctx.reading_attempt_id, question_id, "NOT_GIVEN", 1
                )
            )
            await asyncio.wait_for(second_waiting.wait(), 10)
            assert not second_job.done()
            release_first.set()
            winner = await asyncio.wait_for(first_job, 10)
            assert winner.revision == 2
            with pytest.raises(AppError) as error:
                await asyncio.wait_for(second_job, 10)
            assert error.value.code == "ATTEMPT_RESPONSE_CONFLICT"
        finally:
            release_first.set()
            for job in (first_job, second_job):
                if job is not None and not job.done():
                    job.cancel()
                    await asyncio.gather(job, return_exceptions=True)

    async with ctx.session() as verify:
        answer = await verify.scalar(
            select(AttemptAnswer).where(
                AttemptAnswer.attempt_id == ctx.reading_attempt_id,
                AttemptAnswer.question_id == question_id,
            )
        )
        assert answer is not None
        assert (answer.value, answer.revision) == ("FALSE", 2)


@pytest.mark.integration
async def test_overlapping_writing_writes_have_one_winner(
    response_context: ResponseContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = response_context
    task_id = ctx.writing_tasks[0]
    async with ctx.session() as setup:
        await AttemptService(setup, ctx.owner_id).save_writing_response(
            ctx.writing_attempt_id, task_id, "Original content", 0
        )

    first_locked = asyncio.Event()
    second_waiting = asyncio.Event()
    release_first = asyncio.Event()
    async with ctx.session() as first_tab, ctx.session() as second_tab:
        first_scalar = first_tab.scalar
        second_scalar = second_tab.scalar

        async def hold_first(statement, *args, **kwargs):
            result = await first_scalar(statement, *args, **kwargs)
            if locks_attempt(statement):
                first_locked.set()
                await release_first.wait()
            return result

        async def observe_second(statement, *args, **kwargs):
            if locks_attempt(statement):
                second_waiting.set()
            return await second_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(first_tab, "scalar", hold_first)
        monkeypatch.setattr(second_tab, "scalar", observe_second)
        first_job = asyncio.create_task(
            AttemptService(first_tab, ctx.owner_id).save_writing_response(
                ctx.writing_attempt_id, task_id, "First writer", 1
            )
        )
        second_job = None
        try:
            await asyncio.wait_for(first_locked.wait(), 10)
            second_job = asyncio.create_task(
                AttemptService(second_tab, ctx.owner_id).save_writing_response(
                    ctx.writing_attempt_id, task_id, "Second writer", 1
                )
            )
            await asyncio.wait_for(second_waiting.wait(), 10)
            assert not second_job.done()
            release_first.set()
            winner = await asyncio.wait_for(first_job, 10)
            assert winner.revision == 2
            with pytest.raises(AppError) as error:
                await asyncio.wait_for(second_job, 10)
            assert error.value.code == "ATTEMPT_RESPONSE_CONFLICT"
        finally:
            release_first.set()
            for job in (first_job, second_job):
                if job is not None and not job.done():
                    job.cancel()
                    await asyncio.gather(job, return_exceptions=True)

    async with ctx.session() as verify:
        response = await verify.scalar(
            select(AttemptWritingResponse).where(
                AttemptWritingResponse.attempt_id == ctx.writing_attempt_id,
                AttemptWritingResponse.writing_task_id == task_id,
            )
        )
        assert response is not None
        assert (response.content, response.revision) == ("First writer", 2)
