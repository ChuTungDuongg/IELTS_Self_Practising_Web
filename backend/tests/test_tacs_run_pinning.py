import pytest
from test_task1_tacs import HybridProvider
from test_task1_writing_ai import task1 as task1
from test_writing_ai import service, worker
from test_writing_ai import settings as settings
from test_writing_ai import writing as writing
from test_writing_anchors import anchor_input

from app.models import WritingAIGradingRun
from app.services.writing_anchors import WritingAnchorService

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("initial_bank", [False, True])
async def test_enqueue_pins_bank_or_explicit_empty_and_feedback_failure_is_completed(
    db_session, task1, settings, initial_bank
):
    settings.ai_writing_task1_scorer = "anchor_pairwise"
    bank = WritingAnchorService(db_session)
    owner = db_session.info["current_user_id"]
    old = None
    if initial_bank:
        old = await bank.create_draft(owner, "Original")
        for band in (6, 7, 8):
            await bank.create_anchor(owner, old.id, anchor_input(task1[1], band))
        await bank.activate(owner, old.id)
    api = service(db_session, settings)
    created = await api.create(task1[0], task1[1], force=False)
    draft = await bank.create_draft(owner, "Replacement")
    if not initial_bank:
        for band in (6, 7, 8):
            await bank.create_anchor(owner, draft.id, anchor_input(task1[1], band))
    await bank.activate(owner, draft.id)
    provider = HybridProvider(feedback_failure="provider")
    await worker(db_session, settings, provider).execute(created.run_id)
    result, events = await api.snapshot(created.run_id, 0)
    assert result.status == "COMPLETED" and result.task_number == 1
    assert provider.pairwise_calls == (6 if initial_bank else 0)
    async with db_session.begin():
        stored = await db_session.get(WritingAIGradingRun, result.id)
        assert stored.anchor_set_id == (old.id if old else None)
        metadata = stored.scoring_diagnostics_json
    assert metadata["criteria"]["ta"]["mode"] == "GROUNDED_DIRECT"
    if initial_bank:
        assert result.result.criteria.cc.feedback_status == "UNAVAILABLE"
        assert metadata["criteria"]["cc"]["mode"] == "PAIRWISE"
    public = result.model_dump_json() + "".join(e.model_dump_json() for e in events)
    assert all(
        value not in public
        for value in (
            "anchor_set_id",
            "anchor_id",
            "pairwise_calls",
            "Fictional introduction.",
            "POSITION_CONFLICT",
        )
    )
    assert not (await api.create(task1[0], task1[1], force=False)).cache_hit
