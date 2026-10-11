"""Internal Task 1 candidate contract; persisted/public result DTOs stay unchanged."""

from typing import Annotated, Any, Literal

from pydantic import Field, StrictStr, StringConstraints, WithJsonSchema

from app.schemas.writing_ai import StrictModel

Aspect = Literal[
    "overview",
    "key_feature",
    "comparison",
    "factual_accuracy",
    "omission",
    "task_fulfilment",
    "progression",
    "grouping",
    "paragraphing",
    "sequencing",
    "cohesion",
    "reference",
    "range",
    "precision",
    "collocation",
    "spelling",
    "word_formation",
    "grammar",
    "sentence_structure",
    "punctuation",
    "style",
]


class RawTask1FeedbackObservation(StrictModel):
    source_id: StrictStr
    kind: Literal["STRENGTH", "LIMITATION", "ERROR", "OPTIONAL_REFINEMENT"]
    aspect: Aspect
    # TA selects validated claims, with NO writable factual display prose.
    # Other criteria supply concise source-grounded Vietnamese observations.
    observation: StrictStr | None
    original_span: Annotated[StrictStr, StringConstraints(strip_whitespace=False)] | None = None
    suggested_revision: StrictStr | None = None
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    claim_id: StrictStr | None = None


class RawTask1FeedbackDraft(StrictModel):
    # As in Task 2, bad items are sanitized locally after strict envelope parsing.
    observations: list[
        Annotated[Any, WithJsonSchema(RawTask1FeedbackObservation.model_json_schema())]
    ] = Field(strict=True)
