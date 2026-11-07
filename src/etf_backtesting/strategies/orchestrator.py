"""A/B/C/D strategy signal orchestration on one shared execution/accounting engine."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.corporate_actions import ETFDividend
from etf_backtesting.engine.execution import (
    ExecutionEngine,
    ExecutionMarketContext,
    ExecutionModel,
    OrderIntent,
    TradingCostModel,
)
from etf_backtesting.engine.ledger import PortfolioLedger
from etf_backtesting.engine.runner import BacktestRunResult, PortfolioBacktestRunner
from etf_backtesting.indicators.bollinger import bollinger_bands
from etf_backtesting.portfolio.cash_pool import (
    BuySignal,
    CashPoolAllocator,
    IndustryExposureContext,
)
from etf_backtesting.strategies.bollinger_accumulate import (
    BollingerAccumulator,
    BollingerUpperBandSeller,
)
from etf_backtesting.strategies.fixed_dca import fixed_dca_signal
from etf_backtesting.strategies.orders import budget_to_buy_order, sell_signal_to_order


StrategyName = Literal["A", "B", "C", "D"]
GateStatus = Literal["PASS", "MISSING", "UNKNOWN", "NOT_APPLICABLE"]


@dataclass(frozen=True, slots=True)
class StrategyRunResult:
    strategy: StrategyName
    execution: BacktestRunResult
    dividend_gate: GateStatus
    dividend_snapshot_sha256: str | None
    execution_rules_gate: GateStatus
    index_exposure_gate: GateStatus
    research_only: bool


IndustryContextProvider = Callable[
    [date, PortfolioLedger, Mapping[str, Decimal]],
    IndustryExposureContext,
]


class StrategySignalOrchestrator:
    """Generate close-derived orders for the common next-session runner.

    For B/C/D, per_etf_cycle_budget is the explicit base amount for one
    Bollinger accumulation cycle. The tier fractions are applied to that
    amount. D additionally constrains allocations through the common cash pool.
    """

    def __init__(
        self,
        strategy: StrategyName,
        *,
        dca_budget_by_symbol: Mapping[str, Decimal] | None = None,
        per_etf_cycle_budget: Mapping[str, Decimal] | None = None,
        dca_dates: set[date] | None = None,
        max_market_value_by_symbol: Mapping[str, Decimal] | None = None,
        reserve_cash: Decimal | None = None,
        sell_mode: str = "S0",
        lot_size: int = 100,
        bollinger_period: int = 20,
        bollinger_deviations: float = 2.0,
        industry_caps_enabled: bool = False,
        industry_context_provider: IndustryContextProvider | None = None,
    ) -> None:
        if strategy not in ("A", "B", "C", "D"):
            raise ValueError("strategy must be A, B, C, or D")
        if lot_size < 1:
            raise ValueError("lot_size must be positive")
        if bollinger_period < 2 or bollinger_deviations <= 0:
            raise ValueError("invalid Bollinger configuration")
        if strategy == "A" and not dca_budget_by_symbol:
            raise ValueError("strategy A requires dca_budget_by_symbol")
        if strategy in ("B", "C", "D") and not per_etf_cycle_budget:
            raise ValueError(f"strategy {strategy} requires per_etf_cycle_budget")
        if strategy == "D":
            if not max_market_value_by_symbol:
                raise ValueError("strategy D requires max_market_value_by_symbol")
            if reserve_cash is None:
                raise ValueError("strategy D requires an explicit reserve_cash")
        if industry_caps_enabled and industry_context_provider is None:
            raise ValueError(
                "industry caps are enabled but no point-in-time context provider was supplied"
            )
        if strategy == "C" and sell_mode not in ("S0", "S1", "S2"):
            raise ValueError("strategy C sell_mode must be S0, S1, or S2")

        self.strategy = strategy
        self.dca_budget_by_symbol = dict(dca_budget_by_symbol or {})
        self.per_etf_cycle_budget = dict(per_etf_cycle_budget or {})
        if any(value <= 0 for value in self.dca_budget_by_symbol.values()):
            raise ValueError("all fixed DCA budgets must be positive")
        if any(value <= 0 for value in self.per_etf_cycle_budget.values()):
            raise ValueError("all ETF cycle budgets must be positive")
        self.dca_dates = set(dca_dates or ())
        self.max_market_value_by_symbol = dict(max_market_value_by_symbol or {})
        if any(value <= 0 for value in self.max_market_value_by_symbol.values()):
            raise ValueError("all ETF market-value caps must be positive")
        self.reserve_cash = reserve_cash
        self.sell_mode = sell_mode
        self.lot_size = lot_size
        self.bollinger_period = bollinger_period
        self.bollinger_deviations = bollinger_deviations
        self.industry_caps_enabled = industry_caps_enabled
        self.industry_context_provider = industry_context_provider
        self.histories: dict[str, list[float]] = {}
        self.accumulators: dict[str, BollingerAccumulator] = {}
        self.sellers: dict[str, BollingerUpperBandSeller] = {}
        self.cash_allocator = CashPoolAllocator()

    def __call__(
        self,
        signal_date: date,
        todays_bars: Mapping[str, PriceBar],
        ledger: PortfolioLedger,
        last_closes: Mapping[str, Decimal],
        next_session: date,
    ) -> Sequence[OrderIntent]:
        if self.strategy == "A":
            return self._fixed_dca_orders(signal_date, todays_bars, next_session)
        if self.strategy in ("B", "C"):
            return self._single_etf_orders(
                signal_date, todays_bars, ledger, next_session
            )
        return self._shared_pool_orders(
            signal_date, todays_bars, ledger, last_closes, next_session
        )

    def _update_indicators(
        self,
        symbol: str,
        bar: PriceBar,
    ) -> float | None:
        history = self.histories.setdefault(symbol, [])
        history.append(float(bar.close))
        if len(history) < self.bollinger_period:
            return None
        point = bollinger_bands(
            history,
            period=self.bollinger_period,
            deviations=self.bollinger_deviations,
        )[-1]
        return None if point is None else point.percent_b

    def _accumulation_signals(
        self,
        symbol: str,
        signal_date: date,
        percent_b: float,
    ):
        accumulator = self.accumulators.setdefault(symbol, BollingerAccumulator())
        return accumulator.on_close(symbol, signal_date, percent_b)

    def _fixed_dca_orders(
        self,
        signal_date: date,
        todays_bars: Mapping[str, PriceBar],
        next_session: date,
    ) -> list[OrderIntent]:
        if signal_date not in self.dca_dates:
            return []
        orders: list[OrderIntent] = []
        for symbol, bar in sorted(todays_bars.items()):
            budget = self.dca_budget_by_symbol.get(symbol)
            if budget is None:
                continue
            signal = fixed_dca_signal(symbol, signal_date, budget, scheduled=True)
            if signal is None:
                continue
            order = budget_to_buy_order(
                symbol,
                signal_date,
                next_session,
                signal.budget,
                Decimal(str(bar.close)),
                self.lot_size,
            )
            if order is not None:
                orders.append(order)
        return orders

    def _single_etf_orders(
        self,
        signal_date: date,
        todays_bars: Mapping[str, PriceBar],
        ledger: PortfolioLedger,
        next_session: date,
    ) -> list[OrderIntent]:
        orders: list[OrderIntent] = []
        for symbol, bar in sorted(todays_bars.items()):
            percent_b = self._update_indicators(symbol, bar)
            if percent_b is None:
                continue
            signals = self._accumulation_signals(symbol, signal_date, percent_b)
            if signals and symbol not in self.per_etf_cycle_budget:
                raise ValueError(f"strategy {self.strategy} missing cycle budget for {symbol}")
            base_budget = self.per_etf_cycle_budget.get(symbol, Decimal("0"))
            desired_cash = base_budget * sum(
                (Decimal(str(item.budget_fraction)) for item in signals),
                Decimal("0"),
            )
            if desired_cash > 0:
                order = budget_to_buy_order(
                    symbol,
                    signal_date,
                    next_session,
                    desired_cash,
                    Decimal(str(bar.close)),
                    self.lot_size,
                )
                if order is not None:
                    orders.append(order)

            if self.strategy == "C":
                seller = self.sellers.setdefault(
                    symbol, BollingerUpperBandSeller(mode=self.sell_mode)
                )
                sell_signal = seller.on_close(symbol, signal_date, percent_b)
                if sell_signal is not None:
                    sell_order = sell_signal_to_order(
                        sell_signal,
                        next_session,
                        ledger.positions.get(symbol, Decimal("0")),
                        self.lot_size,
                    )
                    if sell_order is not None:
                        orders.append(sell_order)
        return orders

    def _shared_pool_orders(
        self,
        signal_date: date,
        todays_bars: Mapping[str, PriceBar],
        ledger: PortfolioLedger,
        last_closes: Mapping[str, Decimal],
        next_session: date,
    ) -> list[OrderIntent]:
        candidates: list[BuySignal] = []
        closes = dict(last_closes)
        for symbol, bar in sorted(todays_bars.items()):
            percent_b = self._update_indicators(symbol, bar)
            if percent_b is None:
                continue
            signals = self._accumulation_signals(symbol, signal_date, percent_b)
            if not signals:
                continue
            if symbol not in self.max_market_value_by_symbol:
                raise ValueError(f"strategy D missing market-value cap for {symbol}")
            if symbol not in self.per_etf_cycle_budget:
                raise ValueError(f"strategy D missing cycle budget for {symbol}")
            desired = self.per_etf_cycle_budget[symbol] * sum(
                (Decimal(str(item.budget_fraction)) for item in signals),
                Decimal("0"),
            )
            current_value = ledger.positions.get(symbol, Decimal("0")) * Decimal(
                str(closes.get(symbol, Decimal(str(bar.close))))
            )
            candidates.append(BuySignal(
                symbol=symbol,
                percent_b=percent_b,
                desired_cash=desired,
                current_market_value=current_value,
                max_market_value=self.max_market_value_by_symbol[symbol],
            ))

        if not candidates:
            return []
        industry_context = None
        if self.industry_caps_enabled:
            assert self.industry_context_provider is not None
            industry_context = self.industry_context_provider(
                signal_date, ledger, closes
            )
        allocations = self.cash_allocator.allocate(
            ledger.cash,
            self.reserve_cash or Decimal("0"),
            candidates,
            industry_context,
        )
        orders: list[OrderIntent] = []
        for allocation in allocations:
            if allocation.allocated_cash <= 0:
                continue
            bar = todays_bars[allocation.symbol]
            order = budget_to_buy_order(
                allocation.symbol,
                signal_date,
                next_session,
                allocation.allocated_cash,
                Decimal(str(bar.close)),
                self.lot_size,
            )
            if order is not None:
                orders.append(order)
        return orders


class StrategyBacktestRunner:
    """Run one strategy through the same portfolio, execution, and ledger engine."""

    def __init__(self, lot_size: int = 100) -> None:
        self.lot_size = lot_size

    def run(
        self,
        strategy: StrategyName,
        bars_by_symbol: Mapping[str, Sequence[PriceBar]],
        trading_days: Sequence[date],
        *,
        initial_cash: Decimal,
        costs: TradingCostModel,
        dividend_status: GateStatus,
        execution_rules_status: GateStatus,
        dividend_snapshot_sha256: str | None = None,
        index_exposure_status: GateStatus | None = None,
        execution_model: ExecutionModel | None = None,
        execution_contexts: Mapping[tuple[date, str], ExecutionMarketContext] | None = None,
        research_only: bool = False,
        contributions: Mapping[date, Decimal] | None = None,
        dividends: Sequence[ETFDividend] = (),
        **strategy_options: object,
    ) -> StrategyRunResult:
        if strategy != "D" and len(bars_by_symbol) != 1:
            raise ValueError(
                "strategies A/B/C run one ETF per comparison; strategy D is the multi-ETF shared-pool run"
            )
        if dividend_status == "PASS":
            if dividend_snapshot_sha256 is None or len(dividend_snapshot_sha256) != 64 or any(
                character not in "0123456789abcdefABCDEF"
                for character in dividend_snapshot_sha256
            ):
                raise ValueError(
                    "dividend PASS requires a 64-character official dividend snapshot SHA-256"
                )
            if any(
                event.announcement_date is None
                or event.source_name is None
                or event.source_url is None
                for event in dividends
            ):
                raise ValueError(
                    "dividend PASS requires provenance on every dividend event"
                )
        industry_caps_enabled = bool(strategy_options.get("industry_caps_enabled", False))
        if strategy == "D" and industry_caps_enabled:
            if index_exposure_status is None:
                raise ValueError(
                    "strategy D with industry caps requires an explicit index_exposure_status"
                )
        else:
            index_exposure_status = "NOT_APPLICABLE"
        if not research_only and (
            dividend_status != "PASS"
            or execution_rules_status != "PASS"
            or (strategy == "D" and industry_caps_enabled and index_exposure_status != "PASS")
        ):
            raise ValueError(
                "formal A/B/C/D comparison is blocked until dividend and execution-rule gates pass"
            )
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if not research_only:
            if execution_model is None or not (
                execution_model.require_market_context
                and execution_model.require_quotes
                and execution_model.require_limit_status
            ):
                raise ValueError(
                    "formal runs require explicit quotes, price-limit, suspension, slippage, and impact model"
                )
            if execution_contexts is None:
                raise ValueError("formal runs require dated execution market contexts")
        orchestrator = StrategySignalOrchestrator(
            strategy,
            lot_size=self.lot_size,
            **strategy_options,
        )
        minimum_reserve = (
            strategy_options.get("reserve_cash", Decimal("0"))
            if strategy == "D"
            else Decimal("0")
        )
        execution = PortfolioBacktestRunner(
            ExecutionEngine(
                lot_size=self.lot_size,
                minimum_cash_reserve=minimum_reserve,
                execution_model=execution_model,
            )
        ).run(
            bars_by_symbol,
            (),
            initial_cash,
            costs,
            contributions=contributions,
            dividends=dividends,
            trading_days=trading_days,
            signal_generator=orchestrator,
            execution_contexts=execution_contexts,
        )
        if not research_only:
            incomplete_context = [
                item for item in execution.executions
                if item.status in ("NO_FILL", "REJECTED")
                and item.reason is not None
                and (
                    "missing" in item.reason
                    or "unknown" in item.reason
                    or "incomplete" in item.reason
                    or "despite tradable" in item.reason
                    or "conflicts" in item.reason
                )
            ]
            if incomplete_context:
                raise ValueError(
                    "formal run encountered missing or unknown execution market context"
                )
        return StrategyRunResult(
            strategy=strategy,
            execution=execution,
            dividend_gate=dividend_status,
            dividend_snapshot_sha256=dividend_snapshot_sha256,
            execution_rules_gate=execution_rules_status,
            index_exposure_gate=index_exposure_status,
            research_only=research_only,
        )
