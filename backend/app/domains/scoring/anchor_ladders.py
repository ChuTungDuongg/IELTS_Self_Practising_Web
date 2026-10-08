"""Whole-band adjacency shared by admin coverage and language comparison search."""

from collections.abc import Iterable
from decimal import Decimal


def contiguous_ladder(bands: Iterable[Decimal]) -> tuple[int, ...]:
    whole = sorted(
        {
            int(value)
            for value in bands
            if value.is_finite() and value == int(value) and 0 <= value <= 9
        }
    )
    runs: list[list[int]] = []
    for band in whole:
        if not runs or band != runs[-1][-1] + 1:
            runs.append([])
        runs[-1].append(band)
    usable = [run for run in runs if len(run) >= 2]
    if not usable:
        return ()
    return tuple(
        min(
            usable,
            key=lambda run: (
                -len(run),
                -len(set(run) & {6, 7, 8}),
                min(abs(band - 7) for band in run),
                run[0],
            ),
        )
    )
