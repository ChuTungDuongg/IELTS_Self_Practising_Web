"""Advisory Task 2 arithmetic; official Writing grading is deliberately separate."""

from decimal import Decimal

from app.domains.scoring.ielts_band import round_to_half
from app.domains.scoring.writing import calculate_task_overall


def aggregate_ai_task_two(
    ta: Decimal, cc: Decimal, lr: Decimal, gra: Decimal
) -> tuple[Decimal, Decimal]:
    raw_mean = calculate_task_overall(ta, cc, lr, gra)
    return raw_mean, round_to_half(raw_mean)
