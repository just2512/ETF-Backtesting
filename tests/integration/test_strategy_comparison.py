from datetime import date
from decimal import Decimal

from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.execution import TradingCostModel
from etf_backtesting.strategies.comparison import StrategyComparisonRunner


def test_comparison_matrix_runs_A_B_C_per_etf_and_D_as_shared_pool() -> None:
    days = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
    ]

    def bars(symbol: str) -> list[PriceBar]:
        closes = [10, 10, 4, 4, 4]
        return [
            PriceBar(
                symbol, day, close, close + 0.2, close - 0.2, close,
                100000, close * 100000, source="fixture",
            )
            for day, close in zip(days, closes, strict=True)
        ]

    result = StrategyComparisonRunner().run(
        {
            "510300": bars("510300"),
            "159928": bars("159928"),
        },
        days,
        initial_cash=Decimal("10000"),
        costs=TradingCostModel(Decimal("0"), Decimal("0")),
        dca_budget_by_symbol={
            "510300": Decimal("1000"),
            "159928": Decimal("1000"),
        },
        per_etf_cycle_budget={
            "510300": Decimal("5000"),
            "159928": Decimal("5000"),
        },
        max_market_value_by_symbol={
            "510300": Decimal("50000"),
            "159928": Decimal("50000"),
        },
        dca_dates={days[0]},
        reserve_cash=Decimal("500"),
        sell_mode="S1",
        dividend_status="UNKNOWN",
        execution_rules_status="UNKNOWN",
        research_only=True,
        bollinger_period=3,
        bollinger_deviations=1.0,
    )

    assert set(result.single_etf_runs) == {"510300", "159928"}
    assert set(result.single_etf_runs["510300"]) == {"A", "B", "C"}
    assert set(result.single_etf_runs["159928"]) == {"A", "B", "C"}
    assert result.shared_pool_run.strategy == "D"
    for symbol_runs in result.single_etf_runs.values():
        for run in symbol_runs.values():
            assert run.research_only is True
            assert tuple(item.trade_date for item in run.execution.snapshots[1:]) == tuple(days)
    assert tuple(
        item.trade_date for item in result.shared_pool_run.execution.snapshots[1:]
    ) == tuple(days)

def test_single_etf_runs_use_each_etfs_own_listing_calendar_and_dca_dates() -> None:
    first = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    second = [date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)]

    def make_bars(symbol: str, dates: list[date]) -> list[PriceBar]:
        return [
            PriceBar(
                symbol, day, 1.0, 1.2, 0.8, 1.0, 10000, 10000,
                source="fixture",
            )
            for day in dates
        ]

    result = StrategyComparisonRunner().run(
        {"510300": make_bars("510300", first), "159928": make_bars("159928", second)},
        sorted(set(first + second)),
        initial_cash=Decimal("10000"),
        costs=TradingCostModel(Decimal("0"), Decimal("0")),
        dca_budget_by_symbol={"510300": Decimal("1000"), "159928": Decimal("1000")},
        per_etf_cycle_budget={"510300": Decimal("1000"), "159928": Decimal("1000")},
        max_market_value_by_symbol={"510300": Decimal("10000"), "159928": Decimal("10000")},
        dca_dates={"510300": {first[0]}, "159928": {second[0]}},
        reserve_cash=Decimal("1000"),
        sell_mode="S1",
        dividend_status="UNKNOWN",
        execution_rules_status="UNKNOWN",
        research_only=True,
        bollinger_period=2,
    )
    assert result.single_etf_runs["510300"]["A"].execution.snapshots[0].trade_date == first[0]
    assert result.single_etf_runs["159928"]["A"].execution.snapshots[0].trade_date == second[0]
    assert result.shared_pool_run.execution.snapshots[0].trade_date == first[0]

