from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel

from app.domains.scoring.ielts_band import round_to_half

WRITING_CRITERION_MIN = Decimal("0.0")
WRITING_CRITERION_MAX = Decimal("9.0")
WRITING_CRITERION_STEP = Decimal("0.5")


def validate_writing_criterion_score(value: Decimal) -> Decimal:
    score = Decimal(str(value))
    if (
        score < WRITING_CRITERION_MIN
        or score > WRITING_CRITERION_MAX
        or score % WRITING_CRITERION_STEP != 0
    ):
        raise ValueError("Writing criterion scores must be from 0.0 to 9.0 in 0.5 increments")
    return score


def calculate_task_overall(ta: Decimal, cc: Decimal, lr: Decimal, gra: Decimal) -> Decimal:
    scores = [validate_writing_criterion_score(score) for score in (ta, cc, lr, gra)]
    return sum(scores, start=Decimal("0")) / Decimal(4)


def calculate_weighted_writing_overall(
    task_one_overall: Decimal | None,
    task_two_overall: Decimal | None,
) -> Decimal | None:
    if task_one_overall is None or task_two_overall is None:
        return None
    return (task_one_overall + Decimal(2) * task_two_overall) / Decimal(3)


def calculate_final_writing_band(weighted_overall: Decimal | None) -> Decimal | None:
    return None if weighted_overall is None else round_to_half(weighted_overall)


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
