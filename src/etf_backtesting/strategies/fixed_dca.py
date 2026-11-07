"""Fixed-period accumulation signal independent of execution and accounting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CashBudgetSignal:
    symbol: str
    signal_date: date
    budget: Decimal
    reason: str


def fixed_dca_signal(
    symbol: str,
    signal_date: date,
    budget: Decimal,
    scheduled: bool,
) -> CashBudgetSignal | None:
    if budget <= 0:
        raise ValueError("budget must be positive")
    if not scheduled:
        return None
    return CashBudgetSignal(symbol, signal_date, budget, "FIXED_DCA")
