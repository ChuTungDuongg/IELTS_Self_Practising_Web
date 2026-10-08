import json

import pytest
from test_tacs_tree import snapshot
from test_task1_direct import no_trace
from test_task1_visual import Task1FakeProvider, request

from app.providers.writing_llm.base import Completion, ProviderFailure
from app.services.task1_tacs import Task1TACSScoringService


class HybridProvider(Task1FakeProvider):
    def __init__(self, feedback_failure=None, conflict=False):
        super().__init__()
        self.pairwise_calls = self.feedback_calls = 0
        self.feedback_failure, self.conflict = feedback_failure, conflict

    async def complete(self, messages, schema, *, options=None):
        if "preference" in schema["properties"]:
            self.pairwise_calls += 1
            assert options.max_tokens == 128
            return Completion(
                json.dumps({"preference": "RESPONSE_1_BETTER" if self.conflict else "COMPARABLE"}),
                {"total_tokens": 2},
            )
        if "criteria" in schema["properties"]:
            self.feedback_calls += 1
            assert options.max_tokens == 4096
            if self.feedback_failure == "provider":
                raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE")
            data = {
                t: {"feedback": "Diễn đạt rõ.", "strengths": ["Mạch lạc."], "improvements": []}
                for t in json.loads(messages[1]["content"])["criteria"]
            }
            if self.feedback_failure == "score":
                data["cc"]["score"] = 9
            return Completion(json.dumps({"criteria": data}), {"total_tokens": 5})
        return await super().complete(messages, schema, options=options)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "provider", "score"])
async def test_score_survives_feedback_boundary_and_no_rescore(failure):
    provider = HybridProvider(feedback_failure=failure)
    bank = snapshot()
    service = Task1TACSScoringService(provider, anchor_snapshot=bank, target_fingerprint="target")
    result = await service.assess(request(), no_trace)
    assert result is not None and result.overall_band == 7
    assert provider.pairwise_calls == 6 and provider.feedback_calls == 1
    assert len([m for m in provider.calls if '"score"' in m[0]["content"]]) == 1
    for trait in ("cc", "lr", "gra"):
        criterion = getattr(result.criteria, trait)
        assert criterion.score == 7
        assert criterion.feedback_status == ("AVAILABLE" if failure is None else "UNAVAILABLE")
        assert (criterion.feedback is None) == (failure is not None)
        assert service.scoring_metadata()["criteria"][trait]["mode"] == "PAIRWISE"
    assert service.scoring_metadata()["criteria"]["ta"]["mode"] == "GROUNDED_DIRECT"
    assert not service.failures


@pytest.mark.asyncio
async def test_empty_bank_and_position_conflict_direct_fallback():
    for bank, conflict, calls in [(snapshot(bands=()), False, 0), (snapshot(), True, 6)]:
        provider = HybridProvider(conflict=conflict)
        service = Task1TACSScoringService(
            provider, anchor_snapshot=bank, target_fingerprint="target"
        )
        result = await service.assess(request(), no_trace)
        assert result is not None
        assert provider.pairwise_calls == calls and provider.feedback_calls == 0
        assert all(
            service.scoring_metadata()["criteria"][t]["mode"] == "DIRECT_FALLBACK"
            for t in ("cc", "lr", "gra")
        )


@pytest.mark.asyncio
async def test_ta_never_accesses_language_bank(monkeypatch):
    bank = snapshot()
    original = type(bank).language_anchors

    def guarded(self, task, trait):
        assert trait != "ta"
        return original(self, task, trait)

    monkeypatch.setattr(type(bank), "language_anchors", guarded)
    service = Task1TACSScoringService(
        HybridProvider(), anchor_snapshot=bank, target_fingerprint="target"
    )
    assert await service.assess(request(), no_trace) is not None
