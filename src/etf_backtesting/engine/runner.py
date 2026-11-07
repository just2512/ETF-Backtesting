"""Event-driven portfolio runner for pre-generated, causally dated orders."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.corporate_actions import ETFDividend
from etf_backtesting.engine.execution import ExecutionEngine, ExecutionResult, OrderIntent, TradingCostModel
from etf_backtesting.engine.ledger import PortfolioLedger
from etf_backtesting.reports.performance import mark_to_market


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    trade_date: date
    cash: Decimal
    holdings_value: Decimal
    total_value: Decimal
    external_contribution: Decimal
    cash_distribution: Decimal
    stale_symbols: tuple[str, ...]
    phase: str = "CLOSE"


@dataclass(frozen=True, slots=True)
class BacktestRunResult:
    ledger: PortfolioLedger
    executions: tuple[ExecutionResult, ...]
    snapshots: tuple[AccountSnapshot, ...]


class PortfolioBacktestRunner:
    """Execute pre-generated orders at their specified next-session open."""

    def __init__(self, execution_engine: ExecutionEngine | None = None) -> None:
        self.execution_engine = execution_engine or ExecutionEngine()

    def run(
        self,
        bars_by_symbol: Mapping[str, Sequence[PriceBar]],
        orders: Sequence[OrderIntent],
        initial_cash: Decimal,
        costs: TradingCostModel,
        contributions: Mapping[date, Decimal] | None = None,
        dividends: Sequence[ETFDividend] = (),
    ) -> BacktestRunResult:
        indexed_bars: dict[str, dict[date, PriceBar]] = {}
        all_dates: set[date] = set()
        for symbol, bars in bars_by_symbol.items():
            indexed: dict[date, PriceBar] = {}
            for bar in bars:
                if bar.symbol != symbol:
                    raise ValueError(f"bar symbol mismatch in {symbol} series")
                if bar.trade_date in indexed:
                    raise ValueError(f"duplicate bar date for {symbol}: {bar.trade_date}")
                indexed[bar.trade_date] = bar
                all_dates.add(bar.trade_date)
            indexed_bars[symbol] = indexed

        orders_by_date: defaultdict[date, list[OrderIntent]] = defaultdict(list)
        for order in orders:
            orders_by_date[order.execution_date].append(order)
            all_dates.add(order.execution_date)

        contribution_map = dict(contributions or {})
        all_dates.update(contribution_map)
        dividends_by_record: defaultdict[date, list[ETFDividend]] = defaultdict(list)
        dividends_by_pay: defaultdict[date, list[ETFDividend]] = defaultdict(list)
        for dividend in dividends:
            dividends_by_record[dividend.record_date].append(dividend)
            dividends_by_pay[dividend.pay_date].append(dividend)
            all_dates.update((dividend.ex_date, dividend.record_date, dividend.pay_date))
        entitlements: dict[ETFDividend, Decimal] = {}
        ledger = PortfolioLedger(initial_cash)
        executions: list[ExecutionResult] = []
        snapshots: list[AccountSnapshot] = []
        last_closes: dict[str, Decimal] = {}

        ordered_dates = sorted(all_dates)
        if ordered_dates:
            snapshots.append(AccountSnapshot(
                trade_date=ordered_dates[0],
                cash=ledger.cash,
                holdings_value=Decimal("0"),
                total_value=ledger.cash,
                external_contribution=Decimal("0"),
                cash_distribution=Decimal("0"),
                stale_symbols=(),
                phase="PRE_OPEN",
            ))

        for day in ordered_dates:
            cash_distribution = Decimal("0")
            for dividend in dividends_by_pay.get(day, []):
                eligible_shares = entitlements.get(dividend, Decimal("0"))
                amount = eligible_shares * dividend.cash_per_share
                if amount > 0:
                    ledger.credit_cash_distribution(dividend.symbol, amount)
                    cash_distribution += amount

            contribution = contribution_map.get(day, Decimal("0"))
            if contribution > 0:
                ledger.contribute_cash(contribution)
            elif contribution < 0:
                raise ValueError("negative contributions are not supported; model withdrawals explicitly")

            for order in sorted(
                orders_by_date.get(day, []),
                key=lambda item: (item.signal_date, item.symbol, item.side),
            ):
                bar = indexed_bars.get(order.symbol, {}).get(day)
                executions.append(
                    self.execution_engine.execute_next_open(order, bar, ledger, costs)
                )

            todays_bars = {
                symbol: bars[day]
                for symbol, bars in indexed_bars.items()
                if day in bars
            }
            for symbol, bar in todays_bars.items():
                last_closes[symbol] = Decimal(str(bar.close))

            for dividend in dividends_by_record.get(day, []):
                entitlements[dividend] = ledger.positions.get(
                    dividend.symbol, Decimal("0")
                )

            held = {
                symbol: quantity
                for symbol, quantity in ledger.positions.items()
                if quantity > 0
            }
            stale = tuple(sorted(symbol for symbol in held if symbol not in todays_bars))
            prices = {symbol: last_closes[symbol] for symbol in held if symbol in last_closes}
            holdings_value = mark_to_market(Decimal("0"), held, prices) if held else Decimal("0")
            snapshots.append(AccountSnapshot(
                trade_date=day,
                cash=ledger.cash,
                holdings_value=holdings_value,
                total_value=ledger.cash + holdings_value,
                external_contribution=contribution,
                cash_distribution=cash_distribution,
                stale_symbols=stale,
                phase="CLOSE",
            ))

        return BacktestRunResult(ledger, tuple(executions), tuple(snapshots))
