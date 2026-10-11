"""Speaking authoring contracts; incomplete draft text is intentional."""

from datetime import datetime
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


class CurrentSpeakingPrompt(BuilderSpeakingPrompt):
    part_number: Literal[1, 2, 3]
    part_title: str | None = None
    instructions: str | None = None


class SpeakingResponseData(BaseModel):
    """Allowlisted spoken-response metadata; never includes private scratch notes."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    prompt_id: UUID
    active_take_number: int
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int
    status: str
    completion_reason: str | None
    locked: bool
    committed_audio_fingerprint: str | None


class SpeakingState(BaseModel):
    attempt_id: UUID
    mode: Literal["PRACTICE", "EXAM"]
    phase: Literal[
        "QUESTION_ENTER",
        "PREPARING",
        "STARTING",
        "RECORDING",
        "FINALIZING",
        "COMPLETED",
        "INTERRUPTED",
        "RECOVERY_GRACE",
    ]
    current_prompt: CurrentSpeakingPrompt | None
    response_id: UUID | None
    take_number: int | None
    phase_started_at: datetime | None
    phase_deadline_at: datetime | None
    remaining_ms: int
    server_time: datetime
    can_retry: bool
    can_replay: bool
    scratch_notes: str = ""
    interruption_generation: int = 0
    interruption_count: int = 0
    recovery_state: str | None = None
    recovery_grace_used: bool = False
    last_resumed_at: datetime | None = None
    recovery_grace_deadline_at: datetime | None = None
    recovery_grace_seconds: int = 7
    recovery_allowed: bool = False
    next_segment_index: int = 0


class SpeakingBegin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_id: UUID


class SpeakingCurrentTake(SpeakingBegin):
    take_number: int = Field(ge=1)


class SpeakingHeartbeat(SpeakingCurrentTake):
    client_remaining_ms: int | None = Field(default=None, ge=0)


class SpeakingRecovery(SpeakingCurrentTake):
    interruption_generation: int = Field(ge=0)


class SpeakingFinish(SpeakingCurrentTake):
    completion_reason: Literal["USER_DONE", "TIMEOUT"]


class SpeakingNotes(SpeakingBegin):
    scratch_notes: str = Field(max_length=20000)


class SpeakingSegmentCreate(SpeakingCurrentTake):
    segment_index: int = Field(ge=0, le=1000)
    mime_type: Literal["audio/webm", "audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"]


class SpeakingSegmentClose(BaseModel):
    chunk_count: int = Field(ge=0, le=10000)


class SpeakingChunkData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sequence: int
    sha256: str
    byte_size: int


class SpeakingSegmentData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    segment_index: int
    mime_type: str
    chunk_count: int | None
    closed_at: datetime | None
    chunks: list[SpeakingChunkData] = Field(default_factory=list)
    content_url: str | None = None


class SpeakingManifest(BaseModel):
    response: SpeakingResponseData
    segments: list[SpeakingSegmentData]
