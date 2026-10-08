"""Bounded structured completion and the image-only perception service."""

import json
import logging
from typing import Literal, TypeVar

from pydantic import BaseModel, ValidationError

from app.domains.scoring.task1_prompts import DATA_GUARD
from app.domains.writing.visual_families import visual_family
from app.providers.writing_llm.base import (
    LLMProvider,
    Message,
    ProviderFailure,
    safe_finish_reason,
    validate_finish,
)
from app.schemas.task1_visual import (
    ChartTableVisualReference,
    MapVisualReference,
    OtherVisualReference,
    ProcessVisualReference,
    SystemVisualReference,
    VisualGroundingOutput,
)
from app.schemas.writing_ai import OutputDiagnostic, ValidationIssue
from app.services.task1_diagnostics import WrongVisualFamily, safe_task1_issues
from app.services.task1_input import Task1ScoringRequest

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class Task1StructuredCompletion:
    def __init__(
        self,
        provider: LLMProvider,
        usage: list[dict[str, int]],
        diagnostics: list[OutputDiagnostic] | None = None,
    ) -> None:
        self.provider, self.usage = provider, usage
        self.diagnostics = diagnostics if diagnostics is not None else []

    async def structured(
        self,
        messages: list[Message],
        schema: type[T],
        validate=None,
        *,
        repair: bool = True,
        stage: Literal[
            "visual_grounding", "claim_extraction", "claim_verification"
        ] = "visual_grounding",
    ) -> T:
        for attempt in range(2 if repair else 1):
            reason, kind, issues, finish = "SCHEMA_VALIDATION", "SCHEMA_INVALID", [], None
            try:
                completion = await self.provider.complete(
                    messages, schema.model_json_schema(mode="serialization")
                )
                self.usage.append(completion.usage)
                finish = safe_finish_reason(completion.finish_reason)
                validate_finish(completion.finish_reason)
                result = schema.model_validate_json(completion.text)
                if validate:
                    validate(result)
                return result
            except ValidationError as exc:
                issues = safe_task1_issues(exc, schema)
                if any(issue.validation_type == "json_invalid" for issue in issues):
                    reason, kind = "INVALID_JSON", "JSON_INVALID"
            except WrongVisualFamily:
                kind = "WRONG_FAMILY"
                issues = [
                    ValidationIssue(field="reference.visual_family", validation_type="value_error")
                ]
            except ValueError:
                issues = [ValidationIssue(field="<root>", validation_type="value_error")]
            except ProviderFailure as exc:
                reason = exc.reason or "SCHEMA_VALIDATION"
                finish = exc.finish_reason or finish
                kind = {
                    "PROVIDER_FINISH_LENGTH": "FINISH_LENGTH",
                    "INVALID_JSON": "JSON_INVALID",
                }.get(reason, "PROVIDER_INVALID")
                if exc.code not in {"AI_PROVIDER_BAD_RESPONSE", "INVALID_PROVIDER_OUTPUT"}:
                    self._diagnostic(stage, attempt + 1, reason, "PROVIDER_FAILED", issues, finish)
                    raise
            self._diagnostic(stage, attempt + 1, reason, kind, issues, finish)
            if attempt == 0 and repair:
                messages = messages + [
                    {
                        "role": "system",
                        "content": "Return a shorter valid JSON object following the supplied semantic schema, correct family and allowed reference IDs. No extra fields or hidden reasoning. Explanations in Vietnamese. Do not fabricate unreadable values.",
                    }
                ]
        raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE", reason=reason, finish_reason=finish)

    def _diagnostic(self, stage, attempt, reason, kind, issues, finish) -> None:
        self.diagnostics.append(
            OutputDiagnostic(
                stage=stage,
                criterion="ta",
                reason=reason,
                attempt=attempt,
                finish_reason=finish,
                validation_issues=issues,
            )
        )
        prefix = "GROUNDING" if stage == "visual_grounding" else stage.upper()
        for issue in issues or [ValidationIssue(field="<root>", validation_type="provider_output")]:
            logger.warning(
                "Task1 validation failure: stage=%s attempt=%s reason=%s_%s field=%s type=%s",
                stage,
                attempt,
                prefix,
                kind,
                issue.field,
                issue.validation_type,
            )


class Task1VisualGroundingService(Task1StructuredCompletion):
    """Perception only: trusted image and task prompt to a validated reference."""

    async def ground(self, request: Task1ScoringRequest) -> VisualGroundingOutput:
        if request.image is None:
            raise ProviderFailure("AI_PROVIDER_BAD_RESPONSE")
        family = visual_family(request.task_type)

        def validate(output: VisualGroundingOutput) -> None:
            if output.reference.visual_family != family:
                raise WrongVisualFamily()

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
