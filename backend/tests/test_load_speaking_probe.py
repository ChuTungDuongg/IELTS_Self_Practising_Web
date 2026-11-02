"""The fake workload uses actual score-first Speaking contracts, with no transport."""

from benchmarks.load.speaking_probe import measure


async def test_speaking_fake_probe_keeps_score_checkpoints_and_drains_calls():
    result = await measure(jobs=3, concurrency=2, delay=0)
    assert result["completed"] == 3 and result["provider_calls"] == 24
    assert result["score_checkpoints"] == result["completion_checkpoints"] == 12
    assert result["peak_executing_jobs"] <= 2 and result["calls_left_active"] == 0
    assert result["cancel_drained"] is True
