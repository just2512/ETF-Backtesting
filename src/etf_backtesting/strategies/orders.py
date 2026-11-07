"""Compile close-derived strategy signals into next-session order intents."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_DOWN

from etf_backtesting.engine.execution import OrderIntent
from etf_backtesting.strategies.bollinger_accumulate import SellSignal


def budget_to_buy_order(
    symbol: str,
    signal_date: date,
    execution_date: date,
    allocated_budget: Decimal,
    signal_close: Decimal,
    lot_size: int = 100,
) -> OrderIntent | None:
    """Size from information known at signal close; next-open gaps may reject the order."""
    if allocated_budget <= 0 or signal_close <= 0 or lot_size < 1:
        raise ValueError("budget/close must be positive and lot_size must be positive")
    estimated_shares = (allocated_budget / signal_close).to_integral_value(rounding=ROUND_DOWN)
    quantity = (estimated_shares // lot_size) * lot_size
    if quantity <= 0:
        return None
    return OrderIntent(
        symbol, "BUY", Decimal(quantity), signal_date, execution_date
    )


def sell_signal_to_order(
    signal: SellSignal,
    execution_date: date,
    current_position: Decimal,
    lot_size: int = 100,
) -> OrderIntent | None:
    if current_position < 0 or lot_size < 1:
        raise ValueError("position must not be negative and lot_size must be positive")
    requested = (
        current_position * Decimal(str(signal.fraction_of_current_position))
    ).to_integral_value(rounding=ROUND_DOWN)
    quantity = (requested // lot_size) * lot_size
    if quantity <= 0:
        return None
    return OrderIntent(
        signal.symbol, "SELL", Decimal(quantity), signal.signal_date, execution_date
    )
