"""Speaking history/provenance integration against PostgreSQL, fake providers only."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from teacher_helpers import api_client, make_user
from test_speaking_ai_runs import IDENTITY, FakeLLM, grading_worker, service
from test_speaking_transcript import FakeASR, completed

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import Attempt, Classroom, ClassroomAssignment, ClassroomMembership
from app.models import TestSession as SessionRecord
from app.models.speaking import SpeakingMediaCleanup, SpeakingResponse
from app.models.speaking_ai import SpeakingAIGradingRun
from app.models.speaking_transcript import (
    SpeakingNormalizedAudio,
    SpeakingTranscript,
    SpeakingTranscriptRun,
)
from app.schemas.attempts import AttemptCreate
from app.schemas.classroom_assignments import AssignmentStart
from app.services.analytics import AnalyticsService
from app.services.attempts import AttemptService
from app.services.classroom_assignments import ClassroomAssignmentService
from app.services.classroom_results import ClassroomResultService
from app.services.speaking_attempts import SpeakingAttemptService
from app.services.speaking_media import SpeakingMediaService, drain_media_cleanup


async def graded(session, tmp_path, monkeypatch):
    import app.core.config as config
    import app.providers.speaking_llm as llm
    import app.services.speaking_transcript as transcription

    actor = await make_user(session)
    session.info.update(current_user_id=actor.id, current_user_identity=actor)
    aid, rid, media = await completed(session, tmp_path)
    settings = Settings(storage_root=tmp_path)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "config_identity", lambda _: IDENTITY)
    monkeypatch.setattr(transcription, "provider_identity", lambda _: FakeASR.identity)
    created = await service(session, settings).create(aid)
    await grading_worker(session, settings, media.storage, FakeLLM()).execute(created.run_id)
    return actor, aid, rid, media, created.run_id


async def assigned(session, actor, aid):
    teacher = await make_user(session, "TEACHER")
    async with session.begin():
        attempt = await session.get(Attempt, aid)
        room = Classroom(teacher_id=teacher.id, name="Fictional speech class")
        session.add(room)
        await session.flush()
        assignment = ClassroomAssignment(
            classroom_id=room.id,
            test_version_id=attempt.test_version_id,
            created_by_user_id=teacher.id,
        )
        membership = ClassroomMembership(classroom_id=room.id, user_id=actor.id)
        session.add_all([assignment, membership])
        await session.flush()
        attempt.classroom_assignment_id = assignment.id
    for row in (room, assignment, membership):
        session.expunge(row)
    return teacher, room, assignment, membership


async def test_personal_history_has_current_transcript_and_advisory_separate_from_official_band(
    db_session, tmp_path, monkeypatch
):
    actor, aid, _, _, run_id = await graded(db_session, tmp_path, monkeypatch)
    history = await AttemptService(db_session, actor.id).history()
    item = next(i for i in history.items if i.attempt_id == aid)
    assert item.module == "SPEAKING" and item.elapsed_seconds is not None
    assert item.band_score is None
    assert item.speaking_summary.model_dump() == {
        "transcript_status": "COMPLETED",
        "ai_status": "COMPLETED",
        "advisory_overall_band": 6.5,
        "ai_run_id": run_id,
    }
    # This fixture is focused: it belongs in skill history, not the full-test overall.
    assert not any(g.test_version_id == item.test_version_id for g in history.groups)
    await db_session.rollback()
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        attempt.scope, attempt.focused_speaking_prompt_id = "FULL_MODULE", None
    history = await AttemptService(db_session, actor.id).history()
    group = next(g for g in history.groups if g.test_version_id == item.test_version_id)
    assert group.speaking.attempt_id == aid and group.overall_band_score is None
    await db_session.rollback()
    async with db_session.begin():
        response = await db_session.scalar(
            select(SpeakingResponse).where(SpeakingResponse.attempt_id == aid)
        )
        response.committed_audio_fingerprint = "c" * 64
    stale = next(
        i
        for i in (await AttemptService(db_session, actor.id).history()).items
        if i.attempt_id == aid
    )
    assert (
        stale.speaking_summary.advisory_overall_band is None
        and stale.speaking_summary.transcript_status is None
    )


async def test_mock_history_freezes_three_or_four_skill_overall(db_session, tmp_path, monkeypatch):
    actor, aid, _, _, _ = await graded(db_session, tmp_path, monkeypatch)
    now = TimerService.now()
    async with db_session.begin():
        spoken = await db_session.get(Attempt, aid)
        mock = SessionRecord(
            user_id=actor.id,
            test_version_id=spoken.test_version_id,
            started_at=now,
            status="COMPLETED",
            finished_at=now,
            module_order_json=["LISTENING", "READING", "WRITING", "SPEAKING"],
        )
        db_session.add(mock)
        await db_session.flush()
        spoken.test_session_id = mock.id
        spoken.scope, spoken.focused_speaking_prompt_id = "FULL_MODULE", None
        mock_id = mock.id
        for skill in ("LISTENING", "READING", "WRITING"):
            db_session.add(
                Attempt(
                    user_id=actor.id,
                    test_version_id=spoken.test_version_id,
                    test_session_id=mock.id,
                    module_type=skill,
                    timer_mode="COUNT_UP",
                    started_at=now,
                    last_active_at=now,
                    status="SUBMITTED",
                    finished_at=now,
                    band_score=Decimal("7"),
                )
            )
    result = next(
        m
        for m in (await AttemptService(db_session, actor.id).history()).sessions
        if m.session_id == mock_id
    )
    assert result.speaking.attempt_id == aid and result.overall_band_score is None
    assert result.module_order == ["LISTENING", "READING", "WRITING", "SPEAKING"]
    await db_session.rollback()
    async with db_session.begin():
        spoken = await db_session.get(Attempt, aid)
        spoken.band_score = Decimal("5")
    assert (
        next(
            m
            for m in (await AttemptService(db_session, actor.id).history()).sessions
            if m.session_id == mock_id
        ).overall_band_score
        == 6.5
    )
    await db_session.rollback()
    async with db_session.begin():
        legacy_mock = SessionRecord(
            user_id=actor.id,
            test_version_id=result.test_version_id,
            started_at=now,
            status="COMPLETED",
            finished_at=now,
        )
        db_session.add(legacy_mock)
        await db_session.flush()
        legacy_id = legacy_mock.id
        for skill in ("LISTENING", "READING", "WRITING"):
            db_session.add(
                Attempt(
                    user_id=actor.id,
                    test_version_id=result.test_version_id,
                    test_session_id=legacy_id,
                    module_type=skill,
                    timer_mode="COUNT_UP",
                    started_at=now,
                    last_active_at=now,
                    status="SUBMITTED",
                    finished_at=now,
                    band_score=Decimal("7"),
                )
            )
    legacy = next(
        m
        for m in (await AttemptService(db_session, actor.id).history()).sessions
        if m.session_id == legacy_id
    )
    assert legacy.overall_band_score == 7


@pytest.mark.parametrize("historical_change", ["membership", "archive", "revocation"])
async def test_assignment_teacher_read_only_retained_audio_transcript_and_ai(
    db_session, tmp_path, monkeypatch, historical_change
):
    actor, aid, rid, media, run_id = await graded(db_session, tmp_path, monkeypatch)
    teacher, room, assignment, membership = await assigned(db_session, actor, aid)
    result = await ClassroomResultService(db_session, teacher).detail(room.id, assignment.id, aid)
    assert (
        result.speaking_review.attempt_id == aid
        and not result.speaking_review.can_generate_transcript
    )
    assert result.writing_review is None and result.speaking_ai_run.run_id == run_id
    assert result.speaking_ai_run.overall_band == 6.5 and result.attempt.band_score is None
    await db_session.rollback()
    async with db_session.begin():
        if historical_change == "membership":
            (await db_session.get(ClassroomMembership, membership.id)).left_at = TimerService.now()
        elif historical_change == "archive":
            (await db_session.get(Classroom, room.id)).status = "ARCHIVED"
            (await db_session.get(ClassroomAssignment, assignment.id)).status = "ARCHIVED"
        else:
            from app.models import TestVersionModeration

            db_session.add(
                TestVersionModeration(
                    test_version_id=assignment.test_version_id,
                    scope="CLASSROOM",
                    status="REVOKED",
                    submitted_by_user_id=teacher.id,
                )
            )
    retained = await ClassroomResultService(db_session, teacher).detail(room.id, assignment.id, aid)
    assert retained.speaking_review.parts[0].responses[0].response.id == rid
    await db_session.rollback()
    history = await AttemptService(db_session, actor.id).history()
    retained_item = next(i for i in history.items if i.attempt_id == aid)
    assert not retained_item.deletion_allowed
    await db_session.rollback()
    await AttemptService(db_session, actor.id).delete_standalone_history(
        retained_item.test_version_id
    )
    with pytest.raises(AppError) as error:
        await AttemptService(db_session, actor.id).delete_attempt(aid)
    assert error.value.code == "ASSIGNMENT_HISTORY_RETAINED"
    async with db_session.begin():
        assert await db_session.get(SpeakingAIGradingRun, run_id)
        assert await db_session.scalar(
            select(SpeakingTranscript.id).where(SpeakingTranscript.response_id == rid)
        )
    assert (
        (await SpeakingMediaService(db_session, teacher, storage=media.storage).manifest(aid, rid))
        .segments[0]
        .content_url
    )
    async with api_client(db_session, teacher) as client:
        detail = await client.get(
            f"/api/v1/classrooms/{room.id}/assignments/{assignment.id}/attempts/{aid}"
        )
        assert (
            detail.status_code == 200
            and not detail.json()["speaking_review"]["can_generate_transcript"]
        )
        transcript = await client.get(f"/api/v1/speaking-attempts/{aid}/transcript-runs")
        assert (
            transcript.status_code == 200 and transcript.json()["run"]["responses"][0]["verbatim"]
        )


async def test_teacher_cannot_read_same_version_personal_attempt_or_cross_assignment(
    db_session, tmp_path, monkeypatch
):
    actor, aid, rid, media, run_id = await graded(db_session, tmp_path, monkeypatch)
    teacher, room, assignment, _ = await assigned(db_session, actor, aid)
    outsider = await make_user(db_session, "TEACHER")
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        response = await db_session.get(SpeakingResponse, rid)
        version_id, prompt_id = attempt.test_version_id, response.prompt_id
    personal = await AttemptService(db_session, actor.id).start(
        AttemptCreate(
            test_version_id=version_id,
            module="SPEAKING",
            timer={"mode": "COUNT_UP"},
            scope="FOCUSED_UNIT",
            focused_unit={"kind": "SPEAKING_PROMPT", "id": prompt_id},
        )
    )
    with pytest.raises(AppError) as error:
        await ClassroomResultService(db_session, teacher).detail(
            room.id, assignment.id, personal.attempt_id
        )
    assert error.value.code == "ASSIGNMENT_ATTEMPT_NOT_FOUND"
    await db_session.rollback()
    with pytest.raises(AppError):
        await ClassroomResultService(db_session, outsider).detail(room.id, assignment.id, aid)
    await db_session.rollback()
    async with api_client(db_session, teacher) as client:
        assert (
            await client.get(f"/api/v1/speaking-attempts/{personal.attempt_id}/review")
        ).status_code in {403, 409}
        assert (
            await client.post(f"/api/v1/speaking-attempts/{aid}/ai-runs/{run_id}/cancel")
        ).status_code == 403
        assert (
            await client.post(f"/api/v1/speaking-attempts/{aid}/transcript-runs")
        ).status_code == 403
    rows = await ClassroomResultService(db_session, teacher).list(room.id, assignment.id)
    assert [r.attempt.attempt_id for r in rows] == [aid]


async def test_assignment_full_mock_parent_provenance_and_review_lock(
    db_session, tmp_path, monkeypatch
):
    actor, aid, _, _, run_id = await graded(db_session, tmp_path, monkeypatch)
    teacher, room, assignment, _ = await assigned(db_session, actor, aid)
    async with db_session.begin():
        attempt = await db_session.get(Attempt, aid)
        mock = SessionRecord(
            user_id=actor.id,
            test_version_id=attempt.test_version_id,
            started_at=TimerService.now(),
            classroom_assignment_id=assignment.id,
            module_order_json=["LISTENING", "READING", "WRITING", "SPEAKING"],
        )
        db_session.add(mock)
        await db_session.flush()
        sid = mock.id
        attempt.classroom_assignment_id = None
        attempt.test_session_id = sid
        attempt.scope, attempt.focused_speaking_prompt_id = "FULL_MODULE", None
    locked = await ClassroomResultService(db_session, teacher).detail(room.id, assignment.id, aid)
    assert locked.speaking_review is None and locked.speaking_ai_run is None
    await db_session.rollback()
    async with db_session.begin():
        (await db_session.get(SessionRecord, sid)).status = "COMPLETED"
    unlocked = await ClassroomResultService(db_session, teacher).detail(room.id, assignment.id, aid)
    assert unlocked.speaking_review.attempt_id == aid and unlocked.speaking_ai_run.run_id == run_id
    await db_session.rollback()
    assert not next(
        m
        for m in (await AttemptService(db_session, actor.id).history()).sessions
        if m.session_id == sid
    ).deletion_allowed


async def test_personal_delete_cascades_analysis_and_only_queues_owned_files(
    db_session, tmp_path, monkeypatch
):
    actor, aid, rid, media, run_id = await graded(db_session, tmp_path, monkeypatch)
    other_aid, other_rid, other_media = await completed(db_session, tmp_path)
    own_manifest = await media.manifest(aid, rid)
    own_paths, _ = await media.playback(aid, own_manifest.segments[0].id)
    async with db_session.begin():
        own_derived = list(
            await db_session.scalars(
                select(SpeakingNormalizedAudio.storage_key).where(
                    SpeakingNormalizedAudio.response_id == rid
                )
            )
        )
    other_manifest = await other_media.manifest(other_aid, other_rid)
    other_paths, _ = await other_media.playback(other_aid, other_manifest.segments[0].id)
    await AttemptService(db_session, actor.id).delete_attempt(aid)
    async with db_session.begin():
        assert await db_session.get(SpeakingAIGradingRun, run_id) is None
        assert await db_session.get(SpeakingResponse, rid) is None
        assert (
            await db_session.scalar(
                select(SpeakingTranscriptRun.id).where(SpeakingTranscriptRun.attempt_id == aid)
            )
            is None
        )
        queued = set(await db_session.scalars(select(SpeakingMediaCleanup.storage_key)))
        assert set(own_derived) <= queued and len(queued) >= 2
        assert await db_session.get(Attempt, other_aid)
    await drain_media_cleanup(db_session, storage=media.storage)
    assert all(not media.storage.exists(key) for key, _ in own_paths)
    assert all(other_media.storage.exists(key) for key, _ in other_paths)
    assert all(not (media.storage.root / k).exists() for k in own_derived)


async def test_assigned_focused_speaking_start_and_retry_preserve_provenance(
    db_session, tmp_path, monkeypatch
):
    actor, aid, rid, _, _ = await graded(db_session, tmp_path, monkeypatch)
    _, _, assignment, _ = await assigned(db_session, actor, aid)
    async with db_session.begin():
        prompt = (await db_session.get(SpeakingResponse, rid)).prompt_id
    started = await ClassroomAssignmentService(db_session, actor).start(
        assignment.id,
        AssignmentStart(
            mode="MODULE",
            module="SPEAKING",
            scope="FOCUSED_UNIT",
            focused_unit={"kind": "SPEAKING_PROMPT", "id": prompt},
            timer={"mode": "COUNT_UP"},
            speaking_mode="PRACTICE",
        ),
    )
    runtime = SpeakingAttemptService(db_session, actor.id)
    state = await runtime.begin_prompt(started.attempt_id, prompt)
    future = TimerService.now() + timedelta(seconds=1)
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: future))
    state = await runtime.get_state(started.attempt_id)
    assert state.can_retry
    retried = await runtime.retry_current_response(started.attempt_id, prompt, state.take_number)
    assert retried.take_number == 2 and retried.current_prompt.id == prompt
    async with db_session.begin():
        row = await db_session.get(Attempt, started.attempt_id)
        assert row.classroom_assignment_id == assignment.id and row.scope == "FOCUSED_UNIT"


async def test_analytics_speaking_advisory_never_becomes_official_band(
    db_session, tmp_path, monkeypatch
):
    actor, aid, _, _, _ = await graded(db_session, tmp_path, monkeypatch)
    async with db_session.begin():
        row = await db_session.get(Attempt, aid)
        row.scope, row.focused_speaking_prompt_id = "FULL_MODULE", None
    dashboard = await AnalyticsService(db_session, actor.id).dashboard(skill="SPEAKING")
    assert dashboard.total_finalized_attempts == 1 and "SPEAKING" in dashboard.bands
    assert dashboard.bands["SPEAKING"].latest is None and dashboard.latest_project_overall is None
    assert any(a.attempt_id == aid for a in dashboard.attempts)
