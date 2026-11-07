"""Shared, source-neutral contracts used across workstreams."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Mapping


class AuditStatus(StrEnum):
    PASS = "PASS"
    REJECT = "REJECT"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class PriceBar:
    """Unadjusted executable market OHLCV bar; prices are not total-return adjusted."""

    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    amount: float | None = None
    trade_status: str = "NORMAL"
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        for field_name in ("open", "high", "low", "close"):
            value = getattr(self, field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open, close, and high")
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume must not be negative")
        if self.amount is not None and self.amount < 0:
            raise ValueError("amount must not be negative")


@dataclass(frozen=True, slots=True)
class CorporateAction:
    symbol: str
    ex_date: date
    action_type: str
    cash_per_share: float | None = None
    share_ratio: float | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class AdjustmentFactor:
    symbol: str
    effective_date: date
    factor: float
    factor_type: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class IndexConstituent:
    index_id: str
    constituent_symbol: str
    effective_from: date
    effective_to: date | None = None
    weight: float | None = None
    source: str | None = None

    def active_on(self, when: date) -> bool:
        return self.effective_from <= when and (
            self.effective_to is None or when < self.effective_to
        )


@dataclass(frozen=True, slots=True)
class DataSourceMetadata:
    source_name: str
    source_version: str | None
    retrieved_at: datetime
    snapshot_id: str | None = None
    content_hash: str | None = None
    price_basis: str = "UNADJUSTED"


@dataclass(frozen=True, slots=True)
class AuditFinding:
    status: AuditStatus
    check: str
    message: str
    symbol: str | None = None
    evidence: Mapping[str, object] | None = None
