from datetime import date
from decimal import Decimal

from etf_backtesting.strategies.bollinger_accumulate import SellSignal
from etf_backtesting.strategies.orders import budget_to_buy_order, sell_signal_to_order


def test_buy_order_quantity_uses_signal_close_and_whole_lots() -> None:
    order = budget_to_buy_order(
        "510300", date(2024, 1, 2), date(2024, 1, 3),
        Decimal("1050"), Decimal("10"), 100
    )
    assert order is not None
    assert order.quantity == Decimal("100")
    assert order.execution_date > order.signal_date


def test_sell_order_uses_fraction_of_current_position_and_whole_lots() -> None:
    signal = SellSignal("510300", date(2024, 1, 2), 0.2, "UPPER_BAND_BREAKOUT")
    order = sell_signal_to_order(signal, date(2024, 1, 3), Decimal("550"), 100)
    assert order is not None
    assert order.quantity == Decimal("100")


def test_order_compiler_skips_budgets_below_one_lot() -> None:
    assert budget_to_buy_order(
        "510300", date(2024, 1, 2), date(2024, 1, 3),
        Decimal("500"), Decimal("10"), 100
    ) is None
