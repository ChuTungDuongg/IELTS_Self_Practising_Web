from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel


class WritingScoringRequest(BaseModel):
    attempt_id: UUID
    writing_task_id: UUID
    prompt: str
    response: str


class WritingScoringResult(BaseModel):
    overall_band: float
    criterion_scores: dict[str, float]
    feedback: dict[str, Any]


class WritingScoringProvider(Protocol):
    async def score(self, request: WritingScoringRequest) -> WritingScoringResult: ...
