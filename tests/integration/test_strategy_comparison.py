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
            assert tuple(item.trade_date for item in run.execution.snapshots[1::2]) == tuple(days)
    assert tuple(
        item.trade_date for item in result.shared_pool_run.execution.snapshots[1::2]
    ) == tuple(days)
