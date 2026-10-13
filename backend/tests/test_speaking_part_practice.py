"""Part practice on PostgreSQL; all content/audio is fictional and no providers run."""

import importlib.util
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_speaking_attempts import speaking_content

from app.core.exceptions import AppError
from app.domains.timers import TimerService
from app.models import Attempt, SpeakingPart, SpeakingPrompt
from app.schemas.attempts import AttemptCreate
from app.schemas.classroom_assignments import AssignmentStart
from app.schemas.grading import SpeakingScoreUpdate
from app.services.attempts import AttemptService
from app.services.speaking_attempts import SpeakingAttemptService
from app.services.speaking_final import SpeakingFinalService
from app.services.speaking_media import SpeakingMediaService
from app.storage.local import LocalAssetStorage


def request(version, part, flow="GUIDED", **changes):
    return AttemptCreate.model_validate(
        {
            "test_version_id": version,
            "module": "SPEAKING",
            "scope": "FOCUSED_UNIT",
            "focused_unit": {"kind": "SPEAKING_PART", "id": part},
            "speaking_mode": "PRACTICE",
            "speaking_practice_flow": flow,
            "timer": {"mode": "COUNT_UP"},
            **changes,
        }
    )


async def content(session):
    version, _ = await speaking_content(session)
    async with session.begin():
        parts = list(
            await session.scalars(
                select(SpeakingPart)
                .join(SpeakingPart.module)
                .where(SpeakingPart.module.has(test_version_id=version))
                .order_by(SpeakingPart.part_number)
            )
        )
        for part in parts:
            if part.part_number != 2:
                for index in [1, 2]:
                    session.add(
                        SpeakingPrompt(
                            speaking_part_id=part.id,
                            order_index=index,
                            prompt_type="SHORT_ANSWER",
                            prompt_text=f"Fictional Part {part.part_number} question {index + 1}",
                            response_seconds=60,
                            preparation_seconds=0,
                            config_json={},
                        )
                    )
        await session.flush()
        identities = [p.id for p in parts]
    return version, identities


async def started(session, *, part=1, flow="FREE"):
    version, parts = await content(session)
    aid = (await AttemptService(session).start(request(version, parts[part - 1], flow))).attempt_id
    runtime = SpeakingAttemptService(session)
    async with session.begin():
        attempt = await session.get(Attempt, aid)
        prompts = [p.id for p in await runtime.repository.prompts(attempt)]
    return runtime, aid, prompts, version, parts


@pytest.mark.parametrize(
    "part,flow", [(1, "GUIDED"), (1, "FREE"), (2, "GUIDED"), (3, "GUIDED"), (3, "FREE")]
)
async def test_part_start_scopes_prompts_and_persists_flow(db_session, part, flow):
    runtime, aid, prompts, _, _ = await started(db_session, part=part, flow=flow)
    state = await runtime.get_state(aid)
    assert state.focused_part_number == part and state.practice_flow == flow
    assert state.phase == ("BROWSING" if flow == "FREE" else "QUESTION_ENTER")
    assert state.current_prompt is None if flow == "FREE" else state.current_prompt.id == prompts[0]
    attempt = await AttemptService(db_session).get(aid)
    assert (
        attempt.focused_unit.kind == "SPEAKING_PART"
        and attempt.focused_unit.label == f"Part {part}"
    )
    assert attempt.timer_mode == "COUNT_UP" and attempt.speaking_practice_flow == flow


@pytest.mark.parametrize(
    "changes",
    [
        {"speaking_mode": "EXAM"},
        {"timer": {"mode": "COUNTDOWN", "duration_seconds": 60}},
        {"scope": "FULL_MODULE", "focused_unit": None},
        {"focused_unit": {"kind": "SPEAKING_PROMPT", "id": uuid4()}},
    ],
)
def test_invalid_part_start_contract(changes):
    with pytest.raises(ValidationError):
        request(uuid4(), uuid4(), "FREE", **changes)


def test_part_flow_defaults_guided_and_classroom_contract_is_not_broadened():
    body = request(uuid4(), uuid4(), None)
    assert body.speaking_practice_flow == "GUIDED"
    with pytest.raises(ValidationError):
        AssignmentStart.model_validate(
            {
                "mode": "MODULE",
                **body.model_dump(exclude={"test_version_id", "speaking_practice_flow"}),
            }
        )


async def test_part_two_free_and_foreign_part_rejected(db_session):
    version, parts = await content(db_session)
    with pytest.raises(AppError) as error:
        await AttemptService(db_session).start(request(version, parts[1], "FREE"))
    assert error.value.code == "SPEAKING_FREE_NOT_ALLOWED"
    foreign_version, foreign_parts = await content(db_session)
    assert foreign_version != version
    for part_id in [uuid4(), foreign_parts[0]]:
        with pytest.raises(AppError) as error:
            await AttemptService(db_session).start(request(version, part_id))
        assert error.value.code == "FOCUSED_UNIT_INVALID"


async def test_free_select_commit_last_then_arbitrary_revisit_and_finish(db_session):
    runtime, aid, prompts, _, _ = await started(db_session)
    with pytest.raises(AppError) as error:
        await runtime.finish_practice(aid)
    assert error.value.code == "SPEAKING_COMMITTED_RESPONSE_REQUIRED"
    selected = await runtime.select_prompt(aid, prompts[-1])
    assert selected.phase == "QUESTION_ENTER" and selected.response_id is None
    assert await runtime.repository.response(aid, prompts[-1]) is None
    await db_session.rollback()
    await runtime.begin_prompt(aid, prompts[-1])
    with pytest.raises(AppError):
        await runtime.select_prompt(aid, prompts[0])
    with pytest.raises(AppError):
        await runtime.finish_practice(aid)
    committed = await runtime.finish_current_response(aid, prompts[-1], 1, "USER_DONE")
    assert committed.phase == "BROWSING" and committed.can_finish_practice
    assert (await AttemptService(db_session).get(aid)).status == "IN_PROGRESS"
    await runtime.select_prompt(aid, prompts[0])
    await runtime.select_prompt(aid, prompts[-1])
    restored = await SpeakingAttemptService(db_session).get_state(aid)
    assert restored.can_retry and restored.can_replay
    assert [p.status for p in restored.navigation] == ["UNANSWERED", "UNANSWERED", "COMMITTED"]
    assert await runtime.authorize_current_replay(aid, prompts[-1], 1) == restored.response_id
    await runtime.finish_practice(aid)
    review = await SpeakingMediaService(
        db_session, db_session.info["current_user_identity"]
    ).review(aid)
    assert review.focused_unit.kind == "SPEAKING_PART" and review.practice_flow == "FREE"
    assert len(review.parts) == 1 and len(review.parts[0].responses) == 1
    assert [p.id for p in review.parts[0].unanswered_prompts] == prompts[:2]


async def record(runtime, media, aid, prompt, take, data):
    state = await runtime.get_state(aid)
    segment = await media.create_segment(aid, prompt, take, state.next_segment_index, "audio/webm")
    await media.upload_chunk(aid, segment.id, 0, data)
    await media.close_segment(aid, segment.id, 1)
    await runtime.finish_current_response(aid, prompt, take, "USER_DONE")
    return segment


async def test_free_retry_preserves_last_good_and_other_prompt_takes(
    db_session, tmp_path, monkeypatch
):
    runtime, aid, prompts, _, _ = await started(db_session)
    media = SpeakingMediaService(
        db_session, db_session.info["current_user_identity"], storage=LocalAssetStorage(tmp_path)
    )
    for prompt in prompts[:2]:
        await runtime.select_prompt(aid, prompt)
        await runtime.begin_prompt(aid, prompt)
        await record(runtime, media, aid, prompt, 1, f"fictional-{prompt}".encode())
    await runtime.select_prompt(aid, prompts[0])
    state = await runtime.get_state(aid)
    old_manifest = await media.manifest(aid, state.response_id)
    old_segment = old_manifest.segments[0]
    old_response = await runtime.repository.response(aid, prompts[0])
    old_fingerprint = old_response.committed_audio_fingerprint
    await db_session.rollback()
    retried = await runtime.retry_current_response(aid, prompts[0], 1)
    assert retried.take_number == 2
    response = await runtime.repository.response(aid, prompts[0])
    assert (
        response.locked
        and response.active_take_number == 1
        and response.committed_audio_fingerprint == old_fingerprint
    )
    assert (await runtime.repository.take(response.id, 1)).status == "COMMITTED"
    await db_session.rollback()
    assert (await media.playback(aid, old_segment.id))[0]
    with pytest.raises(AppError):
        await runtime.finish_current_response(aid, prompts[0], 2, "USER_DONE")
    pending = await media.create_segment(aid, prompts[0], 2, 0, "audio/webm")
    await media.upload_chunk(aid, pending.id, 0, b"fictional-pending-retry")
    with pytest.raises(AppError):
        await runtime.finish_current_response(aid, prompts[0], 2, "USER_DONE")
    fallback = await runtime.repository.response(aid, prompts[0])
    assert (
        fallback.active_take_number == 1 and fallback.committed_audio_fingerprint == old_fingerprint
    )
    await db_session.rollback()
    interrupted = await runtime.interrupt(aid, prompts[0], 2, retried.interruption_generation)
    assert interrupted.phase == "INTERRUPTED"
    with pytest.raises(AppError):
        await runtime.select_prompt(aid, prompts[1])
    with pytest.raises(AppError):
        await runtime.finish_practice(aid)
    resumed = await runtime.resume(aid, prompts[0], 2, interrupted.interruption_generation)
    monkeypatch.setattr(
        TimerService,
        "now",
        staticmethod(lambda: resumed.recovery_grace_deadline_at + timedelta(milliseconds=10)),
    )
    await runtime.get_state(aid)
    await record(runtime, media, aid, prompts[0], 2, b"fictional-safe-replacement")
    response = await runtime.repository.response(aid, prompts[0])
    assert (
        response.active_take_number == 2 and response.committed_audio_fingerprint != old_fingerprint
    )
    assert (await runtime.repository.take(response.id, 1)).status == "SUPERSEDED"
    other = await runtime.repository.response(aid, prompts[1])
    assert (
        other.active_take_number == 1
        and (await runtime.repository.take(other.id, 1)).status == "COMMITTED"
    )
    await db_session.rollback()


async def test_every_runtime_mutation_rejects_outside_part(db_session, tmp_path):
    runtime, aid, prompts, _, parts = await started(db_session)
    async with db_session.begin():
        foreign = await db_session.scalar(
            select(SpeakingPrompt.id).where(SpeakingPrompt.speaking_part_id == parts[1])
        )
    await runtime.select_prompt(aid, prompts[0])
    await runtime.begin_prompt(aid, prompts[0])
    media = SpeakingMediaService(
        db_session, db_session.info["current_user_identity"], storage=LocalAssetStorage(tmp_path)
    )
    operations = [
        lambda: runtime.select_prompt(aid, foreign),
        lambda: runtime.begin_prompt(aid, foreign),
        lambda: runtime.finish_current_response(aid, foreign, 1, "USER_DONE"),
        lambda: runtime.retry_current_response(aid, foreign, 1),
        lambda: runtime.authorize_current_replay(aid, foreign, 1),
        lambda: runtime.heartbeat(aid, foreign, 1),
        lambda: media.create_segment(aid, foreign, 1, 0, "audio/webm"),
    ]
    for operation in operations:
        with pytest.raises(AppError) as error:
            await operation()
        assert error.value.code == "ATTEMPT_TARGET_OUT_OF_SCOPE"


async def test_guided_scope_sequence_and_free_operations_denied(db_session, monkeypatch):
    runtime, aid, prompts, _, _ = await started(db_session, part=2, flow="GUIDED")
    now = TimerService.now()
    monkeypatch.setattr(TimerService, "now", staticmethod(lambda: now))
    with pytest.raises(AppError):
        await runtime.select_prompt(aid, prompts[-1])
    with pytest.raises(AppError):
        await runtime.finish_practice(aid)
    assert (await runtime.begin_prompt(aid, prompts[0])).phase == "PREPARING"
    now += timedelta(seconds=63)
    assert (await runtime.get_state(aid)).phase == "RECORDING"
    assert (
        await runtime.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    ).current_prompt.id == prompts[1]
    await runtime.begin_prompt(aid, prompts[1])
    assert (
        await runtime.finish_current_response(aid, prompts[1], 1, "USER_DONE")
    ).phase == "COMPLETED"


async def test_part_final_score_never_promotes_module_history_or_band(db_session):
    runtime, aid, prompts, _, _ = await started(db_session)
    await runtime.select_prompt(aid, prompts[0])
    await runtime.begin_prompt(aid, prompts[0])
    await runtime.finish_current_response(aid, prompts[0], 1, "USER_DONE")
    await runtime.finish_practice(aid)
    final = await SpeakingFinalService(db_session, db_session.info["current_user_identity"]).save(
        aid, SpeakingScoreUpdate(fc=7, lr=7, gra=7, pr=7)
    )
    assert final.final_score.overall_band == 7
    history = await AttemptService(db_session).history()
    row = next(r for r in history.items if r.attempt_id == aid)
    assert (
        row.band_score is None
        and row.scope == "FOCUSED_UNIT"
        and row.speaking_practice_flow == "FREE"
    )
    assert not any(g.speaking and g.speaking.attempt_id == aid for g in history.groups)
    await db_session.rollback()
    from app.core.config import get_settings
    from app.services.analytics import AnalyticsService
    from app.services.speaking_transcript import SpeakingTranscriptService

    analytics = await AnalyticsService(db_session).dashboard()
    assert analytics.bands["SPEAKING"].latest is None
    assert not any(point.attempt_id == aid for point in analytics.trends)
    await db_session.rollback()
    async with db_session.begin():
        transcripts = SpeakingTranscriptService(
            db_session,
            db_session.info["current_user_identity"],
            get_settings(),
            identity={"provider": "fake"},
        )
        rows = await transcripts.authorized(aid)
        assert len(transcripts.manifest(rows)) == 1
        assert rows[0].prompt_id == prompts[0]


async def test_actual_migration_preserves_legacy_and_enforces_exclusive_targets(db_session):
    version, parts = await content(db_session)
    async with db_session.begin():
        prompt = await db_session.scalar(
            select(SpeakingPrompt.id).where(SpeakingPrompt.speaking_part_id == parts[0])
        )
    legacy = await AttemptService(db_session).start(
        AttemptCreate(
            test_version_id=version,
            module="SPEAKING",
            scope="FOCUSED_UNIT",
            focused_unit={"kind": "SPEAKING_PROMPT", "id": prompt},
            timer={"mode": "COUNT_UP"},
        )
    )
    path = Path(__file__).parents[1] / "alembic/versions/20261013_0034_speaking_part_practice.py"
    spec = importlib.util.spec_from_file_location("part_revision", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with db_session.begin():

        def cycle(sync_session):
            with Operations.context(MigrationContext.configure(sync_session.connection())):
                migration.downgrade()
                migration.upgrade()

        await db_session.run_sync(cycle)
    assert (
        await AttemptService(db_session).get(legacy.attempt_id)
    ).focused_unit.kind == "SPEAKING_PROMPT"
    for changes in [
        "focused_speaking_part_id = :part",
        "speaking_practice_flow = 'FREE'",
        "focused_speaking_prompt_id = NULL",
    ]:
        with pytest.raises(IntegrityError):
            async with db_session.begin(), db_session.begin_nested():
                await db_session.execute(
                    text(f"UPDATE attempts SET {changes} WHERE id = :id"),
                    {"id": legacy.attempt_id, "part": parts[0]},
                )


async def test_free_http_routes_require_owner_and_do_not_accept_browser_scope(db_session):
    from teacher_helpers import api_client, make_user

    runtime, aid, prompts, _, _ = await started(db_session)
    owner = db_session.info["current_user_identity"]
    unrelated = await make_user(db_session)
    path = f"/api/v1/speaking-attempts/{aid}/select-prompt"
    async with api_client(db_session, unrelated) as client:
        assert (await client.post(path, json={"prompt_id": str(prompts[0])})).status_code == 404
    async with api_client(db_session, owner) as client:
        assert (
            await client.post(
                path,
                json={
                    "prompt_id": str(prompts[0]),
                    "allowed_prompt_ids": [str(p) for p in prompts],
                },
            )
        ).status_code == 422
        response = await client.post(path, json={"prompt_id": str(prompts[-1])})
        assert response.status_code == 200
        assert response.json()["phase"] == "QUESTION_ENTER"
        assert response.json()["response_id"] is None
        assert (
            await client.post(f"/api/v1/speaking-attempts/{aid}/finish-practice")
        ).status_code == 409
