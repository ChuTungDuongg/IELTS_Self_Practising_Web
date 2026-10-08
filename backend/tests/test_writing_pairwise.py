import json

import pytest
from pydantic import ValidationError
from test_tacs_tree import snapshot

from app.providers.writing_llm.base import Completion, ProviderFailure
from app.services.writing_execution import BoundedWritingProvider


class Provider:
    def __init__(self, output='{"preference":"COMPARABLE"}', finish="stop"):
        self.output, self.finish, self.calls = output, finish, []

    async def complete(self, messages, schema, *, options=None):
        self.calls.append((messages, schema, options))
        return Completion(self.output, {"total_tokens": 5}, self.finish)


async def test_actual_message_boundary_excludes_metadata_and_preserves_essay_numbers():
    from app.schemas.tacs import ComparisonResponse
    from app.services.writing_pairwise import PairwiseComparator

    provider = Provider()
    target = ComparisonResponse(
        task_prompt="Fictional chart 7.", response_text="Target has 7 categories."
    )
    human = snapshot().anchors[1]
    response = ComparisonResponse(task_prompt=human.prompt, response_text=human.response_text)
    comparator = PairwiseComparator(BoundedWritingProvider(provider, 1))
    assert (await comparator.compare("lr", target, response)).preference == "COMPARABLE"
    messages, schema, options = provider.calls[0]
    payload = json.loads(messages[1]["content"])
    assert set(payload) == {"response_1", "response_2"}
    assert payload["response_1"] == {
        "task_prompt": "Fictional chart 7.",
        "response_text": "Target has 7 categories.",
    }
    assert payload["response_2"] == {
        "task_prompt": human.prompt,
        "response_text": human.response_text,
    }
    assert set(schema["properties"]) == {"preference"} and options.max_tokens == 128
    assert comparator.usage == [{"total_tokens": 5}]
    with pytest.raises(ValidationError):
        ComparisonResponse.model_validate(human.model_dump())


@pytest.mark.parametrize(
    "output,finish",
    [
        ('{"score":7}', "stop"),
        ('{"preference":"COMPARABLE","score":7}', "stop"),
        ("not json", "stop"),
        ('{"preference":"COMPARABLE"}', "length"),
    ],
)
async def test_invalid_or_truncated_comparison_fails_without_repair(output, finish):
    from app.schemas.tacs import ComparisonResponse
    from app.services.writing_pairwise import PairwiseComparator

    provider = Provider(output, finish)
    response = ComparisonResponse(task_prompt="Task.", response_text="Essay.")
    with pytest.raises(ProviderFailure):
        await PairwiseComparator(provider).compare("cc", response, response)
    assert len(provider.calls) == 1
