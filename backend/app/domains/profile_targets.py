from decimal import Decimal

from app.domains.scoring.ielts_band import round_to_half


def calculate_profile_target_band(
    listening: Decimal | None,
    reading: Decimal | None,
    writing: Decimal | None,
    speaking: Decimal | None,
) -> Decimal | None:
    targets = (listening, reading, writing, speaking)
    if any(target is None for target in targets):
        return None
    return round_to_half(sum(target for target in targets if target is not None) / Decimal(4))
