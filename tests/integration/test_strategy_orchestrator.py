from datetime import date
from decimal import Decimal

import pytest

from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.execution import TradingCostModel
from etf_backtesting.strategies.orchestrator import StrategyBacktestRunner


DAYS = [
    date(2024, 1, 2),
    date(2024, 1, 3),
    date(2024, 1, 4),
    date(2024, 1, 5),
    date(2024, 1, 8),
]


def bars(
    symbol: str,
    closes: list[float],
    opens: list[float] | None = None,
) -> list[PriceBar]:
    return [
        PriceBar(
            symbol=symbol,
            trade_date=day,
            open=close if opens is None else opens[index],
            high=max(close, close if opens is None else opens[index]) + 0.2,
            low=min(close, close if opens is None else opens[index]) - 0.2,
            close=close,
            volume=100000,
            amount=close * 100000,
            source="fixture",
        )
        for index, (day, close) in enumerate(zip(DAYS, closes, strict=True))
    ]


def free_costs() -> TradingCostModel:
    return TradingCostModel(Decimal("0"), Decimal("0"))


def test_strategy_a_fixed_dca_executes_only_on_next_session() -> None:
    result = StrategyBacktestRunner().run(
        "A",
        {"510300": bars("510300", [10, 10, 10, 10, 10])},
        DAYS,
        initial_cash=Decimal("10000"),
        costs=free_costs(),
        dividend_status="UNKNOWN",
        execution_rules_status="UNKNOWN",
        research_only=True,
        dca_budget_by_symbol={"510300": Decimal("10000")},
        dca_dates={DAYS[0]},
    )

    assert result.research_only is True
    assert result.execution.ledger.positions["510300"] == Decimal("1000")
    assert result.execution.executions[0].execution_date == DAYS[1]
    assert result.execution.executions[0].status == "FILLED"


def test_strategy_b_bollinger_accumulation_uses_next_session_open() -> None:
    result = StrategyBacktestRunner(lot_size=100).run(
        "B",
        {"510300": bars("510300", [10, 10, 4, 4, 4])},
        DAYS,
        initial_cash=Decimal("10000"),
        costs=free_costs(),
        dividend_status="UNKNOWN",
        execution_rules_status="UNKNOWN",
        research_only=True,
        per_etf_cycle_budget={"510300": Decimal("5000")},
        bollinger_period=3,
        bollinger_deviations=1.0,
    )

    filled = [item for item in result.execution.executions if item.status == "FILLED"]
    assert len(filled) == 1
    assert filled[0].signal_date == DAYS[2]
    assert filled[0].execution_date == DAYS[3]
    assert filled[0].quantity == Decimal("500")


def test_strategy_c_s1_sell_is_based_on_position_at_signal_close() -> None:
    result = StrategyBacktestRunner(lot_size=100).run(
        "C",
        {"510300": bars("510300", [10, 10, 4, 13, 13])},
        DAYS,
        initial_cash=Decimal("10000"),
        costs=free_costs(),
        dividend_status="UNKNOWN",
        execution_rules_status="UNKNOWN",
        research_only=True,
        per_etf_cycle_budget={"510300": Decimal("5000")},
        sell_mode="S1",
        bollinger_period=3,
        bollinger_deviations=1.0,
    )

    filled = [item for item in result.execution.executions if item.status == "FILLED"]
    assert [item.side for item in filled] == ["BUY", "SELL"]
    assert filled[0].quantity == Decimal("500")
    assert filled[1].signal_date == DAYS[3]
    assert filled[1].execution_date == DAYS[4]
    assert filled[1].quantity == Decimal("100")
    assert result.execution.ledger.positions["510300"] == Decimal("400")


def test_strategy_d_uses_shared_cash_pool_and_preserves_reserve() -> None:
    result = StrategyBacktestRunner(lot_size=100).run(
        "D",
        {
            "510300": bars("510300", [10, 10, 4, 4, 4], [10, 10, 10, 4, 4]),
            "159928": bars("159928", [10, 8, 4, 4, 4]),
        },
        DAYS,
        initial_cash=Decimal("5000"),
        costs=free_costs(),
        dividend_status="UNKNOWN",
        execution_rules_status="UNKNOWN",
        research_only=True,
        per_etf_cycle_budget={
            "510300": Decimal("10000"),
            "159928": Decimal("10000"),
        },
        max_market_value_by_symbol={
            "510300": Decimal("100000"),
            "159928": Decimal("100000"),
        },
        reserve_cash=Decimal("1000"),
        bollinger_period=3,
        bollinger_deviations=1.0,
    )

    executions = result.execution.executions
    assert [item.symbol for item in executions] == ["510300", "159928"]
    assert [item.status for item in executions] == ["REJECTED", "FILLED"]
    assert "allocated cash budget" in (executions[0].reason or "")
    assert result.execution.ledger.cash == Decimal("3000")
    assert result.execution.ledger.positions["159928"] == Decimal("500")
    assert result.execution.ledger.positions.get("510300", Decimal("0")) == 0


def test_formal_strategy_run_fails_closed_on_missing_dividends_or_execution_rules() -> None:
    with pytest.raises(ValueError, match="formal A/B/C/D comparison is blocked"):
        StrategyBacktestRunner().run(
            "A",
            {"510300": bars("510300", [10, 10, 10, 10, 10])},
            DAYS,
            initial_cash=Decimal("10000"),
            costs=free_costs(),
            dividend_status="MISSING",
            execution_rules_status="UNKNOWN",
            dca_budget_by_symbol={"510300": Decimal("10000")},
            dca_dates={DAYS[0]},
        )


def test_A_B_C_reject_multi_etf_runs_to_avoid_implicit_priority() -> None:
    with pytest.raises(ValueError, match="run one ETF per comparison"):
        StrategyBacktestRunner().run(
            "B",
            {
                "510300": bars("510300", [10, 10, 4, 4, 4]),
                "159928": bars("159928", [10, 10, 4, 4, 4]),
            },
            DAYS,
            initial_cash=Decimal("10000"),
            costs=free_costs(),
            dividend_status="UNKNOWN",
            execution_rules_status="UNKNOWN",
            research_only=True,
            per_etf_cycle_budget={
                "510300": Decimal("10000"),
                "159928": Decimal("10000"),
            },
            bollinger_period=2,
        )
