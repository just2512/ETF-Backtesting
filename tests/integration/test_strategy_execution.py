from datetime import date
from decimal import Decimal

from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.execution import ExecutionEngine, OrderIntent, TradingCostModel
from etf_backtesting.engine.ledger import PortfolioLedger
from etf_backtesting.indicators.bollinger import bollinger_bands
from etf_backtesting.portfolio.cash_pool import BuySignal, CashPoolAllocator
from etf_backtesting.strategies.bollinger_accumulate import BollingerAccumulator


def test_bollinger_signal_to_cash_allocation_to_next_open_ledger() -> None:
    # Synthetic fixture: algorithm wiring only; it is not real ETF market history.
    closes = [10.0] * 19 + [8.0]
    point = bollinger_bands(closes)[-1]
    assert point is not None and point.percent_b is not None and point.percent_b < 0

    signal_date = date(2024, 1, 31)
    execution_date = date(2024, 2, 1)
    signals = BollingerAccumulator().on_close("510300", signal_date, point.percent_b)
    assert [signal.tier_index for signal in signals] == [0, 1, 2, 3]
    assert sum(signal.budget_fraction for signal in signals) == 1.0

    allocations = CashPoolAllocator().allocate(
        Decimal("5000"),
        Decimal("500"),
        [BuySignal("510300", point.percent_b, Decimal("1000"), Decimal("0"), Decimal("2000"))],
    )
    assert allocations[0].allocated_cash == Decimal("1000")

    ledger = PortfolioLedger(Decimal("5000"))
    order = OrderIntent("510300", "BUY", Decimal("100"), signal_date, execution_date)
    next_day_bar = PriceBar(
        "510300", execution_date, 8.1, 8.3, 8.0, 8.2, volume=100000, amount=810000
    )
    result = ExecutionEngine().execute_next_open(
        order, next_day_bar, ledger, TradingCostModel(Decimal("0"), Decimal("0"))
    )

    assert result.status == "FILLED"
    assert result.fill_price == Decimal("8.1")
    assert ledger.positions["510300"] == Decimal("100")
    assert ledger.cash == Decimal("4190")
    assert ledger.events[0].cash_delta == Decimal("-810")
