"""Speaking authoring contracts; incomplete draft text is intentional."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import SpeakingPromptType


class SpeakingPromptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cue_points: list[Annotated[str, Field(max_length=1000)]] = Field(
        default_factory=list, max_length=12
    )


class SpeakingPromptWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_type: SpeakingPromptType
    prompt_text: str = Field(default="", max_length=20_000)
    preparation_seconds: int = Field(default=0, ge=0, le=3600)
    response_seconds: int = Field(default=60, ge=1, le=3600)
    config_json: SpeakingPromptConfig = Field(default_factory=SpeakingPromptConfig)

    @model_validator(mode="before")
    @classmethod
    def long_turn_defaults(cls, data):
        if isinstance(data, dict) and data.get("prompt_type") == SpeakingPromptType.LONG_TURN:
            data = {"preparation_seconds": 60, "response_seconds": 120, **data}
        return data


class SpeakingPartWrite(BaseModel):
    part_number: Literal[1, 2, 3]
    title: str | None = Field(default=None, max_length=240)
    instructions: str | None = Field(default=None, max_length=4000)


class BuilderSpeakingPrompt(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    order_index: int
    prompt_type: SpeakingPromptType
    prompt_text: str
    preparation_seconds: int
    response_seconds: int
    config_json: SpeakingPromptConfig


class BuilderSpeakingPart(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision: int
    part_number: Literal[1, 2, 3]
    title: str | None = None
    instructions: str | None = None
    order_index: int
    prompts: list[BuilderSpeakingPrompt] = Field(default_factory=list)


class SpeakingPromptItem(SpeakingPromptWrite):
    id: UUID | None = None
    order_index: int = Field(ge=0)


class SpeakingPartUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=240)
    instructions: str | None = Field(default=None, max_length=4000)
    prompts: list[SpeakingPromptItem] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_prompts(self):
        ids = [item.id for item in self.prompts if item.id is not None]
        orders = [item.order_index for item in self.prompts]
        if len(ids) != len(set(ids)) or sorted(orders) != list(range(len(orders))):
            raise ValueError("Prompt IDs and canonical order indexes must be unique")
        return self


class SpeakingPromptCreate(SpeakingPromptWrite):
    expected_revision: int = Field(ge=1)


class SpeakingPromptOrderWrite(BaseModel):
    expected_revision: int = Field(ge=1)
    prompt_ids: list[UUID] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(self.prompt_ids) != len(set(self.prompt_ids)):
            raise ValueError("Prompt IDs must be unique")
        return self


class SpeakingPartOrderWrite(BaseModel):
    expected_revision: int = Field(ge=1)
    part_ids: list[UUID] = Field(max_length=3)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(self.part_ids) != len(set(self.part_ids)):
            raise ValueError("Part IDs must be unique")
        return self
