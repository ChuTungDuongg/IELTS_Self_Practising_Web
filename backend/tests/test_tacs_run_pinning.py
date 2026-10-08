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


async def test_queued_obsolete_contract_fails_safely_without_provider_calls(
    db_session, task1, settings, monkeypatch
):
    from app.services import task1_scorer

    settings.ai_writing_task1_scorer = "anchor_pairwise"
    api = service(db_session, settings)
    created = await api.create(task1[0], task1[1], force=False)
    monkeypatch.setattr(task1_scorer, "PAIRWISE_PROMPT_VERSION", "future-contract")

    class Provider(HybridProvider):
        ready_calls = 0

        async def ensure_ready(self):
            self.ready_calls += 1

    provider = Provider()
    await worker(db_session, settings, provider).execute(created.run_id)
    result = await api.get(created.run_id)
    assert result.status == "FAILED"
    assert result.error_code == "AI_CONFIGURATION_CHANGED"
    assert provider.ready_calls == provider.pairwise_calls == provider.feedback_calls == 0
    assert provider.calls == []


async def test_deactivation_preserves_pinned_custom_bank_and_future_runs_use_direct(
    db_session, task1, settings
):
    from sqlalchemy import text
    from test_anchor_source_lifecycle import custom_input

    settings.ai_writing_task1_scorer = "anchor_pairwise"
    bank = WritingAnchorService(db_session)
    owner = db_session.info["current_user_id"]
    working = await bank.begin_edit(owner)
    for band in (6, 7, 8):
        await bank.create_anchor(owner, working.id, custom_input(band=band))
    await bank.activate(owner, working.id)
    api = service(db_session, settings)
    pinned = await api.create(task1[0], task1[1], force=False)
    async with db_session.begin():
        before = await db_session.scalar(
            text("SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM attempt_writing_responses r")
        )
        official = await db_session.scalar(
            text("SELECT jsonb_agg(to_jsonb(s) ORDER BY s.id) FROM attempt_writing_scores s")
        )
        assert official  # Existing official human grades are part of the preservation check.
        attempts = await db_session.scalar(
            text("SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id) FROM attempts a")
        )
    await bank.deactivate(working.id)
    provider = HybridProvider()
    await worker(db_session, settings, provider).execute(pinned.run_id)
    old = await api.get(pinned.run_id)
    assert old.status == "COMPLETED" and provider.pairwise_calls == 6
    future = await api.create(task1[0], task1[1], force=True)
    direct = HybridProvider()
    await worker(db_session, settings, direct).execute(future.run_id)
    assert (await api.get(future.run_id)).status == "COMPLETED" and direct.pairwise_calls == 0
    async with db_session.begin():
        retained = await db_session.get(WritingAIGradingRun, old.id)
        assert retained.anchor_set_id == working.id
        assert retained.scoring_diagnostics_json["criteria"]["ta"]["mode"] == "GROUNDED_DIRECT"
        assert (await db_session.get(WritingAIGradingRun, future.run_id)).anchor_set_id is None
        assert (
            await db_session.scalar(
                text("SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM attempt_writing_responses r")
            )
            == before
        )
        assert (
            await db_session.scalar(
                text("SELECT jsonb_agg(to_jsonb(s) ORDER BY s.id) FROM attempt_writing_scores s")
            )
            == official
        )
        assert (
            await db_session.scalar(
                text("SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id) FROM attempts a")
            )
            == attempts
        )
    assert len((await bank.snapshot(working.id)).anchors) == 3


async def test_custom_task2_bank_never_switches_production_away_from_mts(
    db_session, writing, settings
):
    from test_anchor_source_lifecycle import custom_input
    from test_writing_ai import FakeProvider

    settings.ai_writing_task1_scorer = "anchor_pairwise"
    bank = WritingAnchorService(db_session)
    owner = db_session.info["current_user_id"]
    working = await bank.begin_edit(owner)
    for number in (1, 2):
        for band in (6, 7, 8):
            await bank.create_anchor(owner, working.id, custom_input(number=number, band=band))
    await bank.activate(owner, working.id)
    api = service(db_session, settings)
    created = await api.create(writing[0], writing[2], force=False)
    provider = FakeProvider()
    await worker(db_session, settings, provider).execute(created.run_id)
    result = await api.get(created.run_id)
    assert result.status == "COMPLETED" and result.task_number == 2
    assert len(provider.calls) == 8 and provider.scored == 4  # Existing two-stage MTS per trait.
    async with db_session.begin():
        stored = await db_session.get(WritingAIGradingRun, result.id)
        assert stored.anchor_set_id is None and stored.execution_config_json is None
        assert stored.prompt_version == "mts-task2-v7"
