from datetime import date
from decimal import Decimal

from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.corporate_actions import ETFDividend
from etf_backtesting.engine.execution import OrderIntent, TradingCostModel
from etf_backtesting.engine.runner import PortfolioBacktestRunner
from etf_backtesting.reports.performance import unitized_nav


def test_runner_executes_orders_and_tracks_external_contributions() -> None:
    day1 = date(2024, 1, 2)
    day2 = date(2024, 1, 3)
    bars = {
        "510300": [
            PriceBar("510300", day1, 10, 11, 9.9, 11),
        ],
        "510880": [
            PriceBar("510880", day2, 5, 5.1, 4.9, 5),
        ],
    }
    orders = [
        OrderIntent("510300", "BUY", Decimal("100"), date(2024, 1, 1), day1),
    ]
    result = PortfolioBacktestRunner().run(
        bars,
        orders,
        Decimal("1000"),
        TradingCostModel(Decimal("0"), Decimal("0")),
        contributions={day2: Decimal("100")},
    )

    assert result.executions[0].status == "FILLED"
    assert result.ledger.positions["510300"] == Decimal("100")
    assert result.snapshots[0].phase == "PRE_OPEN"
    assert result.snapshots[0].total_value == Decimal("1000")
    assert result.snapshots[1].total_value == Decimal("1100")
    assert result.snapshots[2].external_contribution == Decimal("100")
    assert result.snapshots[2].stale_symbols == ("510300",)
    nav = unitized_nav(
        [item.total_value for item in result.snapshots],
        [item.external_contribution for item in result.snapshots],
        flow_timing="BEGINNING",
    )
    assert nav[1] == Decimal("1.1")
    assert nav[2] == Decimal("1.1")


def test_runner_records_no_fill_when_execution_bar_is_absent() -> None:
    day = date(2024, 1, 2)
    order = OrderIntent("510300", "BUY", Decimal("100"), date(2024, 1, 1), day)
    result = PortfolioBacktestRunner().run(
        {},
        [order],
        Decimal("1000"),
        TradingCostModel(Decimal("0"), Decimal("0")),
    )
    assert result.executions[0].status == "NO_FILL"
    assert result.ledger.cash == Decimal("1000")



def test_runner_credits_etf_dividend_using_record_date_shares() -> None:
    day1 = date(2024, 1, 2)
    ex_date = date(2024, 1, 3)
    pay_date = date(2024, 1, 5)
    bars = {
        "510300": [
            PriceBar("510300", day1, 10, 10, 10, 10),
            PriceBar("510300", ex_date, 9.5, 9.5, 9.5, 9.5),
            PriceBar("510300", pay_date, 9.5, 9.5, 9.5, 9.5),
        ]
    }
    order = OrderIntent("510300", "BUY", Decimal("100"), date(2024, 1, 1), day1)
    dividend = ETFDividend(
        "510300", ex_date, day1, pay_date, Decimal("0.5")
    )
    result = PortfolioBacktestRunner().run(
        bars,
        [order],
        Decimal("1000"),
        TradingCostModel(Decimal("0"), Decimal("0")),
        dividends=[dividend],
    )
    pay_snapshot = next(item for item in result.snapshots if item.trade_date == pay_date)
    assert pay_snapshot.cash_distribution == Decimal("50.0")
    assert pay_snapshot.cash == Decimal("50.0")
    assert pay_snapshot.holdings_value == Decimal("950.0")
    assert pay_snapshot.total_value == Decimal("1000.0")
    assert result.ledger.cost_basis["510300"] == Decimal("1000")
