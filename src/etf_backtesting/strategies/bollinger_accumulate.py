"""Bollinger accumulation/exit state machines with one trigger per band cycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


BUY_TIERS: tuple[tuple[float, float], ...] = (
    (0.0, 0.20),
    (-0.10, 0.20),
    (-0.20, 0.25),
    (-0.30, 0.35),
)


@dataclass(frozen=True, slots=True)
class AccumulationSignal:
    symbol: str
    signal_date: date
    tier_index: int
    budget_fraction: float
    percent_b: float


class BollingerAccumulator:
    def __init__(self) -> None:
        self._triggered: set[int] = set()

    def on_close(
        self,
        symbol: str,
        signal_date: date,
        percent_b: float,
    ) -> list[AccumulationSignal]:
        if percent_b >= 0.5:
            self._triggered.clear()
            return []
        signals = []
        for index, (threshold, fraction) in enumerate(BUY_TIERS):
            if percent_b <= threshold and index not in self._triggered:
                self._triggered.add(index)
                signals.append(AccumulationSignal(
                    symbol, signal_date, index, fraction, percent_b
                ))
        return signals


class BollingerUpperBandSeller:
    def __init__(self, sell_fraction: float = 0.20) -> None:
        if not 0 < sell_fraction <= 1:
            raise ValueError("sell_fraction must be in (0, 1]")
        self.sell_fraction = sell_fraction
        self._sold_this_breakout = False

    def on_close(self, symbol: str, signal_date: date, percent_b: float) -> bool:
        if percent_b < 1.0:
            self._sold_this_breakout = False
            return False
        if self._sold_this_breakout:
            return False
        self._sold_this_breakout = True
        return True
