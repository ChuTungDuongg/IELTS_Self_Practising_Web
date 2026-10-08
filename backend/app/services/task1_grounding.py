"""Bounded structured completion and the image-only perception service."""

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.domains.scoring.task1_prompts import DATA_GUARD
from app.domains.writing.visual_families import visual_family
from app.providers.writing_llm.base import LLMProvider, Message, ProviderFailure, validate_finish
from app.schemas.task1_visual import (
    ChartTableVisualReference,
    MapVisualReference,
    OtherVisualReference,
    ProcessVisualReference,
    SystemVisualReference,
    VisualGroundingOutput,
)
from app.services.task1_input import Task1ScoringRequest

T = TypeVar("T", bound=BaseModel)


class Task1StructuredCompletion:
    def __init__(self, provider: LLMProvider, usage: list[dict[str, int]]) -> None:
        self.provider, self.usage = provider, usage

    async def structured(
        self, messages: list[Message], schema: type[T], validate=None, *, repair: bool = True
    ) -> T:
        for attempt in range(2 if repair else 1):
            try:
                completion = await self.provider.complete(
                    messages, schema.model_json_schema(mode="serialization")
                )
                self.usage.append(completion.usage)
                validate_finish(completion.finish_reason)
                result = schema.model_validate_json(completion.text)
                if validate:
                    validate(result)
                return result
            except (ValidationError, ValueError):
                pass
            except ProviderFailure as exc:
                if exc.code not in {"AI_PROVIDER_BAD_RESPONSE", "INVALID_PROVIDER_OUTPUT"}:
                    raise
            if attempt == 0 and repair:
                messages = messages + [
                    {
                        "role": "system",
                        "content": "Return a shorter valid JSON object following the supplied semantic schema, correct family and allowed reference IDs. No extra fields or hidden reasoning. Explanations in Vietnamese. Do not fabricate unreadable values.",
                    }
                ]
        raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason="SCHEMA_VALIDATION")


class Task1VisualGroundingService(Task1StructuredCompletion):
    """Perception only: trusted image and task prompt to a validated reference."""

    async def ground(self, request: Task1ScoringRequest) -> VisualGroundingOutput:
        if request.image is None:
            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE")
        family = visual_family(request.task_type)

        def validate(output: VisualGroundingOutput) -> None:
            if output.reference.visual_family != family:
                raise ValueError("Wrong visual family")

        output = await self.structured(
            [
                {
                    "role": "system",
                    "content": f"{DATA_GUARD} Extract visual information only, never IELTS scores or final feedback. Required family: {family.value}. Use at most 2 components and 10 points/stages/features per component where possible. Include all major features. Never fabricate unreadable numbers: value=null, low point confidence; downgrade overall confidence when coverage is incomplete. For chart points set value_is_labelled=true only for a readable printed numeric label; false for visual estimates, whose confidence should remain below 0.8. Preserve separate components/units/snapshots for mixed charts; tables use headers/cells; pies have no invented axes; ordered_categories=true only for an explicitly ordered/time dimension. Process edges, map states/changes and system connections must reference declared IDs. Map locations are qualitative, no invented coordinates. Schema: {json.dumps(VisualGroundingOutput.model_json_schema(mode='serialization'))}",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {"task_type": request.task_type.value, "question": request.prompt},
                                ensure_ascii=False,
                            ),
                        },
                        request.image,
                    ],
                },
            ],
            VisualGroundingOutput,
            validate,
        )
        reference = output.reference
        match reference:
            case ChartTableVisualReference():
                usable = any(
                    component.series or component.cells for component in reference.components
                )
            case ProcessVisualReference():
                usable = bool(reference.stages)
            case MapVisualReference():
                usable = any(state.features for state in reference.states)
            case SystemVisualReference():
                usable = bool(reference.components)
            case OtherVisualReference():
                usable = bool(reference.entities or reference.observations)
        if not usable:
            reference.confidence = "UNUSABLE"
        return output
