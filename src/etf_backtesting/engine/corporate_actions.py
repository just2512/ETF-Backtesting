"""ETF-level cash distribution events sourced from fund announcements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ETFDividend:
    symbol: str
    ex_date: date
    record_date: date
    pay_date: date
    cash_per_share: Decimal

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("dividend symbol must not be empty")
        if not self.ex_date <= self.record_date < self.pay_date:
            raise ValueError("dividend dates must satisfy ex_date <= record_date < pay_date")
        if self.cash_per_share < 0:
            raise ValueError("cash_per_share must not be negative")
