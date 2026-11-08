"""Deterministic shared-cash allocation across ETF buy signals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from etf_backtesting.portfolio.exposure import max_allocation_under_industry_caps


@dataclass(frozen=True, slots=True)
class BuySignal:
    symbol: str
    percent_b: float
    desired_cash: Decimal
    current_market_value: Decimal
    max_market_value: Decimal


@dataclass(frozen=True, slots=True)
class IndustryExposureContext:
    portfolio_value: Decimal
    current_industry_values: Mapping[str, Decimal]
    etf_constituent_weights: Mapping[str, Mapping[str, float]]
    security_industries: Mapping[str, str]
    industry_caps: Mapping[str, Decimal]


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
        industry_context: IndustryExposureContext | None = None,
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
            if signal.max_market_value < 0:
                raise ValueError("configured ETF cap must not be negative")

        spendable = available_cash - reserve_cash
        allocations: list[CashAllocation] = []
        current_industry_values = (
            dict(industry_context.current_industry_values) if industry_context else {}
        )
        for signal in sorted(signals, key=lambda item: (item.percent_b, item.symbol)):
            remaining_cap = signal.max_market_value - signal.current_market_value
            amount = max(Decimal("0"), min(signal.desired_cash, remaining_cap, spendable))
            reason = "ALLOCATED" if amount > 0 else "CAP_OR_CASH_LIMIT"
            if amount > 0 and industry_context:
                weights = industry_context.etf_constituent_weights.get(signal.symbol)
                if weights is None:
                    raise ValueError(f"missing constituent weights for {signal.symbol}")
                allowed = max_allocation_under_industry_caps(
                    amount,
                    industry_context.portfolio_value,
                    current_industry_values,
                    weights,
                    industry_context.security_industries,
                    industry_context.industry_caps,
                )
                if allowed < amount:
                    reason = "INDUSTRY_CAP_LIMIT"
                amount = allowed
                for security, weight in weights.items():
                    industry = industry_context.security_industries[security]
                    current_industry_values[industry] = (
                        current_industry_values.get(industry, Decimal("0"))
                        + amount * Decimal(str(weight))
                    )
            allocations.append(CashAllocation(signal.symbol, signal.desired_cash, amount, reason))
            spendable -= amount
        return allocations
