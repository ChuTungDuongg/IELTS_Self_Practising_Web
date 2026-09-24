"""PostgreSQL regressions for the Builder/Publish serialization boundary."""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.exceptions import AppError
from app.models import (
    ListeningPart,
    Question,
    QuestionGroup,
    ReadingPassage,
    WritingTask,
)
from app.models import (
    Test as DomainTest,
)
from app.models import (
    TestModule as ModuleRecord,
)
from app.models import (
    TestVersion as VersionRecord,
)
from app.models.enums import ModuleType, VersionStatus
from app.schemas.content import ListeningPartWrite, PassageWrite, TextBlock, WritingTaskWrite
from app.services.listening import ListeningService
from app.services.reading import ReadingService
from app.services.tests import TestService as VersionService
from app.services.writing import WritingService


@dataclass
class IndependentSessions:
    factory: async_sessionmaker[AsyncSession]
    create_draft: Callable[..., Awaitable[tuple[UUID, UUID, UUID, UUID | None, UUID | None]]]

    def __call__(self) -> AsyncSession:
        return self.factory()


@pytest_asyncio.fixture
async def independent_sessions() -> AsyncIterator[IndependentSessions]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
    if "test" not in (make_url(url).database or "").lower():
        raise RuntimeError("TEST_DATABASE_URL must name a test database")
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    created_test_ids: list[UUID] = []

    async def create_draft(
        *, with_other_skills: bool = False
    ) -> tuple[UUID, UUID, UUID, UUID | None, UUID | None]:
        test = DomainTest(title=f"Fictional concurrency test {uuid4()}")
        version = VersionRecord(version_number=1, status=VersionStatus.DRAFT)
        test.versions.append(version)
        reading = ModuleRecord(module_type=ModuleType.READING, title="Reading", order_index=0)
        version.modules.append(reading)
        passage = ReadingPassage(
            title="Original passage",
            order_index=0,
            content_json=[
                {"id": str(uuid4()), "type": "paragraph", "label": "A", "text": "Fictional text"}
            ],
            plain_text="Fictional text",
        )
        reading.passages.append(passage)
        group = QuestionGroup(
            question_type="true_false_not_given",
            instruction="Choose TRUE, FALSE, or NOT GIVEN.",
            config={},
            order_index=0,
        )
        group.questions.append(
            Question(
                number=1,
                prompt="Fictional statement",
                config={},
                answer_key={"kind": "SINGLE_OPTION", "value": "TRUE"},
                order_index=0,
            )
        )
        passage.question_groups.append(group)
        reading.question_groups.append(group)

        part: ListeningPart | None = None
        task: WritingTask | None = None
        if with_other_skills:
            listening = ModuleRecord(
                module_type=ModuleType.LISTENING, title="Listening", order_index=1
            )
            part = ListeningPart(title="Original part", order_index=0)
            listening.listening_parts.append(part)
            version.modules.append(listening)
            writing = ModuleRecord(module_type=ModuleType.WRITING, title="Writing", order_index=2)
            task = WritingTask(
                task_number=1,
                prompt="Original prompt",
                minimum_recommended_words=150,
                recommended_duration_seconds=1200,
                order_index=0,
            )
            writing.writing_tasks.extend(
                [
                    task,
                    WritingTask(
                        task_number=2,
                        prompt="Second prompt",
                        minimum_recommended_words=250,
                        recommended_duration_seconds=2400,
                        order_index=1,
                    ),
                ]
            )
            version.modules.append(writing)

        async with factory() as session:
            async with session.begin():
                session.add(test)
                await session.flush()
                created_test_ids.append(test.id)
        return test.id, version.id, passage.id, part.id if part else None, task.id if task else None

    try:
        yield IndependentSessions(factory=factory, create_draft=create_draft)
    finally:
        if created_test_ids:
            async with factory() as session:
                async with session.begin():
                    await session.execute(
                        delete(DomainTest).where(DomainTest.id.in_(created_test_ids))
                    )
        await engine.dispose()


def passage_body(title: str) -> PassageWrite:
    return PassageWrite(
        title=title,
        order_index=0,
        blocks=[TextBlock(id=uuid4(), type="paragraph", label="A", text="Fictional text")],
    )


def locks_version(statement: object) -> bool:
    return (
        getattr(statement, "_for_update_arg", None) is not None
        and statement.column_descriptions[0]["entity"] is VersionRecord
    )


@pytest.mark.integration
async def test_builder_lock_first_publish_includes_committed_edit(
    independent_sessions: IndependentSessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, version_id, passage_id, _, _ = await independent_sessions.create_draft()
    builder_locked = asyncio.Event()
    publish_waiting = asyncio.Event()
    release_builder = asyncio.Event()

    async with independent_sessions() as builder, independent_sessions() as publisher:
        builder_scalar = builder.scalar
        publisher_scalar = publisher.scalar

        async def pause_builder(statement, *args, **kwargs):
            result = await builder_scalar(statement, *args, **kwargs)
            if locks_version(statement):
                builder_locked.set()
                await release_builder.wait()
            return result

        async def observe_publish(statement, *args, **kwargs):
            if locks_version(statement):
                publish_waiting.set()
            return await publisher_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(builder, "scalar", pause_builder)
        monkeypatch.setattr(publisher, "scalar", observe_publish)
        builder_task = asyncio.create_task(
            ReadingService(builder).update_passage(
                passage_id, passage_body("Edited before publish")
            )
        )
        publisher_task = None
        try:
            await asyncio.wait_for(builder_locked.wait(), 10)
            publisher_task = asyncio.create_task(VersionService(publisher).publish(version_id))
            await asyncio.wait_for(publish_waiting.wait(), 10)
            assert not publisher_task.done()
            release_builder.set()
            await asyncio.wait_for(builder_task, 10)
            await asyncio.wait_for(publisher_task, 10)
        finally:
            release_builder.set()
            for task in (builder_task, publisher_task):
                if task is not None and not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    async with independent_sessions() as verify:
        assert (
            await verify.scalar(select(VersionRecord.status).where(VersionRecord.id == version_id))
            == VersionStatus.PUBLISHED
        )
        assert (
            await verify.scalar(select(ReadingPassage.title).where(ReadingPassage.id == passage_id))
            == "Edited before publish"
        )


@pytest.mark.integration
async def test_publish_lock_first_rejects_stale_builder_edit(
    independent_sessions: IndependentSessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, version_id, passage_id, _, _ = await independent_sessions.create_draft()
    publish_locked = asyncio.Event()
    builder_waiting = asyncio.Event()
    release_publish = asyncio.Event()

    async with independent_sessions() as publisher, independent_sessions() as builder:
        publisher_scalar = publisher.scalar
        builder_scalar = builder.scalar

        async def pause_publish(statement, *args, **kwargs):
            result = await publisher_scalar(statement, *args, **kwargs)
            if locks_version(statement):
                publish_locked.set()
                await release_publish.wait()
            return result

        async def observe_builder(statement, *args, **kwargs):
            if locks_version(statement):
                builder_waiting.set()
            return await builder_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(publisher, "scalar", pause_publish)
        monkeypatch.setattr(builder, "scalar", observe_builder)
        publisher_task = asyncio.create_task(VersionService(publisher).publish(version_id))
        builder_task = None
        try:
            await asyncio.wait_for(publish_locked.wait(), 10)
            builder_task = asyncio.create_task(
                ReadingService(builder).update_passage(passage_id, passage_body("Stale edit"))
            )
            await asyncio.wait_for(builder_waiting.wait(), 10)
            assert not builder_task.done()
            release_publish.set()
            await asyncio.wait_for(publisher_task, 10)
            with pytest.raises(AppError) as error:
                await asyncio.wait_for(builder_task, 10)
            assert error.value.code == "TEST_VERSION_IMMUTABLE"
            assert error.value.status_code == 409
        finally:
            release_publish.set()
            for task in (publisher_task, builder_task):
                if task is not None and not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    async with independent_sessions() as verify:
        assert (
            await verify.scalar(select(VersionRecord.status).where(VersionRecord.id == version_id))
            == VersionStatus.PUBLISHED
        )
        assert (
            await verify.scalar(select(ReadingPassage.title).where(ReadingPassage.id == passage_id))
            == "Original passage"
        )


@pytest.mark.integration
async def test_each_skill_edits_draft_and_rejects_published_version(
    independent_sessions: IndependentSessions,
) -> None:
    _, version_id, passage_id, part_id, task_id = await independent_sessions.create_draft(
        with_other_skills=True
    )
    assert part_id is not None and task_id is not None
    async with independent_sessions() as session:
        await ReadingService(session).update_passage(passage_id, passage_body("Draft reading edit"))
        await session.rollback()
        await ListeningService(session).update_part(
            part_id, ListeningPartWrite(title="Draft listening edit", order_index=0)
        )
        await session.rollback()
        await WritingService(session).update_task(
            task_id, WritingTaskWrite(prompt="Draft writing edit")
        )
        await session.rollback()
        published = await VersionService(session).publish(version_id)
        assert published.status == VersionStatus.PUBLISHED
        await session.rollback()

        for edit in (
            ReadingService(session).update_passage(passage_id, passage_body("Stale reading edit")),
            ListeningService(session).update_part(
                part_id, ListeningPartWrite(title="Stale listening edit", order_index=0)
            ),
            WritingService(session).update_task(
                task_id, WritingTaskWrite(prompt="Stale writing edit")
            ),
        ):
            with pytest.raises(AppError) as error:
                await edit
            assert error.value.code == "TEST_VERSION_IMMUTABLE"
            assert error.value.status_code == 409

    async with independent_sessions() as verify:
        assert (
            await verify.scalar(select(ReadingPassage.title).where(ReadingPassage.id == passage_id))
            == "Draft reading edit"
        )
        assert (
            await verify.scalar(select(ListeningPart.title).where(ListeningPart.id == part_id))
            == "Draft listening edit"
        )
        assert (
            await verify.scalar(select(WritingTask.prompt).where(WritingTask.id == task_id))
            == "Draft writing edit"
        )
