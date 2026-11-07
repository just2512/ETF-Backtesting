from datetime import date
from decimal import Decimal

import pytest

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
        cash_limit=Decimal("499"),
    )
    bar = PriceBar("510300", date(2024, 1, 3), 5, 5.1, 4.9, 5)
    result = ExecutionEngine().execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0))
    )

    assert result.status == "REJECTED"
    assert result.reason == "insufficient allocated cash or cash reserve"
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

    assert result.status == "PARTIAL"
    assert result.quantity == Decimal("400")
    assert result.requested_quantity == Decimal("500")
    assert ledger.cash == Decimal("1400")
    assert ledger.positions["510300"] == Decimal("400")


def test_buy_uses_ask_and_applies_slippage_and_market_impact() -> None:
    from etf_backtesting.engine.execution import ExecutionMarketContext, ExecutionModel

    ledger = PortfolioLedger(Decimal("5000"))
    order = OrderIntent(
        "510300", "BUY", Decimal("100"),
        date(2024, 1, 2), date(2024, 1, 3),
    )
    bar = PriceBar("510300", date(2024, 1, 3), 10, 10.2, 9.8, 10)
    context = ExecutionMarketContext(
        bid=Decimal("9.99"),
        ask=Decimal("10.01"),
        limit_up=Decimal("11"),
        limit_down=Decimal("9"),
        suspended=False,
        upper_limit_locked=False,
        lower_limit_locked=False,
    )
    engine = ExecutionEngine(
        execution_model=ExecutionModel(
            slippage_bps=Decimal("5"),
            market_impact_bps=Decimal("10"),
            max_spread_bps=Decimal("30"),
        )
    )
    result = engine.execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0)), context
    )

    assert result.status == "FILLED"
    assert result.fill_price is not None
    assert result.fill_price > Decimal("10.01")
    assert result.fill_price < Decimal("11")


def test_buy_is_not_filled_when_upper_limit_is_locked() -> None:
    from etf_backtesting.engine.execution import ExecutionMarketContext, ExecutionModel

    ledger = PortfolioLedger(Decimal("5000"))
    order = OrderIntent(
        "510300", "BUY", Decimal("100"),
        date(2024, 1, 2), date(2024, 1, 3),
    )
    bar = PriceBar("510300", date(2024, 1, 3), 11, 11, 10, 11)
    context = ExecutionMarketContext(
        bid=Decimal("10.99"),
        ask=Decimal("11"),
        limit_up=Decimal("11"),
        limit_down=Decimal("9"),
        suspended=False,
        upper_limit_locked=True,
        lower_limit_locked=False,
    )
    engine = ExecutionEngine(
        execution_model=ExecutionModel(Decimal("0"), Decimal("0"))
    )
    result = engine.execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0)), context
    )

    assert result.status == "NO_FILL"
    assert result.reason == "upper price limit locked"
    assert ledger.positions == {}


def test_missing_execution_context_is_not_silently_assumed() -> None:
    from etf_backtesting.engine.execution import ExecutionModel

    ledger = PortfolioLedger(Decimal("5000"))
    order = OrderIntent(
        "510300", "BUY", Decimal("100"),
        date(2024, 1, 2), date(2024, 1, 3),
    )
    bar = PriceBar("510300", date(2024, 1, 3), 10, 10.2, 9.8, 10)
    engine = ExecutionEngine(
        execution_model=ExecutionModel(Decimal("0"), Decimal("0"))
    )
    result = engine.execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0))
    )

    assert result.status == "NO_FILL"
    assert result.reason == "execution market context missing"
    assert ledger.cash == Decimal("5000")


def test_execution_model_rejects_impossible_adverse_adjustment() -> None:
    from etf_backtesting.engine.execution import ExecutionModel

    with pytest.raises(ValueError, match="below 10000 bps"):
        ExecutionModel(Decimal("5000"), Decimal("5000"))


def test_buy_partially_fills_to_stay_within_allocated_cash_limit() -> None:
    ledger = PortfolioLedger(Decimal("10000"))
    order = OrderIntent(
        "510300", "BUY", Decimal("500"),
        date(2024, 1, 2), date(2024, 1, 3),
        cash_limit=Decimal("2000"),
    )
    bar = PriceBar("510300", date(2024, 1, 3), 5, 5.1, 4.9, 5)
    result = ExecutionEngine().execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0))
    )

    assert result.status == "PARTIAL"
    assert result.quantity == Decimal("400")
    assert result.requested_quantity == Decimal("500")
    assert ledger.positions["510300"] == Decimal("400")
    assert ledger.cash == Decimal("8000")


def test_execution_rejects_spread_above_configured_maximum() -> None:
    from etf_backtesting.engine.execution import ExecutionMarketContext, ExecutionModel

    ledger = PortfolioLedger(Decimal("5000"))
    order = OrderIntent(
        "510300", "BUY", Decimal("100"),
        date(2024, 1, 2), date(2024, 1, 3),
    )
    bar = PriceBar("510300", date(2024, 1, 3), 10, 11, 9, 10)
    context = ExecutionMarketContext(
        bid=Decimal("9"),
        ask=Decimal("11"),
        limit_up=Decimal("12"),
        limit_down=Decimal("8"),
        suspended=False,
        upper_limit_locked=False,
        lower_limit_locked=False,
    )
    engine = ExecutionEngine(
        execution_model=ExecutionModel(
            Decimal("0"), Decimal("0"), max_spread_bps=Decimal("100")
        )
    )
    result = engine.execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0)), context
    )

    assert result.status == "REJECTED"
    assert result.reason == "spread exceeds configured maximum"
    assert ledger.positions == {}


def test_sell_is_not_filled_when_lower_limit_is_locked() -> None:
    from etf_backtesting.engine.execution import ExecutionMarketContext, ExecutionModel

    ledger = PortfolioLedger(Decimal("0"))
    ledger.buy("510300", Decimal("100"), Decimal("10"), Decimal("0"))
    order = OrderIntent(
        "510300", "SELL", Decimal("100"),
        date(2024, 1, 2), date(2024, 1, 3),
    )
    bar = PriceBar("510300", date(2024, 1, 3), 9, 9.1, 8.9, 9)
    context = ExecutionMarketContext(
        bid=Decimal("8.99"),
        ask=Decimal("9"),
        limit_up=Decimal("11"),
        limit_down=Decimal("9"),
        suspended=False,
        upper_limit_locked=False,
        lower_limit_locked=True,
    )
    engine = ExecutionEngine(
        execution_model=ExecutionModel(Decimal("0"), Decimal("0"))
    )
    result = engine.execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0)), context
    )

    assert result.status == "NO_FILL"
    assert result.reason == "lower price limit locked"
    assert ledger.positions["510300"] == Decimal("100")


def test_non_normal_bar_requires_confirmed_suspension_status() -> None:
    from etf_backtesting.engine.execution import ExecutionMarketContext, ExecutionModel

    ledger = PortfolioLedger(Decimal("5000"))
    order = OrderIntent(
        "510300", "BUY", Decimal("100"),
        date(2024, 1, 2), date(2024, 1, 3),
    )
    bar = PriceBar(
        "510300", date(2024, 1, 3), 10, 10.2, 9.8, 10,
        trade_status="SUSPENDED",
    )
    context = ExecutionMarketContext(
        bid=None,
        ask=None,
        limit_up=Decimal("11"),
        limit_down=Decimal("9"),
        suspended=None,
        upper_limit_locked=False,
        lower_limit_locked=False,
    )
    engine = ExecutionEngine(
        execution_model=ExecutionModel(Decimal("0"), Decimal("0"))
    )
    result = engine.execute_next_open(
        order, bar, ledger, TradingCostModel(Decimal(0), Decimal(0)), context
    )

    assert result.status == "NO_FILL"
    assert result.reason == "suspension status unknown for non-normal bar"
