"""Bollinger bands computed only from observations available at each index."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import pstdev
from typing import Sequence


@dataclass(frozen=True, slots=True)
class BollingerPoint:
    middle: float
    upper: float
    lower: float
    percent_b: float | None


def bollinger_bands(
    closes: Sequence[float],
    period: int = 20,
    deviations: float = 2.0,
) -> list[BollingerPoint | None]:
    if period < 2:
        raise ValueError("period must be at least 2")
    if deviations <= 0:
        raise ValueError("deviations must be positive")
    if any(not isfinite(value) or value <= 0 for value in closes):
        raise ValueError("closes must contain only finite positive prices")

    output: list[BollingerPoint | None] = [None] * len(closes)
    for index in range(period - 1, len(closes)):
        window = closes[index - period + 1:index + 1]
        middle = sum(window) / period
        spread = deviations * pstdev(window)
        upper = middle + spread
        lower = middle - spread
        percent_b = None if upper == lower else (closes[index] - lower) / (upper - lower)
        output[index] = BollingerPoint(middle, upper, lower, percent_b)
    return output
