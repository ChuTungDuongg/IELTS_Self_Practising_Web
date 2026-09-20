from decimal import ROUND_HALF_UP, Decimal

BandInput = float | Decimal | None

_PRODUCT_THRESHOLDS: tuple[tuple[int, float], ...] = (
    (39, 9.0),
    (37, 8.5),
    (35, 8.0),
    (33, 7.5),
    (30, 7.0),
    (27, 6.5),
    (23, 6.0),
    (20, 5.5),
    (16, 5.0),
    (13, 4.5),
    (10, 4.0),
    (7, 3.5),
    (5, 3.0),
    (3, 2.5),
)


def _raw_to_band(raw_score: int, max_score: int) -> float | None:
    if max_score < 0 or raw_score < 0 or raw_score > max_score:
        raise ValueError("Raw score must be between zero and the maximum score")
    if max_score != 40:
        return None
    for threshold, band in _PRODUCT_THRESHOLDS:
        if raw_score >= threshold:
            return band
    return None


def listening_raw_to_band(raw_score: int, max_score: int) -> float | None:
    return _raw_to_band(raw_score, max_score)


def reading_raw_to_band(raw_score: int, max_score: int) -> float | None:
    return _raw_to_band(raw_score, max_score)


def round_to_half(value: Decimal) -> Decimal:
    return (value * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2


def project_overall_band(
    reading: BandInput,
    listening: BandInput,
    writing: BandInput,
) -> float | None:
    scores = (reading, listening, writing)
    if any(score is None for score in scores):
        return None
    decimal_scores = [Decimal(str(score)) for score in scores if score is not None]
    return float(round_to_half(sum(decimal_scores) / Decimal(3)))
