from datetime import date
from decimal import Decimal

from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.execution import ExecutionEngine, OrderIntent, TradingCostModel
from etf_backtesting.engine.ledger import PortfolioLedger


def test_buy_executes_at_next_session_open_with_explicit_fees() -> None:
    ledger = PortfolioLedger(Decimal("10000"))
    order = OrderIntent("510300", "BUY", Decimal("100"), date(2024, 1, 2), date(2024, 1, 3))
    bar = PriceBar("510300", date(2024, 1, 3), 3.8, 3.9, 3.7, 3.85)
    costs = TradingCostModel(Decimal("0.00015"), Decimal("0.00004"))
    result = ExecutionEngine().execute_next_open(order, bar, ledger, costs)

    assert result.status == "FILLED"
    assert result.fill_price == Decimal("3.8")
    assert ledger.positions["510300"] == Decimal("100")
    assert ledger.events[0].cash_delta < 0


def test_execution_rejects_same_day_signal_and_fill() -> None:
    try:
        OrderIntent("510300", "BUY", Decimal("100"), date(2024, 1, 3), date(2024, 1, 3))
    except ValueError as exc:
        assert "later than signal date" in str(exc)
    else:
        raise AssertionError("same-day execution must be rejected")


def test_halted_bar_does_not_fill() -> None:
    ledger = PortfolioLedger(Decimal("10000"))
    order = OrderIntent("510300", "BUY", Decimal("100"), date(2024, 1, 2), date(2024, 1, 3))
    bar = PriceBar("510300", date(2024, 1, 3), 3.8, 3.9, 3.7, 3.85, trade_status="SUSPENDED")
    result = ExecutionEngine().execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0))
    )
    assert result.status == "NO_FILL"
    assert ledger.cash == Decimal("10000")


def test_buy_rejects_open_gap_above_allocated_budget() -> None:
    ledger = PortfolioLedger(Decimal("10000"))
    order = OrderIntent(
        "510300",
        "BUY",
        Decimal("500"),
        date(2024, 1, 2),
        date(2024, 1, 3),
        cash_limit=Decimal("2000"),
    )
    bar = PriceBar("510300", date(2024, 1, 3), 5, 5.1, 4.9, 5)
    result = ExecutionEngine().execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0))
    )

    assert result.status == "REJECTED"
    assert result.reason == "execution cost exceeds allocated cash budget"
    assert ledger.cash == Decimal("10000")
    assert ledger.positions == {}


def test_buy_cannot_breach_configured_minimum_cash_reserve() -> None:
    ledger = PortfolioLedger(Decimal("5000"))
    order = OrderIntent(
        "510300",
        "BUY",
        Decimal("500"),
        date(2024, 1, 2),
        date(2024, 1, 3),
    )
    bar = PriceBar("510300", date(2024, 1, 3), 9, 9.1, 8.9, 9)
    result = ExecutionEngine(
        minimum_cash_reserve=Decimal("1000")
    ).execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0))
    )

    assert result.status == "REJECTED"
    assert result.reason == "minimum cash reserve would be breached"
    assert ledger.cash == Decimal("5000")
    assert ledger.positions == {}
