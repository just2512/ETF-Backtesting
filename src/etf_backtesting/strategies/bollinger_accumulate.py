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

    def on_close(self, symbol: str, signal_date: date, percent_b: float) -> list[AccumulationSignal]:
        if percent_b >= 0.5:
            self._triggered.clear()
            return []
        signals = []
        for index, (threshold, fraction) in enumerate(BUY_TIERS):
            if percent_b <= threshold and index not in self._triggered:
                self._triggered.add(index)
                signals.append(AccumulationSignal(symbol, signal_date, index, fraction, percent_b))
        return signals


@dataclass(frozen=True, slots=True)
class SellSignal:
    symbol: str
    signal_date: date
    fraction_of_current_position: float
    reason: str


class BollingerUpperBandSeller:
    """S0 holds; S1 sells once on breakout; S2 sells in two stages after re-entry."""

    def __init__(
        self,
        mode: str = "S1",
        sell_fraction: float = 0.20,
        first_fraction: float = 0.10,
        second_fraction: float = 0.10,
    ) -> None:
        if mode not in ("S0", "S1", "S2"):
            raise ValueError("mode must be S0, S1, or S2")
        if not 0 < sell_fraction <= 1:
            raise ValueError("sell_fraction must be in (0, 1]")
        if not 0 < first_fraction <= 1 or not 0 < second_fraction <= 1:
            raise ValueError("staged sell fractions must be in (0, 1]")
        if first_fraction + second_fraction > 1:
            raise ValueError("staged sell fractions must not exceed 1")
        self.mode = mode
        self.sell_fraction = sell_fraction
        self.first_fraction = first_fraction
        self.second_fraction = second_fraction
        self._breakout_seen = False
        self._first_sold = False
        self._s1_sold = False

    def on_close(self, symbol: str, signal_date: date, percent_b: float) -> SellSignal | None:
        if self.mode == "S0":
            return None
        if self.mode == "S1":
            if percent_b < 1.0:
                self._s1_sold = False
                return None
            if self._s1_sold:
                return None
            self._s1_sold = True
            return SellSignal(symbol, signal_date, self.sell_fraction, "UPPER_BAND_BREAKOUT")

        if not self._breakout_seen:
            if percent_b >= 1.0:
                self._breakout_seen = True
            return None
        if not self._first_sold and percent_b < 1.0:
            self._first_sold = True
            return SellSignal(symbol, signal_date, self.first_fraction, "UPPER_BAND_REENTRY")
        if self._first_sold and percent_b <= 0.5:
            self._breakout_seen = False
            self._first_sold = False
            return SellSignal(symbol, signal_date, self.second_fraction, "MIDDLE_BAND_REVISIT")
        return None
