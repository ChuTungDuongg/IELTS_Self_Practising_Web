"""AI reads preserve state; Writing recovery belongs to the durable worker scanner."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models import Attempt, WritingAIGradingRun
from app.services.speaking_ai import SpeakingAIService
from app.services.speaking_transcript import SpeakingTranscriptService
from app.services.writing_ai import WritingAIService
from tests.test_classroom_classwork_unit import actor, session_double


@pytest.mark.parametrize("operation", ["list", "snapshot", "get"])
@pytest.mark.parametrize(
    "role,origin",
    [
        ("ADMIN", "direct"),
        ("ADMIN", "parent"),
        ("ADMIN", "personal"),
        ("USER", "direct"),
        ("USER", "personal"),
    ],
)
@pytest.mark.parametrize(
    "status,lease_offset",
    [("PENDING", None), ("RUNNING", None), ("RUNNING", -60), ("RUNNING", 60)],
    ids=["queued", "legacy-stale", "expired-lease", "live-lease"],
)
async def test_writing_ai_reads_preserve_state_until_worker_recovery(
    operation, role, origin, status, lease_offset
):
    current = actor(role)
    assignment_id = uuid4()
    attempt = Attempt(
        id=uuid4(),
        user_id=current.id,
        classroom_assignment_id=assignment_id if origin == "direct" else None,
        test_session_id=uuid4() if origin == "parent" else None,
    )
    now = datetime.now(UTC)
    old = now - timedelta(hours=2)
    run = WritingAIGradingRun(
        id=uuid4(),
        attempt_id=attempt.id,
        writing_task_id=uuid4(),
        requested_by_user_id=current.id,
        status=status,
        lease_token=uuid4() if lease_offset is not None else None,
        lease_expires_at=now + timedelta(seconds=lease_offset)
        if lease_offset is not None
        else None,
        provider="fictional",
        model="fictional",
        prompt_version="fictional",
        input_fingerprint="f" * 64,
        created_at=old,
        updated_at=old,
    )
    session = session_double(assignment_id if origin == "parent" else None)
    session.get = AsyncMock(return_value=current)
    service = WritingAIService(session, current.id, Settings(_env_file=None))
    # Request composition and ORM loading are external to this read-state boundary.
    service.input = AsyncMock(return_value=SimpleNamespace())
    service.repository.attempt = AsyncMock(return_value=attempt)
    service.repository.runs = AsyncMock(return_value=[run])
    service.repository.run = AsyncMock(return_value=run)
    events = []

    async def append_event(_run, event_type, payload):
        events.append(
            SimpleNamespace(
                sequence=len(events) + 1,
                event_type=event_type,
                payload=payload.model_dump(mode="json"),
                created_at=datetime.now(UTC),
            )
        )

    service.repository.append_event = append_event
    service.repository.events = AsyncMock(return_value=events)
    before = deepcopy({column.key: getattr(run, column.key) for column in run.__table__.columns})
    if operation == "list":
        result = (await service.list(attempt.id, run.writing_task_id)).items[0]
    elif operation == "snapshot":
        result, _ = await service.snapshot(run.id, 0)
    else:
        result = await service.get(run.id)
    # Neither personal reads nor classroom observers own lease recovery. In
    # particular, an old updated_at must not terminate a worker with a live lease.
    assert result.status == status and result.error_code is None
    assert before == {key: getattr(run, key) for key in before}
    assert events == []
    session.flush.assert_not_awaited()
    session.add.assert_not_called()
    if operation == "list":
        service.input.assert_awaited_once_with(attempt.id, run.writing_task_id, require_essay=False)
        service.repository.runs.assert_awaited_once_with(attempt.id, run.writing_task_id)
    else:
        service.repository.run.assert_awaited_once_with(run.id, user_id=current.id, lock=True)


@pytest.mark.parametrize("engine", ["speaking_ai", "transcript"])
async def test_speaking_stale_source_reads_only_change_returned_dto(engine):
    admin = actor("ADMIN")
    aid, rid, response_id = uuid4(), uuid4(), uuid4()
    run = SimpleNamespace(
        id=rid,
        attempt_id=aid,
        status="RUNNING",
        stage="SCORING",
        cache_key="fictional",
        manifest_json=[{"response_id": str(response_id), "audio_fingerprint": "old"}],
        responses_json={str(response_id): {"status": "WAITING"}},
        criteria_json={},
        summary_json={},
        raw_mean=None,
        overall_band=None,
        error_code=None,
        created_at=datetime.now(UTC),
    )
    session = session_double(0)
    settings = Settings(_env_file=None)
    if engine == "speaking_ai":
        service = SpeakingAIService(
            session,
            admin,
            settings,
            llm_identity={"provider": "fictional"},
            transcript_identity={"provider": "fictional"},
        )
        service.manifest = AsyncMock(
            return_value=[{"response_id": str(response_id), "audio_fingerprint": "new"}]
        )
    else:
        service = SpeakingTranscriptService(
            session, admin, settings, identity={"provider": "fictional"}
        )
        service.authorized = AsyncMock(
            return_value=[SimpleNamespace(id=response_id, committed_audio_fingerprint="new")]
        )
    service.repository.run = AsyncMock(return_value=run)
    before = deepcopy(vars(run))
    result, events = await service.snapshot(aid, rid)
    assert events == []
    assert before == vars(run)
    assert (result.status if engine == "speaking_ai" else result.responses[0].status) == "FAILED"
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
