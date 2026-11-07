"""Deterministic shared-cash allocation across ETF buy signals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BuySignal:
    symbol: str
    percent_b: float
    desired_cash: Decimal
    current_market_value: Decimal
    max_market_value: Decimal


@dataclass(frozen=True, slots=True)
class CashAllocation:
    symbol: str
    requested_cash: Decimal
    allocated_cash: Decimal
    reason: str


class CashPoolAllocator:
    def allocate(
        self,
        available_cash: Decimal,
        reserve_cash: Decimal,
        signals: list[BuySignal],
    ) -> list[CashAllocation]:
        if available_cash < 0 or reserve_cash < 0:
            raise ValueError("cash values must not be negative")
        if reserve_cash > available_cash:
            raise ValueError("reserve cash cannot exceed available cash")
        if len({signal.symbol for signal in signals}) != len(signals):
            raise ValueError("each ETF may appear only once per allocation batch")
        for signal in signals:
            if signal.desired_cash < 0 or signal.current_market_value < 0:
                raise ValueError("signal cash and market values must not be negative")
            if signal.max_market_value < signal.current_market_value:
                raise ValueError("current market value exceeds configured ETF cap")

        spendable = available_cash - reserve_cash
        allocations: list[CashAllocation] = []
        for signal in sorted(signals, key=lambda item: (item.percent_b, item.symbol)):
            remaining_cap = signal.max_market_value - signal.current_market_value
            amount = min(signal.desired_cash, remaining_cap, spendable)
            reason = "ALLOCATED" if amount > 0 else "CAP_OR_CASH_LIMIT"
            allocations.append(CashAllocation(signal.symbol, signal.desired_cash, amount, reason))
            spendable -= amount
        return allocations
