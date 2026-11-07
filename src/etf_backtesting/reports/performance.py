"""Portfolio valuation and drawdown primitives."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal


def mark_to_market(
    cash: Decimal,
    positions: dict[str, Decimal],
    closing_prices: dict[str, Decimal],
) -> Decimal:
    missing = sorted(symbol for symbol, quantity in positions.items()
                     if quantity > 0 and symbol not in closing_prices)
    if missing:
        raise ValueError(f"missing closing prices for held symbols: {missing}")
    holdings_value = sum(
        quantity * closing_prices[symbol]
        for symbol, quantity in positions.items()
    )
    return cash + holdings_value


def maximum_drawdown(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("at least one account value is required")
    if any(value <= 0 for value in values):
        raise ValueError("account values must be positive")
    peak = values[0]
    worst = Decimal("0")
    for value in values:
        peak = max(peak, value)
        drawdown = value / peak - Decimal("1")
        worst = min(worst, drawdown)
    return worst
