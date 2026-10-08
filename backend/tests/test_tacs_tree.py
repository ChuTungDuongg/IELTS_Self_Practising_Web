import asyncio
from decimal import Decimal
from uuid import UUID

import pytest

from app.providers.writing_llm.base import ProviderFailure
from app.schemas.writing_anchors import AnchorRecord, AnchorSnapshot, HumanAnchorScores


def snapshot(bands=(6, 7, 8), density=1, task_number=1):
    return AnchorSnapshot(
        id=UUID(int=500),
        version=1,
        anchors=tuple(
            AnchorRecord(
                id=UUID(int=band * 10 + index),
                writing_task_id=UUID(int=10),
                test_version_id=UUID(int=20),
                task_number=task_number,
                task_type=None,
                prompt="Fictional context.",
                response_text=f"Fictional response {band}-{index}.",
                human_scores=HumanAnchorScores(ta=5.5, cc=band, lr=band, gra=band),
            )
            for band in bands
            for index in range(density)
        ),
    )


class Duel:
    def __init__(self, preferences):
        self.preferences = iter(preferences)
        self.calls = []

    async def compare(self, criterion, response_1, response_2):
        from app.schemas.tacs import PairwisePreference

        self.calls.append((criterion, response_1, response_2))
        value = next(self.preferences)
        if isinstance(value, Exception):
            raise value
        return PairwisePreference(preference=value)


@pytest.mark.parametrize(
    "preferences,score,bands",
    [
        (["COMPARABLE", "COMPARABLE"], "7", [7]),
        (
            ["RESPONSE_1_BETTER", "RESPONSE_2_BETTER", "RESPONSE_2_BETTER", "RESPONSE_1_BETTER"],
            "7.5",
            [7, 8],
        ),
        (
            ["RESPONSE_2_BETTER", "RESPONSE_1_BETTER", "RESPONSE_1_BETTER", "RESPONSE_2_BETTER"],
            "6.5",
            [7, 6],
        ),
    ],
)
async def test_binary_nodes_swap_each_response_and_reconstruct_score(preferences, score, bands):
    from app.domains.scoring.tacs import TACSTree
    from app.schemas.tacs import ComparisonResponse

    comparator = Duel(preferences)
    target = ComparisonResponse(task_prompt="Target task.", response_text="Target essay.")
    result = await TACSTree(comparator).score(snapshot(), 1, "lr", target, "fingerprint")
    assert result.score == Decimal(score) and result.fallback_reason is None
    assert [node.band for node in result.nodes] == bands
    assert len(comparator.calls) == 2 * len(bands)
    for forward, reverse in zip(comparator.calls[::2], comparator.calls[1::2], strict=True):
        assert forward[1] == target and reverse[2] == target
        assert forward[2] == reverse[1]


@pytest.mark.parametrize(
    "preferences,reason",
    [
        (["RESPONSE_1_BETTER", "RESPONSE_1_BETTER"], "POSITION_CONFLICT"),
        (["RESPONSE_1_BETTER", "COMPARABLE"], "POSITION_CONFLICT"),
        (["RESPONSE_1_BETTER", "RESPONSE_2_BETTER"] * 2, "OUT_OF_RANGE"),
        ([ProviderFailure("AI_PROVIDER_TIMEOUT"), "COMPARABLE"], "PAIRWISE_PROVIDER_FAILURE"),
    ],
)
async def test_failed_search_never_clamps_retries_or_adds_a_third_vote(preferences, reason):
    from app.domains.scoring.tacs import TACSTree
    from app.schemas.tacs import ComparisonResponse

    comparator = Duel(preferences)
    result = await TACSTree(comparator).score(
        snapshot(),
        1,
        "cc",
        ComparisonResponse(task_prompt="Task.", response_text="Essay."),
        "fingerprint",
    )
    assert result.score is None and result.fallback_reason == reason
    assert len(comparator.calls) == (4 if reason == "OUT_OF_RANGE" else 2)


async def test_node_budget_and_sparse_coverage_bound_calls():
    from app.domains.scoring.tacs import TACSTree
    from app.schemas.tacs import ComparisonResponse

    target = ComparisonResponse(task_prompt="Task.", response_text="Essay.")
    comparator = Duel(["RESPONSE_1_BETTER", "RESPONSE_2_BETTER"] * 2)
    result = await TACSTree(comparator, max_nodes=2).score(
        snapshot((5, 6, 7, 8, 9)), 1, "gra", target, "key"
    )
    assert result.fallback_reason == "BUDGET_EXHAUSTED" and len(comparator.calls) == 4
    empty = Duel([])
    for bank, reason in (
        (snapshot((6, 8)), "INSUFFICIENT_CONTIGUOUS_COVERAGE"),
        (AnchorSnapshot(), "NO_ANCHORS"),
        (snapshot(task_number=2), "NO_ANCHORS"),
    ):
        result = await TACSTree(empty).score(bank, 1, "cc", target, "key")
        assert result.fallback_reason == reason and empty.calls == []


def test_ladder_and_representative_are_stable_without_rounding_labels():
    from app.domains.scoring.tacs import contiguous_ladder, representative

    assert contiguous_ladder(map(Decimal, [2, 3, 6, 7, 8, 8.5])) == (6, 7, 8)
    assert contiguous_ladder(map(Decimal, [6, 8, 7.5])) == ()
    bank = snapshot(density=3)
    first = representative(bank, bank.anchors, "cc", 7, "stable")
    assert first == representative(bank, tuple(reversed(bank.anchors)), "cc", 7, "stable")
    assert first.human_scores.cc == 7
    assert (
        len({representative(bank, bank.anchors, "cc", 7, f"target-{i}").id for i in range(20)}) > 1
    )


async def test_ta_is_not_a_production_tree_trait():
    from app.domains.scoring.tacs import TACSTree
    from app.schemas.tacs import ComparisonResponse

    comparator = Duel([])
    with pytest.raises(ValueError):
        await TACSTree(comparator).score(
            snapshot(), 1, "ta", ComparisonResponse(task_prompt="T", response_text="E"), "key"
        )
    assert comparator.calls == []


async def test_trace_failure_cancels_other_direction_promptly():
    from app.domains.scoring.tacs import TACSTree
    from app.schemas.tacs import ComparisonResponse, PairwisePreference
    from app.services.writing_execution import TraceFailure

    cancelled = asyncio.Event()

    class BlockingDuel:
        async def compare(self, criterion, first, second):
            if first.response_text == "Target":
                return PairwisePreference(preference="COMPARABLE")
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    async def broken_trace(event):
        if event == "anchor.forward.completed":
            raise TraceFailure()

    with pytest.raises(TraceFailure):
        await asyncio.wait_for(TACSTree(BlockingDuel()).score(snapshot(), 1, "cc",
            ComparisonResponse(task_prompt="Task", response_text="Target"), "key", on_event=broken_trace), .3)
    assert cancelled.is_set()
