import json

import pytest
from test_task1_visual import Task1FakeProvider, request

from app.providers.writing_llm.base import Completion
from app.services.task1_direct import Task1DirectScoringService


async def no_trace(*args):
    pass


@pytest.mark.asyncio
async def test_direct_has_four_score_turns_and_only_ta_receives_grounding():
    provider = Task1FakeProvider()
    service = Task1DirectScoringService(provider)
    result = await service.assess(request(), no_trace)
    assert result is not None
    turns = [m for m in provider.calls if '"score"' in m[0]["content"]]
    assert len(turns) == 4
    for messages in turns:
        payload = json.loads(messages[1]["content"])
        is_ta = "Criterion: Task Achievement." in messages[0]["content"]
        assert ("visual_reference" in payload) == is_ta
        assert "evidence" not in payload
    assert all(not getattr(result.criteria, t).evidence for t in ("ta", "cc", "lr", "gra"))


@pytest.mark.asyncio
async def test_unusable_visual_fails_ta_only():
    service = Task1DirectScoringService(Task1FakeProvider(confidence="UNUSABLE"))
    assert await service.assess(request(), no_trace) is None
    assert set(service.failures) == {"ta"}
    assert all(service.states[t].result for t in ("cc", "lr", "gra"))


@pytest.mark.asyncio
async def test_direct_length_repair_keeps_existing_caps():
    budgets = []

    class Provider(Task1FakeProvider):
        async def complete(self, messages, schema, *, options=None):
            if "score" in schema["properties"]:
                budgets.append(options.max_tokens)
                if len(messages) == 2:
                    return Completion("{}", finish_reason="length")
            return await super().complete(messages, schema, options=options)

    service = Task1DirectScoringService(Provider())
    assert await service.assess(request(), no_trace) is not None
    assert budgets.count(3072) == budgets.count(4096) == 4
