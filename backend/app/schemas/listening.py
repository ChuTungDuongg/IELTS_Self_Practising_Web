from typing import Self

from pydantic import BaseModel, Field, model_validator


class ListeningAudioRange(BaseModel):
    """Optional section boundaries in the module's shared recording."""

    audio_start_seconds: int | None = Field(default=None, ge=0, strict=True)
    audio_end_seconds: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def validate_audio_range(self) -> Self:
        start, end = self.audio_start_seconds, self.audio_end_seconds
        if (start is None) != (end is None):
            raise ValueError("Provide both audio start and end, or leave both empty.")
        if start is not None and end is not None and end <= start:
            raise ValueError("Audio end must be later than audio start.")
        return self
