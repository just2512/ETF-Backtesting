"""Portfolio valuation, unitized NAV, and drawdown primitives."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Literal


def mark_to_market(
    cash: Decimal,
    positions: dict[str, Decimal],
    closing_prices: dict[str, Decimal],
) -> Decimal:
    missing = sorted(
        symbol for symbol, quantity in positions.items()
        if quantity > 0 and symbol not in closing_prices
    )
    if missing:
        raise ValueError(f"missing closing prices for held symbols: {missing}")
    holdings_value = sum(
        quantity * closing_prices[symbol]
        for symbol, quantity in positions.items()
    )
    return cash + holdings_value


def unitized_nav(
    account_values: Sequence[Decimal],
    external_flows: Sequence[Decimal],
    flow_timing: Literal["BEGINNING", "END"] = "END",
) -> list[Decimal]:
    """Unitize returns while excluding external flows at the declared period boundary."""

    if not account_values or len(account_values) != len(external_flows):
        raise ValueError("account values and external flows must have the same non-zero length")
    if account_values[0] <= 0:
        raise ValueError("initial account value must be positive")
    if flow_timing not in ("BEGINNING", "END"):
        raise ValueError("flow_timing must be BEGINNING or END")
    nav = [Decimal("1")]
    for previous, current, flow in zip(
        account_values[:-1], account_values[1:], external_flows[1:], strict=True
    ):
        if flow_timing == "BEGINNING":
            denominator = previous + flow
            if denominator <= 0 or current <= 0:
                raise ValueError("beginning-flow adjusted account values must be positive")
            period_factor = current / denominator
        else:
            pre_flow_value = current - flow
            if previous <= 0 or pre_flow_value <= 0:
                raise ValueError("end-flow adjusted account values must be positive")
            period_factor = pre_flow_value / previous
        nav.append(nav[-1] * period_factor)
    return nav


def maximum_drawdown(nav_values: Sequence[Decimal]) -> Decimal:
    """Calculate drawdown from a unitized NAV series, not raw values with deposits."""
    if not nav_values:
        raise ValueError("at least one NAV value is required")
    if any(value <= 0 for value in nav_values):
        raise ValueError("NAV values must be positive")
    peak = nav_values[0]
    worst = Decimal("0")
    for value in nav_values:
        peak = max(peak, value)
        drawdown = value / peak - Decimal("1")
        worst = min(worst, drawdown)
    return worst
