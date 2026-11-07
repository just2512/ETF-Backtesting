from datetime import date
from decimal import Decimal
from pathlib import Path

from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.execution import TradingCostModel
from etf_backtesting.reports.strategy_report import (
    build_strategy_report,
    write_strategy_report,
)
from etf_backtesting.strategies.orchestrator import StrategyBacktestRunner


def test_strategy_report_is_bound_to_data_and_config_and_exports_artifacts(
    tmp_path: Path,
) -> None:
    days = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
    ]
    bars = [
        PriceBar("510300", day, 10, 10.2, 9.8, 10, 10000, 100000, source="fixture")
        for day in days
    ]
    result = StrategyBacktestRunner().run(
        "A",
        {"510300": bars},
        days,
        initial_cash=Decimal("10000"),
        costs=TradingCostModel(Decimal("0"), Decimal("0")),
        dividend_status="UNKNOWN",
        execution_rules_status="UNKNOWN",
        research_only=True,
        dca_budget_by_symbol={"510300": Decimal("10000")},
        dca_dates={days[0]},
    )
    config = {
        "initial_cash": "10000",
        "strategy": "A",
        "dca_dates": ["2024-01-02"],
        "costs": {"commission_rate": "0", "other_fee_rate": "0"},
    }

    report = build_strategy_report(
        result,
        data_snapshot_sha256="a" * 64,
        run_config=config,
    )
    repeated = build_strategy_report(
        result,
        data_snapshot_sha256="a" * 64,
        run_config=config,
    )
    paths = write_strategy_report(report, tmp_path)

    assert report["run_id"] == repeated["run_id"]
    assert len(report["run_id"]) == 64
    assert report["gates"]["formal_result_allowed"] is False
    assert report["reproducibility"]["data_snapshot_sha256"] == "a" * 64
    assert report["summary"]["filled_orders"] == 1
    assert report["summary"]["external_contributions"] == "0"
    assert set(paths) == {"summary", "equity", "executions", "ledger"}
    assert all(Path(path).exists() for path in paths.values())


def test_report_rejects_missing_snapshot_hash_or_empty_config() -> None:
    days = [date(2024, 1, 2)]
    bars = [PriceBar("510300", days[0], 10, 10.2, 9.8, 10)]
    result = StrategyBacktestRunner().run(
        "A",
        {"510300": bars},
        days,
        initial_cash=Decimal("10000"),
        costs=TradingCostModel(Decimal("0"), Decimal("0")),
        dividend_status="UNKNOWN",
        execution_rules_status="UNKNOWN",
        research_only=True,
        dca_budget_by_symbol={"510300": Decimal("10000")},
        dca_dates=set(),
    )

    try:
        build_strategy_report(result, data_snapshot_sha256="invalid", run_config={"a": 1})
    except ValueError as exc:
        assert "64-character hexadecimal" in str(exc)
    else:
        raise AssertionError("invalid snapshot digest must be rejected")

    try:
        build_strategy_report(result, data_snapshot_sha256="b" * 64, run_config={})
    except ValueError as exc:
        assert "run_config" in str(exc)
    else:
        raise AssertionError("empty run config must be rejected")
