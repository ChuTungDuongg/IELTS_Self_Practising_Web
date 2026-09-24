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
from app.schemas.content import (
    ListeningModuleAudioWrite,
    ListeningPartUpdate,
    PassageUpdate,
    PassageWrite,
    QuestionGroupOrderWrite,
    QuestionGroupUpdate,
    QuestionGroupWrite,
    QuestionWrite,
    TextBlock,
    WritingTaskUpdate,
)
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


def passage_body(title: str, expected_revision: int = 1) -> PassageUpdate:
    return PassageUpdate(
        expected_revision=expected_revision,
        title=title,
        order_index=0,
        blocks=[TextBlock(id=uuid4(), type="paragraph", label="A", text="Fictional text")],
    )


def group_body(prompt: str, question_id: UUID, expected_revision: int = 1) -> QuestionGroupUpdate:
    return QuestionGroupUpdate(
        expected_revision=expected_revision,
        question_type="true_false_not_given",
        instruction="Choose TRUE, FALSE, or NOT GIVEN.",
        config={},
        order_index=0,
        questions=[
            QuestionWrite(
                id=question_id,
                number=1,
                prompt=prompt,
                config={},
                answer_key={"kind": "SINGLE_OPTION", "value": "TRUE"},
                order_index=0,
            )
        ],
    )


def locks_version(statement: object) -> bool:
    return (
        getattr(statement, "_for_update_arg", None) is not None
        and statement.column_descriptions[0]["entity"] is VersionRecord
    )


@pytest.mark.integration
async def test_stale_passage_save_preserves_first_admin_edit(
    independent_sessions: IndependentSessions,
) -> None:
    _, _, passage_id, _, _ = await independent_sessions.create_draft()
    first = passage_body("Admin A edit")
    stale = passage_body("Admin B stale edit")

    async with independent_sessions() as admin_a, independent_sessions() as admin_b:
        saved = await ReadingService(admin_a).update_passage(passage_id, first)
        assert saved.revision == 2
        with pytest.raises(AppError) as error:
            await ReadingService(admin_b).update_passage(passage_id, stale)
        assert error.value.code == "DRAFT_REVISION_CONFLICT"
        assert error.value.status_code == 409

    async with independent_sessions() as verify:
        passage = await verify.get(ReadingPassage, passage_id)
        assert passage is not None
        assert passage.title == "Admin A edit"
        assert passage.revision == 2

    async with independent_sessions() as reloader:
        latest = await reloader.get(ReadingPassage, passage_id)
        assert latest is not None
        latest_revision = latest.revision
    async with independent_sessions() as admin_b:
        recovered = await ReadingService(admin_b).update_passage(
            passage_id, passage_body("Admin B after reload", latest_revision)
        )
        assert recovered.revision == 3


@pytest.mark.integration
async def test_unrelated_passages_keep_independent_revisions(
    independent_sessions: IndependentSessions,
) -> None:
    _, version_id, first_id, _, _ = await independent_sessions.create_draft()
    async with independent_sessions() as creator:
        second = await ReadingService(creator).create_passage(
            version_id,
            PassageWrite(
                title="Second passage",
                order_index=1,
                blocks=[TextBlock(id=uuid4(), type="paragraph", label="A", text="Second fictional text")],
            ),
        )
        assert second.revision == 1
    async with independent_sessions() as first_editor:
        first = await ReadingService(first_editor).update_passage(
            first_id, passage_body("First passage edited")
        )
        assert first.revision == 2
    async with independent_sessions() as second_editor:
        saved_second = await ReadingService(second_editor).update_passage(
            second.id, PassageUpdate(
                expected_revision=1,
                title="Second passage edited",
                order_index=1,
                blocks=[TextBlock(id=uuid4(), type="paragraph", label="A", text="Second fictional text")],
            )
        )
        assert saved_second.revision == 2


@pytest.mark.integration
async def test_overlapping_passage_saves_only_one_can_advance_revision_one(
    independent_sessions: IndependentSessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, passage_id, _, _ = await independent_sessions.create_draft()
    first_locked = asyncio.Event()
    second_waiting = asyncio.Event()
    release_first = asyncio.Event()

    async with independent_sessions() as first_session, independent_sessions() as second_session:
        first_scalar = first_session.scalar
        second_scalar = second_session.scalar

        async def pause_first(statement, *args, **kwargs):
            result = await first_scalar(statement, *args, **kwargs)
            if locks_version(statement):
                first_locked.set()
                await release_first.wait()
            return result

        async def observe_second(statement, *args, **kwargs):
            if locks_version(statement):
                second_waiting.set()
            return await second_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(first_session, "scalar", pause_first)
        monkeypatch.setattr(second_session, "scalar", observe_second)
        first_task = asyncio.create_task(
            ReadingService(first_session).update_passage(passage_id, passage_body("First"))
        )
        second_task = None
        try:
            await asyncio.wait_for(first_locked.wait(), 10)
            second_task = asyncio.create_task(
                ReadingService(second_session).update_passage(passage_id, passage_body("Second"))
            )
            await asyncio.wait_for(second_waiting.wait(), 10)
            assert not second_task.done()
            release_first.set()
            first = await asyncio.wait_for(first_task, 10)
            assert first.revision == 2
            with pytest.raises(AppError) as error:
                await asyncio.wait_for(second_task, 10)
            assert error.value.code == "DRAFT_REVISION_CONFLICT"
        finally:
            release_first.set()
            for task in (first_task, second_task):
                if task is not None and not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    async with independent_sessions() as verify:
        passage = await verify.get(ReadingPassage, passage_id)
        assert passage is not None
        assert (passage.title, passage.revision) == ("First", 2)


@pytest.mark.integration
async def test_reading_group_revision_protects_child_question(
    independent_sessions: IndependentSessions,
) -> None:
    _, _, passage_id, _, _ = await independent_sessions.create_draft()
    async with independent_sessions() as read:
        group = await read.scalar(select(QuestionGroup).where(QuestionGroup.passage_id == passage_id))
        assert group is not None
        question = await read.scalar(select(Question).where(Question.question_group_id == group.id))
        assert question is not None
        group_id, question_id = group.id, question.id

    async with independent_sessions() as editor:
        saved = await ReadingService(editor).update_group(group_id, group_body("Admin A question", question_id))
        assert saved.revision == 2
    async with independent_sessions() as stale_editor:
        with pytest.raises(AppError) as error:
            await ReadingService(stale_editor).update_group(group_id, group_body("Stale question", question_id))
        assert error.value.code == "DRAFT_REVISION_CONFLICT"
    async with independent_sessions() as verify:
        question = await verify.get(Question, question_id)
        group = await verify.get(QuestionGroup, group_id)
        assert question is not None and group is not None
        assert (question.prompt, group.revision) == ("Admin A question", 2)


@pytest.mark.integration
async def test_listening_part_and_group_reject_stale_updates(
    independent_sessions: IndependentSessions,
) -> None:
    _, _, _, part_id, _ = await independent_sessions.create_draft(with_other_skills=True)
    assert part_id is not None
    async with independent_sessions() as editor:
        saved_part = await ListeningService(editor).update_part(
            part_id, ListeningPartUpdate(expected_revision=1, title="Admin A part", order_index=0)
        )
        assert saved_part.revision == 2
    async with independent_sessions() as stale_editor:
        with pytest.raises(AppError) as error:
            await ListeningService(stale_editor).update_part(
                part_id, ListeningPartUpdate(expected_revision=1, title="Stale part", order_index=0)
            )
        assert error.value.code == "DRAFT_REVISION_CONFLICT"

    new_group = group_body("Original Listening question", uuid4()).model_dump(exclude={"expected_revision"})
    async with independent_sessions() as creator:
        created = await ListeningService(creator).create_group(part_id, QuestionGroupWrite.model_validate(new_group))
        assert created.revision == 1
        group_id, question_id = created.id, created.questions[0].id
    async with independent_sessions() as editor:
        saved = await ListeningService(editor).update_group(group_id, group_body("Admin A Listening question", question_id))
        assert saved.revision == 2
    async with independent_sessions() as stale_editor:
        with pytest.raises(AppError) as error:
            await ListeningService(stale_editor).update_group(group_id, group_body("Stale Listening question", question_id))
        assert error.value.code == "DRAFT_REVISION_CONFLICT"
    async with independent_sessions() as verify:
        part = await verify.get(ListeningPart, part_id)
        group = await verify.get(QuestionGroup, group_id)
        question = await verify.get(Question, question_id)
        assert part is not None and group is not None and question is not None
        assert (part.title, part.revision) == ("Admin A part", 2)
        assert (question.prompt, group.revision) == ("Admin A Listening question", 2)


@pytest.mark.integration
async def test_writing_task_revision_is_independent_per_task(
    independent_sessions: IndependentSessions,
) -> None:
    _, _, _, _, task_id = await independent_sessions.create_draft(with_other_skills=True)
    assert task_id is not None
    async with independent_sessions() as read:
        task_two = await read.scalar(
            select(WritingTask).where(WritingTask.module_id == select(WritingTask.module_id).where(WritingTask.id == task_id).scalar_subquery(), WritingTask.task_number == 2)
        )
        assert task_two is not None
        task_two_id = task_two.id
    async with independent_sessions() as editor:
        saved = await WritingService(editor).update_task(
            task_id, WritingTaskUpdate(expected_revision=1, prompt="Admin A prompt")
        )
        assert saved.revision == 2
    async with independent_sessions() as stale_editor:
        with pytest.raises(AppError) as error:
            await WritingService(stale_editor).update_task(
                task_id, WritingTaskUpdate(expected_revision=1, prompt="Stale prompt")
            )
        assert error.value.code == "DRAFT_REVISION_CONFLICT"
    async with independent_sessions() as other_task_editor:
        saved_two = await WritingService(other_task_editor).update_task(
            task_two_id, WritingTaskUpdate(expected_revision=1, prompt="Independent Task 2 prompt")
        )
        assert saved_two.revision == 2
    async with independent_sessions() as verify:
        first = await verify.get(WritingTask, task_id)
        second = await verify.get(WritingTask, task_two_id)
        assert first is not None and second is not None
        assert (first.prompt, first.revision) == ("Admin A prompt", 2)
        assert (second.prompt, second.revision) == ("Independent Task 2 prompt", 2)


@pytest.mark.integration
async def test_module_audio_and_group_order_use_module_revision(
    independent_sessions: IndependentSessions,
) -> None:
    _, _, passage_id, part_id, _ = await independent_sessions.create_draft(with_other_skills=True)
    assert part_id is not None
    async with independent_sessions() as read:
        reading_module_id = await read.scalar(
            select(ReadingPassage.module_id).where(ReadingPassage.id == passage_id)
        )
        listening_module_id = await read.scalar(
            select(ListeningPart.module_id).where(ListeningPart.id == part_id)
        )
        first_group_id = await read.scalar(
            select(QuestionGroup.id).where(QuestionGroup.passage_id == passage_id)
        )
        assert reading_module_id and listening_module_id and first_group_id

    async with independent_sessions() as editor:
        audio = await ListeningService(editor).attach_audio(
            listening_module_id, ListeningModuleAudioWrite(expected_revision=1, asset_id=None)
        )
        assert audio.revision == 2
    async with independent_sessions() as stale_editor:
        with pytest.raises(AppError) as error:
            await ListeningService(stale_editor).attach_audio(
                listening_module_id, ListeningModuleAudioWrite(expected_revision=1, asset_id=None)
            )
        assert error.value.code == "DRAFT_REVISION_CONFLICT"

    async with independent_sessions() as creator:
        new_group = await ReadingService(creator).create_group(
            passage_id,
            QuestionGroupWrite.model_validate(
                group_body("Second reading group", uuid4()).model_dump(exclude={"expected_revision"})
            ),
        )
        assert new_group.revision == 1
    async with independent_sessions() as editor:
        ordered = await ReadingService(editor).reorder_groups(
            reading_module_id,
            QuestionGroupOrderWrite(
                expected_revision=1, group_ids=[new_group.id, first_group_id]
            ),
        )
        assert ordered.revision == 2
    async with independent_sessions() as stale_editor:
        with pytest.raises(AppError) as error:
            await ReadingService(stale_editor).reorder_groups(
                reading_module_id,
                QuestionGroupOrderWrite(
                    expected_revision=1, group_ids=[first_group_id, new_group.id]
                ),
            )
        assert error.value.code == "DRAFT_REVISION_CONFLICT"
    async with independent_sessions() as verify:
        first = await verify.get(QuestionGroup, first_group_id)
        second = await verify.get(QuestionGroup, new_group.id)
        assert first is not None and second is not None
        assert (first.revision, second.revision) == (2, 2)


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
            part_id, ListeningPartUpdate(expected_revision=1, title="Draft listening edit", order_index=0)
        )
        await session.rollback()
        await WritingService(session).update_task(
            task_id, WritingTaskUpdate(expected_revision=1, prompt="Draft writing edit")
        )
        await session.rollback()
        published = await VersionService(session).publish(version_id)
        assert published.status == VersionStatus.PUBLISHED
        await session.rollback()

        for edit in (
            ReadingService(session).update_passage(passage_id, passage_body("Stale reading edit")),
            ListeningService(session).update_part(
                part_id, ListeningPartUpdate(expected_revision=1, title="Stale listening edit", order_index=0)
            ),
            WritingService(session).update_task(
                task_id, WritingTaskUpdate(expected_revision=1, prompt="Stale writing edit")
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
