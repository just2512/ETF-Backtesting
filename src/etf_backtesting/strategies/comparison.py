"""Run comparable A/B/C single-ETF experiments and one D shared-pool experiment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.corporate_actions import ETFDividend
from etf_backtesting.engine.execution import (
    ExecutionMarketContext,
    ExecutionModel,
    TradingCostModel,
)
from etf_backtesting.strategies.orchestrator import (
    GateStatus,
    IndustryContextProvider,
    StrategyBacktestRunner,
    StrategyRunResult,
)


@dataclass(frozen=True, slots=True)
class StrategyComparisonResult:
    """A/B/C runs per ETF and one D run over the complete ETF universe."""

    single_etf_runs: Mapping[str, Mapping[str, StrategyRunResult]]
    shared_pool_run: StrategyRunResult
    trading_days: tuple[date, ...]


class StrategyComparisonRunner:
    """Run all four strategy families with identical dates, cash flows, and costs."""

    def __init__(self, lot_size: int = 100) -> None:
        self.runner = StrategyBacktestRunner(lot_size=lot_size)

    def run(
        self,
        bars_by_symbol: Mapping[str, Sequence[PriceBar]],
        trading_days: Sequence[date],
        *,
        initial_cash: Decimal,
        costs: TradingCostModel,
        dca_budget_by_symbol: Mapping[str, Decimal],
        per_etf_cycle_budget: Mapping[str, Decimal],
        max_market_value_by_symbol: Mapping[str, Decimal],
        dca_dates: set[date],
        reserve_cash: Decimal,
        sell_mode: str,
        dividend_status: GateStatus,
        execution_rules_status: GateStatus,
        dividend_snapshot_sha256: str | None = None,
        index_exposure_status: GateStatus | None = None,
        execution_model: ExecutionModel | None = None,
        execution_contexts: Mapping[
            tuple[date, str], ExecutionMarketContext
        ] | None = None,
        contributions: Mapping[date, Decimal] | None = None,
        dividends: Sequence[ETFDividend] = (),
        research_only: bool = False,
        bollinger_period: int = 20,
        bollinger_deviations: float = 2.0,
        industry_caps_enabled: bool = False,
        industry_context_provider: IndustryContextProvider | None = None,
    ) -> StrategyComparisonResult:
        symbols = sorted(bars_by_symbol)
        if not symbols:
            raise ValueError("bars_by_symbol must contain at least one ETF")
        for name, values in (
            ("dca_budget_by_symbol", dca_budget_by_symbol),
            ("per_etf_cycle_budget", per_etf_cycle_budget),
            ("max_market_value_by_symbol", max_market_value_by_symbol),
        ):
            missing = sorted(set(symbols) - set(values))
            if missing:
                raise ValueError(f"{name} missing symbols: {missing}")
        calendar = tuple(trading_days)
        if not calendar or list(calendar) != sorted(set(calendar)):
            raise ValueError("trading_days must be non-empty, unique, and ascending")

        shared_options = {
            "initial_cash": initial_cash,
            "costs": costs,
            "dividend_status": dividend_status,
            "dividend_snapshot_sha256": dividend_snapshot_sha256,
            "execution_rules_status": execution_rules_status,
            "execution_model": execution_model,
            "execution_contexts": execution_contexts,
            "research_only": research_only,
            "contributions": contributions,
            "dividends": dividends,
            "bollinger_period": bollinger_period,
            "bollinger_deviations": bollinger_deviations,
        }

        single_etf_runs: dict[str, dict[str, StrategyRunResult]] = {}
        for symbol in symbols:
            single_bars = {symbol: bars_by_symbol[symbol]}
            single_etf_runs[symbol] = {
                "A": self.runner.run(
                    "A",
                    single_bars,
                    calendar,
                    dca_budget_by_symbol={symbol: dca_budget_by_symbol[symbol]},
                    dca_dates=dca_dates,
                    **shared_options,
                ),
                "B": self.runner.run(
                    "B",
                    single_bars,
                    calendar,
                    per_etf_cycle_budget={symbol: per_etf_cycle_budget[symbol]},
                    **shared_options,
                ),
                "C": self.runner.run(
                    "C",
                    single_bars,
                    calendar,
                    per_etf_cycle_budget={symbol: per_etf_cycle_budget[symbol]},
                    sell_mode=sell_mode,
                    **shared_options,
                ),
            }

        shared_pool_run = self.runner.run(
            "D",
            bars_by_symbol,
            calendar,
            per_etf_cycle_budget=per_etf_cycle_budget,
            max_market_value_by_symbol=max_market_value_by_symbol,
            reserve_cash=reserve_cash,
            index_exposure_status=index_exposure_status,
            industry_caps_enabled=industry_caps_enabled,
            industry_context_provider=industry_context_provider,
            **shared_options,
        )
        return StrategyComparisonResult(
            single_etf_runs=single_etf_runs,
            shared_pool_run=shared_pool_run,
            trading_days=calendar,
        )
