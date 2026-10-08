from pydantic import ValidationError

from app.domains.scoring.tacs_prompts import pairwise_messages
from app.providers.writing_llm.base import CompletionOptions, ProviderFailure, validate_finish
from app.schemas.tacs import ComparisonResponse, PairwisePreference
from app.schemas.writing_anchors import LanguageTrait


class PairwiseComparator:
    """One short completion per ordering, with no model repair or score metadata."""

    def __init__(self, provider, *, usage=None):
        self.provider = provider
        self.usage = usage if usage is not None else []

    async def compare(
        self,
        criterion: LanguageTrait,
        response_1: ComparisonResponse,
        response_2: ComparisonResponse,
    ) -> PairwisePreference:
        completion = await self.provider.complete(
            pairwise_messages(criterion, response_1, response_2),
            PairwisePreference.model_json_schema(),
            options=CompletionOptions(max_tokens=128),
        )
        self.usage.append(completion.usage)
        validate_finish(completion.finish_reason)
        try:
            return PairwisePreference.model_validate_json(completion.text)
        except ValidationError:
            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="SCHEMA_VALIDATION") from None
