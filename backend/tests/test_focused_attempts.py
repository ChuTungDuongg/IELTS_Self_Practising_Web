"""Focused scope authorization and lifecycle against PostgreSQL, fictional content only."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domains.scoring import calculate_task_overall
from app.domains.timers import TimerService
from app.models import (
    Asset,
    Attempt,
    AttemptAnswer,
    ListeningPart,
    Question,
    QuestionGroup,
    ReadingPassage,
    WritingTask,
)
from app.models import Test as ExamRecord
from app.models import TestModule as ModuleRecord
from app.models import TestVersion as VersionRecord
from app.models.enums import AssetType, AttemptScope, AttemptStatus, ModuleType, VersionStatus
from app.schemas.attempts import AttemptCreate, NavigationRequest, WritingTaskScoreUpdate
from app.schemas.content import HighlightCreate
from app.services.analytics import AnalyticsService
from app.services.attempts import AttemptService
from app.services.test_sessions import TestSessionService as SessionService
from app.services.writing_ai import WritingAIService

KINDS = {
    ModuleType.READING: "READING_PASSAGE",
    ModuleType.LISTENING: "LISTENING_PART",
    ModuleType.WRITING: "WRITING_TASK",
}


PRESETS = {
    ModuleType.READING: [1200, 1500, 1800],
    ModuleType.LISTENING: [600, 900, 1200],
    ModuleType.WRITING: [1200, 1500, 1800, 2100, 2400],
}


async def content(session, *, status=VersionStatus.PUBLISHED, archived=False):
    test = ExamRecord(
        title="Fictional focused test", archived_at=TimerService.now() if archived else None
    )
    version = VersionRecord(version_number=1, status=status)
    test.versions.append(version)
    units = {}
    for index, skill in enumerate(ModuleType):
        module = ModuleRecord(
            module_type=skill, order_index=index, recommended_duration_seconds=3600
        )
        version.modules.append(module)
        if skill == ModuleType.LISTENING:
            audio = Asset(
                id=uuid4(),
                asset_type=AssetType.LISTENING_AUDIO,
                relative_path=f"audio/fictional-{uuid4()}.mp3",
                mime_type="audio/mpeg",
                original_name="fictional-focused.mp3",
                file_size=10,
            )
            version.assets.append(audio)
            module.audio_asset = audio
        units[skill] = []
        for order in range(2):
            if skill == ModuleType.WRITING:
                unit = WritingTask(
                    task_number=order + 1,
                    order_index=order,
                    prompt="Discuss fictional parks.",
                    task_type="OTHER_ESSAY" if order else "BAR_CHART",
                )
                module.writing_tasks.append(unit)
            else:
                if skill == ModuleType.READING:
                    unit = ReadingPassage(
                        title=f"Fictional passage {order + 1}",
                        order_index=order,
                        content_json=[
                            {
                                "id": str(uuid4()),
                                "type": "paragraph",
                                "text": "Fictional passage text.",
                            }
                        ],
                        plain_text="Fictional passage text.",
                    )
                    module.passages.append(unit)
                else:
                    unit = ListeningPart(
                        title=f"Fictional section {order + 1}",
                        order_index=order,
                        audio_start_seconds=order * 60,
                        audio_end_seconds=(order + 1) * 60,
                    )
                    module.listening_parts.append(unit)
                group = QuestionGroup(
                    question_type="short_answer",
                    instruction="Answer briefly.",
                    order_index=order,
                    config={},
                )
                unit.question_groups.append(group)
                module.question_groups.append(group)
                for q in range(2):
                    group.questions.append(
                        Question(
                            number=order * 2 + q + 1,
                            order_index=q,
                            prompt="Fictional question",
                            config={"max_words": 2, "max_numbers": 0},
                            answer_key={"kind": "TEXT", "accepted": ["fixture"]},
                        )
                    )
            units[skill].append(unit)
    async with session.begin():
        session.add(test)
        await session.flush()
    # Rejected writes expire ORM objects on rollback; retain detached fixture data.
    snapshots = {}
    for skill, items in units.items():
        snapshots[skill] = [
            SimpleNamespace(
                id=unit.id,
                content_json=unit.content_json if skill == ModuleType.READING else [],
                question_groups=[
                    SimpleNamespace(
                        id=group.id, questions=[SimpleNamespace(id=q.id) for q in group.questions]
                    )
                    for group in unit.question_groups
                ]
                if skill != ModuleType.WRITING
                else [],
            )
            for unit in items
        ]
    return SimpleNamespace(id=version.id), snapshots


def request(version, skill, unit=None, duration=None, **extra):
    values = {
        "test_version_id": version.id,
        "module": skill,
        "timer": {"mode": "COUNT_UP"}
        if duration is None
        else {"mode": "COUNTDOWN", "duration_seconds": duration},
    }
    if unit:
        values.update(scope="FOCUSED_UNIT", focused_unit={"kind": KINDS[skill], "id": unit.id})
    return AttemptCreate.model_validate({**values, **extra})


@pytest.mark.integration
@pytest.mark.parametrize(
    "skill,index",
    [
        (ModuleType.READING, 1),
        (ModuleType.LISTENING, 1),
        (ModuleType.WRITING, 0),
        (ModuleType.WRITING, 1),
    ],
)
async def test_focused_creation_exam_mutations_review_and_grading(db_session, skill, index):
    version, units = await content(db_session)
    target, other = units[skill][index], units[skill][1 - index]
    service = AttemptService(db_session)
    started = await service.start(request(version, skill, target))
    assert started.scope == AttemptScope.FOCUSED_UNIT and started.attempt_context == "STANDALONE"
    assert started.focused_unit.id == target.id
    assert started.focused_unit.label == (
        f"Task {index + 1}"
        if skill == ModuleType.WRITING
        else f"Passage {index + 1}"
        if skill == ModuleType.READING
        else f"Section {index + 1}"
    )
    exam = await service.exam(started.attempt_id)
    selected = (
        exam.passages
        if skill == ModuleType.READING
        else exam.listening_parts
        if skill == ModuleType.LISTENING
        else exam.writing_tasks
    )
    assert [item.id for item in selected] == [target.id]
    assert "answer_key" not in exam.model_dump_json()
    await db_session.rollback()
    kind = (
        "WRITING_TASK"
        if skill == ModuleType.WRITING
        else "PASSAGE"
        if skill == ModuleType.READING
        else "LISTENING_PART"
    )
    await service.record_navigation(
        started.attempt_id, NavigationRequest(kind=kind, target_id=target.id)
    )
    with pytest.raises(AppError) as failure:
        await service.record_navigation(
            started.attempt_id, NavigationRequest(kind=kind, target_id=other.id)
        )
    assert failure.value.code == "ATTEMPT_TARGET_OUT_OF_SCOPE"
    if skill == ModuleType.WRITING:
        await service.save_writing_response(started.attempt_id, target.id, "A fictional essay.", 0)
        with pytest.raises(AppError) as failure:
            await service.save_writing_response(started.attempt_id, other.id, "Other essay.", 0)
        assert failure.value.code == "ATTEMPT_TARGET_OUT_OF_SCOPE"
    else:
        question, outside = (
            target.question_groups[0].questions[0],
            other.question_groups[0].questions[0],
        )
        await service.save_answer(started.attempt_id, question.id, "fixture", 0)
        await service.save_flag(started.attempt_id, question.id, True)
        await service.record_navigation(
            started.attempt_id, NavigationRequest(kind="QUESTION", target_id=question.id)
        )
        for operation in [
            lambda: service.save_answer(started.attempt_id, outside.id, "fixture", 0),
            lambda: service.save_flag(started.attempt_id, outside.id, True),
            lambda: service.record_navigation(
                started.attempt_id, NavigationRequest(kind="QUESTION", target_id=outside.id)
            ),
            lambda: service.create_highlight(
                started.attempt_id,
                HighlightCreate(
                    target_kind="QUESTION_PROMPT",
                    target_id=outside.id,
                    start_offset=0,
                    end_offset=9,
                    selected_text="Fictional",
                ),
            ),
            lambda: service.create_highlight(
                started.attempt_id,
                HighlightCreate(
                    target_kind="QUESTION_GROUP_OPTION",
                    target_id=other.question_groups[0].id,
                    segment_id=uuid4(),
                    start_offset=0,
                    end_offset=9,
                    selected_text="Fictional",
                ),
            ),
        ]:
            with pytest.raises(AppError) as failure:
                await operation()
            assert failure.value.code == "ATTEMPT_TARGET_OUT_OF_SCOPE"
        async with db_session.begin():
            await db_session.execute(
                update(QuestionGroup)
                .where(QuestionGroup.id == other.question_groups[0].id)
                .values(question_type="text_completion")
            )
        with pytest.raises(AppError) as failure:
            await service.create_highlight(
                started.attempt_id,
                HighlightCreate(
                    target_kind="TEXT_COMPLETION_SEGMENT",
                    target_id=other.question_groups[0].id,
                    segment_id=uuid4(),
                    start_offset=0,
                    end_offset=9,
                    selected_text="Fictional",
                ),
            )
        assert failure.value.code == "ATTEMPT_TARGET_OUT_OF_SCOPE"
        if skill == ModuleType.READING:
            for passage, valid in [(target, True), (other, False)]:
                body = HighlightCreate(
                    passage_id=passage.id,
                    start_block_id=passage.content_json[0]["id"],
                    start_offset=0,
                    end_offset=9,
                    selected_text="Fictional",
                )
                if valid:
                    await service.create_highlight(started.attempt_id, body)
                else:
                    with pytest.raises(AppError) as failure:
                        await service.create_highlight(started.attempt_id, body)
                    assert failure.value.code == "ATTEMPT_TARGET_OUT_OF_SCOPE"
    paused = await service.pause(started.attempt_id)
    assert paused.status == AttemptStatus.PAUSED and paused.scope == started.scope
    await service.resume(started.attempt_id)
    submitted = await service.submit(started.attempt_id)
    assert submitted.band_score is None
    assert (submitted.raw_score, submitted.max_score) == (
        (None, None) if skill == ModuleType.WRITING else (1, 2)
    )
    review = await service.review(started.attempt_id)
    assert len(review.writing_responses if skill == ModuleType.WRITING else review.answers) == 1
    if skill == ModuleType.WRITING:
        await db_session.rollback()
        grade = WritingTaskScoreUpdate(ta=7, cc=7, lr=7, gra=7)
        with pytest.raises(AppError) as failure:
            await service.grade_writing_task(started.attempt_id, other.id, grade)
        assert failure.value.code == "ATTEMPT_TARGET_OUT_OF_SCOPE"
        graded = await service.grade_writing_task(started.attempt_id, target.id, grade)
        assert graded.band_score is None and graded.tasks[0].score.overall == 7
        assert graded.weighted_overall is None
        ai = WritingAIService(db_session, service.user_id, Settings(_env_file=None))
        async with db_session.begin():
            # No model call: validate the input/eligibility boundary only.
            await ai.input(started.attempt_id, target.id, require_essay=False)
        with pytest.raises(AppError) as failure:
            async with db_session.begin():
                await ai.input(started.attempt_id, other.id, require_essay=False)
        assert failure.value.code == "ATTEMPT_TARGET_OUT_OF_SCOPE"
    else:
        detailed = await (
            service.reading_review(started.attempt_id)
            if skill == ModuleType.READING
            else service.listening_review(started.attempt_id)
        )
        assert [
            unit.id
            for unit in (detailed.passages if skill == ModuleType.READING else detailed.parts)
        ] == [target.id]
        await db_session.rollback()


@pytest.mark.integration
@pytest.mark.parametrize("skill", list(ModuleType))
async def test_focused_targets_require_exact_available_version(db_session, skill):
    version, units = await content(db_session)
    foreign, elsewhere = await content(db_session)
    service = AttemptService(db_session)
    for unit in [
        elsewhere[skill][0],
        units[ModuleType.WRITING if skill != ModuleType.WRITING else ModuleType.READING][0],
        SimpleNamespace(id=uuid4()),
    ]:
        with pytest.raises(AppError) as failure:
            await service.start(request(version, skill, unit))
        assert failure.value.code == "FOCUSED_UNIT_INVALID"
    for status, archived in [(VersionStatus.DRAFT, False), (VersionStatus.PUBLISHED, True)]:
        unavailable, targets = await content(db_session, status=status, archived=archived)
        with pytest.raises(AppError) as failure:
            await service.start(request(unavailable, skill, targets[skill][0]))
        assert failure.value.code == "TEST_MODULE_UNAVAILABLE"


@pytest.mark.integration
@pytest.mark.parametrize("skill", list(ModuleType))
async def test_scope_and_timer_policy_and_full_module_compatibility(db_session, skill):
    version, units = await content(db_session)
    service = AttemptService(db_session)
    for duration in PRESETS[skill]:
        assert (
            await service.start(request(version, skill, units[skill][0], duration))
        ).timer_limit_seconds == duration
    for duration in [2400, 3000, 3600, 4200, None]:
        started = await service.start(request(version, skill, duration=duration))
        assert started.scope == AttemptScope.FULL_MODULE and started.focused_unit is None
    exam = await service.exam(started.attempt_id)
    assert (
        len(
            exam.passages
            if skill == ModuleType.READING
            else exam.listening_parts
            if skill == ModuleType.LISTENING
            else exam.writing_tasks
        )
        == 2
    )
    await db_session.rollback()
    for duration in {600, 900, 1200, 1500, 1800, 2100, 2400, 3000, 3600, 4200} - set(
        PRESETS[skill]
    ):
        with pytest.raises(AppError) as failure:
            await service.start(request(version, skill, units[skill][0], duration))
        assert failure.value.code == "INVALID_TIMER_PRESET"
    for duration in [600, 1200, 2100]:
        with pytest.raises(AppError) as failure:
            await service.start(request(version, skill, duration=duration))
        assert failure.value.code == "INVALID_TIMER_PRESET"
    for extra, code in [
        ({"scope": "FOCUSED_UNIT"}, "FOCUSED_UNIT_REQUIRED"),
        (
            {
                "scope": "FULL_MODULE",
                "focused_unit": {"kind": KINDS[skill], "id": units[skill][0].id},
            },
            "INVALID_ATTEMPT_SCOPE",
        ),
        (
            {
                "scope": "FOCUSED_UNIT",
                "focused_unit": {
                    "kind": "WRITING_TASK" if skill != ModuleType.WRITING else "READING_PASSAGE",
                    "id": uuid4(),
                },
            },
            "FOCUSED_UNIT_INVALID",
        ),
    ]:
        with pytest.raises(AppError) as failure:
            await service.start(request(version, skill, **extra))
        assert failure.value.code == code


@pytest.mark.integration
@pytest.mark.parametrize("skill", [ModuleType.READING, ModuleType.LISTENING])
async def test_focused_countdown_auto_submit_scores_selected_unit_only(
    db_session, monkeypatch, skill
):
    version, units = await content(db_session)
    service = AttemptService(db_session)
    started = await service.start(request(version, skill, units[skill][1], 1200))
    await service.save_answer(
        started.attempt_id, units[skill][1].question_groups[0].questions[0].id, "fixture", 0
    )
    monkeypatch.setattr(
        TimerService, "now", staticmethod(lambda: started.started_at + timedelta(seconds=1200))
    )
    expired = await service.get(started.attempt_id)
    assert expired.status == AttemptStatus.AUTO_SUBMITTED
    assert expired.focused_unit.id == units[skill][1].id
    assert (expired.raw_score, expired.max_score, expired.band_score) == (1, 2, None)


@pytest.mark.integration
async def test_history_analytics_and_full_mock_exclude_focused_results(db_session):
    version, units = await content(db_session)
    service = AttemptService(db_session)
    ids = []
    for skill in ModuleType:
        started = await service.start(request(version, skill, units[skill][0]))
        ids.append(started.attempt_id)
        await service.submit(started.attempt_id)
    history = await service.history()
    assert len(history.items) == 3 and history.groups == []
    assert all(
        item.scope == AttemptScope.FOCUSED_UNIT and item.focused_unit for item in history.items
    )
    await db_session.rollback()
    dashboard = await AnalyticsService(db_session).dashboard()
    assert (
        dashboard.total_finalized_attempts == 0
        and dashboard.trends == []
        and dashboard.attempts == []
    )
    await db_session.rollback()
    mock = await SessionService(db_session).start(version.id)
    full = await service.start(request(version, ModuleType.READING))
    await service.submit(full.attempt_id)
    mixed = await service.history()
    assert len(mixed.groups) == 1 and mixed.groups[0].reading.attempt_id == full.attempt_id
    assert mixed.groups[0].listening is None and mixed.groups[0].writing is None
    await db_session.rollback()
    assert mock.current_attempt.scope == AttemptScope.FULL_MODULE
    for _ in range(3):
        snapshot = await SessionService(db_session).get(mock.session.session_id)
        assert snapshot.current_attempt.scope == AttemptScope.FULL_MODULE
        await service.submit(snapshot.current_attempt.attempt_id)
        await SessionService(db_session).advance(mock.session.session_id)
    assert (await SessionService(db_session).get(mock.session.session_id)).status == "COMPLETED"


@pytest.mark.integration
@pytest.mark.parametrize(
    "invalid",
    [
        {"scope": "FOCUSED_UNIT"},
        {"scope": "FULL_MODULE", "focused_reading_passage_id": "READING"},
        {"scope": "FOCUSED_UNIT", "focused_listening_part_id": "LISTENING"},
        {
            "scope": "FOCUSED_UNIT",
            "module_type": "WRITING",
            "focused_reading_passage_id": "READING",
        },
        {
            "scope": "FOCUSED_UNIT",
            "focused_reading_passage_id": "READING",
            "focused_listening_part_id": "LISTENING",
        },
        {"scope": "FOCUSED_UNIT", "focused_reading_passage_id": "MISSING"},
        {
            "scope": "FOCUSED_UNIT",
            "focused_reading_passage_id": "READING",
            "test_session_id": "SESSION",
        },
    ],
)
async def test_database_rejects_invalid_scope_combinations(db_session, invalid):
    version, units = await content(db_session)
    service = AttemptService(db_session)
    started = await service.start(request(version, ModuleType.READING))
    mock = await SessionService(db_session).start(version.id)
    values = {
        key: (
            units[ModuleType(value)][0].id
            if value in {"READING", "LISTENING"}
            else mock.session.session_id
            if value == "SESSION"
            else uuid4()
            if value == "MISSING"
            else value
        )
        for key, value in invalid.items()
    }
    with pytest.raises(IntegrityError):
        async with db_session.begin():
            await db_session.execute(
                update(Attempt).where(Attempt.id == started.attempt_id).values(**values)
            )


@pytest.mark.integration
async def test_focused_unit_fk_restricts_deletion(db_session):
    version, units = await content(db_session)
    await AttemptService(db_session).start(
        request(version, ModuleType.READING, units[ModuleType.READING][0])
    )
    with pytest.raises(IntegrityError):
        async with db_session.begin():
            passage = await db_session.get(ReadingPassage, units[ModuleType.READING][0].id)
            await db_session.delete(passage)
            await db_session.flush()


@pytest.mark.integration
async def test_even_40_question_focused_reading_cannot_become_a_band(db_session):
    from test_attempt_scoring_history import _objective_version

    test = ExamRecord(title="Fictional complete-sized focused unit")
    version = _objective_version()
    test.versions.append(version)
    async with db_session.begin():
        db_session.add(test)
        await db_session.flush()
    service = AttemptService(db_session)
    focused = await service.start(
        request(version, ModuleType.READING, version.modules[0].passages[0])
    )
    full = await service.start(request(version, ModuleType.READING))
    async with db_session.begin():
        for attempt_id in [focused.attempt_id, full.attempt_id]:
            db_session.add_all(
                AttemptAnswer(
                    attempt_id=attempt_id,
                    question=question,
                    value=f"answer {question.number}",
                    is_correct=True,
                )
                for question in version.modules[0].question_groups[0].questions[:20]
            )
    partial = await service.submit(focused.attempt_id)
    complete = await service.submit(full.attempt_id)
    assert (partial.raw_score, partial.max_score, partial.band_score) == (20, 40, None)
    assert complete.max_score == 40 and complete.band_score is not None


@pytest.mark.integration
async def test_focused_writing_history_exposes_task_score_without_overall_band(db_session):
    version, units = await content(db_session)
    service = AttemptService(db_session)
    writing = await service.start(
        request(version, ModuleType.WRITING, units[ModuleType.WRITING][0])
    )
    reading = await service.start(
        request(version, ModuleType.READING, units[ModuleType.READING][0])
    )
    full = await service.start(request(version, ModuleType.WRITING))
    await service.submit(full.attempt_id)
    await service.grade_writing_task(
        full.attempt_id,
        units[ModuleType.WRITING][0].id,
        WritingTaskScoreUpdate(ta=6.5, cc=7.0, lr=6.5, gra=7.0),
    )
    await service.submit(writing.attempt_id)
    history = {item.attempt_id: item for item in (await service.history()).items}
    assert history[writing.attempt_id].task_score is None
    await db_session.rollback()
    await service.grade_writing_task(
        writing.attempt_id,
        units[ModuleType.WRITING][0].id,
        WritingTaskScoreUpdate(ta=6.5, cc=7.0, lr=6.5, gra=7.0),
    )
    # Reload through the history repository, rather than relying on the grading identity map.
    await db_session.rollback()
    db_session.expire_all()
    history = {item.attempt_id: item for item in (await service.history()).items}
    assert history[writing.attempt_id].band_score is None
    assert history[writing.attempt_id].task_score == float(calculate_task_overall(6.5, 7, 6.5, 7))
    assert history[reading.attempt_id].task_score is None
    assert history[full.attempt_id].task_score is None
