"""Bounded language-trait search; human bands never cross the comparator boundary."""

import asyncio
import hashlib
import json
from collections.abc import Sequence
from decimal import Decimal

from app.domains.scoring.anchor_ladders import contiguous_ladder
from app.domains.scoring.writing import validate_writing_criterion_score
from app.schemas.tacs import ComparisonResponse, TreeNode, TreeResult
from app.schemas.writing_anchors import LANGUAGE_TRAITS, AnchorRecord, AnchorSnapshot, LanguageTrait
from app.services.writing_execution import TraceFailure, gather_isolated


def representative(
    snapshot: AnchorSnapshot,
    anchors: Sequence[AnchorRecord],
    criterion: LanguageTrait,
    band: int,
    target_fingerprint: str,
) -> AnchorRecord:
    candidates = sorted(
        (anchor for anchor in anchors if getattr(anchor.human_scores, criterion) == band),
        key=lambda anchor: str(anchor.id),
    )
    if not candidates:
        raise ValueError("No representative at this band")
    identity = json.dumps(
        [target_fingerprint, criterion, band, str(snapshot.id), snapshot.version],
        separators=(",", ":"),
    )
    index = int.from_bytes(hashlib.sha256(identity.encode()).digest(), "big") % len(candidates)
    return candidates[index]


def normalize(preference, *, reverse=False):
    if preference == "COMPARABLE":
        return "COMPARABLE"
    first_wins = preference == "RESPONSE_1_BETTER"
    return "TARGET_BETTER" if first_wins != reverse else "ANCHOR_BETTER"


class TACSTree:
    def __init__(self, comparator, max_nodes: int = 2):
        if type(max_nodes) is not int or not 1 <= max_nodes <= 3:
            raise ValueError("Tree node budget must be between 1 and 3")
        self.comparator, self.max_nodes = comparator, max_nodes

    async def score(
        self,
        snapshot: AnchorSnapshot,
        task_number,
        criterion: LanguageTrait,
        target: ComparisonResponse,
        target_fingerprint: str,
        *,
        on_event=None,
    ) -> TreeResult:
        if criterion not in LANGUAGE_TRAITS:
            raise ValueError("TA is never a production pairwise criterion")
        anchors = snapshot.language_anchors(task_number, criterion)
        if not anchors:
            return TreeResult(fallback_reason="NO_ANCHORS")
        remaining = list(
            contiguous_ladder(getattr(anchor.human_scores, criterion) for anchor in anchors)
        )
        if not remaining:
            return TreeResult(fallback_reason="INSUFFICIENT_CONTIGUOUS_COVERAGE")
        nodes = []
        lower = upper = None

        async def emit(event):
            if on_event:
                await on_event(event)

        await emit("anchor.search.started")
        while remaining:
            if len(nodes) == self.max_nodes:
                return TreeResult(nodes=nodes, fallback_reason="BUDGET_EXHAUSTED")
            pivot = 7 if not nodes and 7 in remaining else remaining[(len(remaining) - 1) // 2]
            anchor = representative(snapshot, anchors, criterion, pivot, target_fingerprint)
            other = ComparisonResponse(
                task_prompt=anchor.prompt, response_text=anchor.response_text
            )
            node = TreeNode(band=pivot, anchor_id=anchor.id)
            nodes.append(node)
            await emit("anchor.node.started")

            async def direction(first, second, reverse):
                try:
                    preference = await self.comparator.compare(criterion, first, second)
                except TraceFailure:
                    raise
                except Exception:
                    outcome = None
                else:
                    outcome = normalize(preference.preference, reverse=reverse)
                await emit("anchor.reverse.completed" if reverse else "anchor.forward.completed")
                return outcome

            calls = [
                asyncio.create_task(direction(target, other, False)),
                asyncio.create_task(direction(other, target, True)),
            ]
            try:
                outcomes = await gather_isolated(*calls)
                node.forward, node.reverse = outcomes
            finally:
                for call in calls:
                    if not call.done():
                        call.cancel()
                await asyncio.gather(*calls, return_exceptions=True)
            await emit("anchor.node.completed")
            if node.forward is None or node.reverse is None:
                return TreeResult(nodes=nodes, fallback_reason="PAIRWISE_PROVIDER_FAILURE")
            if node.forward != node.reverse:
                return TreeResult(nodes=nodes, fallback_reason="POSITION_CONFLICT")
            node.result = node.forward
            if node.result == "COMPARABLE":
                await emit("anchor.bracket.completed")
                return TreeResult(
                    nodes=nodes, score=validate_writing_criterion_score(Decimal(pivot))
                )
            if node.result == "TARGET_BETTER":
                lower = pivot
                remaining = [band for band in remaining if band > pivot]
            else:
                upper = pivot
                remaining = [band for band in remaining if band < pivot]
            if lower is not None and upper is not None and upper - lower == 1:
                await emit("anchor.bracket.completed")
                return TreeResult(
                    nodes=nodes,
                    score=validate_writing_criterion_score((Decimal(lower) + Decimal(upper)) / 2),
                )
        return TreeResult(nodes=nodes, fallback_reason="OUT_OF_RANGE")


__all__ = ["TACSTree", "contiguous_ladder", "representative"]
