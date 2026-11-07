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
    announcement_date: date | None = None
    source_name: str | None = None
    source_url: str | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("dividend symbol must not be empty")
        if not self.record_date <= self.ex_date < self.pay_date:
            raise ValueError("dividend dates must satisfy ex_date <= record_date < pay_date")
        if self.cash_per_share < 0:
            raise ValueError("cash_per_share must not be negative")
        provenance = (
            self.announcement_date is not None,
            self.source_name is not None,
            self.source_url is not None,
        )
        if any(provenance) and not all(provenance):
            raise ValueError("dividend provenance requires announcement_date, source_name, and source_url")
        if self.announcement_date is not None and self.announcement_date > self.ex_date:
            raise ValueError("dividend announcement must not postdate the ex-date")
