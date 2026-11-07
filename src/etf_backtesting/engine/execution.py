"""Next-session open execution with explicit market costs and lot constraints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.ledger import PortfolioLedger


def decimal_value(value: Decimal | str | float) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class TradingCostModel:
    commission_rate: Decimal
    other_fee_rate: Decimal
    minimum_commission: Decimal = Decimal("0")
    currency_quantum: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        if self.commission_rate < 0 or self.other_fee_rate < 0:
            raise ValueError("fee rates must not be negative")
        if self.minimum_commission < 0 or self.currency_quantum <= 0:
            raise ValueError("minimum commission and currency quantum are invalid")

    def calculate(self, notional: Decimal) -> Decimal:
        commission = notional * self.commission_rate
        if commission and self.minimum_commission:
            commission = max(commission, self.minimum_commission)
        other = notional * self.other_fee_rate
        return (commission + other).quantize(self.currency_quantum, rounding=ROUND_HALF_UP)



@dataclass(frozen=True, slots=True)
class ExecutionMarketContext:
    """Point-in-time quote, price-limit, and suspension state for one symbol/session."""

    bid: Decimal | None
    ask: Decimal | None
    limit_up: Decimal | None
    limit_down: Decimal | None
    suspended: bool | None
    upper_limit_locked: bool | None
    lower_limit_locked: bool | None

    def __post_init__(self) -> None:
        if self.bid is not None and self.bid <= 0:
            raise ValueError("bid must be positive")
        if self.ask is not None and self.ask <= 0:
            raise ValueError("ask must be positive")
        if self.bid is not None and self.ask is not None and self.ask < self.bid:
            raise ValueError("ask must not be below bid")
        if self.limit_up is not None and self.limit_up <= 0:
            raise ValueError("limit_up must be positive")
        if self.limit_down is not None and self.limit_down <= 0:
            raise ValueError("limit_down must be positive")
        if (
            self.limit_up is not None
            and self.limit_down is not None
            and self.limit_up < self.limit_down
        ):
            raise ValueError("limit_up must not be below limit_down")


@dataclass(frozen=True, slots=True)
class ExecutionModel:
    """Explicit adverse execution assumptions; no defaults are silently inferred."""

    slippage_bps: Decimal
    market_impact_bps: Decimal
    max_spread_bps: Decimal | None = None
    require_market_context: bool = True
    require_quotes: bool = True
    require_limit_status: bool = True

    def __post_init__(self) -> None:
        if self.slippage_bps < 0 or self.market_impact_bps < 0:
            raise ValueError("slippage and market impact must not be negative")
        if self.slippage_bps + self.market_impact_bps >= Decimal("10000"):
            raise ValueError("combined adverse execution adjustment must be below 10000 bps")
        if self.max_spread_bps is not None and self.max_spread_bps < 0:
            raise ValueError("max_spread_bps must not be negative")


@dataclass(frozen=True, slots=True)
class OrderIntent:
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    signal_date: date
    execution_date: date
    cash_limit: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.execution_date <= self.signal_date:
            raise ValueError("execution date must be later than signal date")
        if self.cash_limit is not None and self.cash_limit <= 0:
            raise ValueError("cash_limit must be positive when provided")
        if self.side == "SELL" and self.cash_limit is not None:
            raise ValueError("cash_limit applies only to buy orders")


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: Literal["FILLED", "PARTIAL", "NO_FILL", "REJECTED"]
    symbol: str
    side: str
    execution_date: date
    quantity: Decimal
    fill_price: Decimal | None
    notional: Decimal
    fee: Decimal
    reason: str | None = None
    signal_date: date | None = None
    requested_quantity: Decimal | None = None


class ExecutionEngine:
    def __init__(
        self,
        lot_size: int = 100,
        minimum_cash_reserve: Decimal = Decimal("0"),
        execution_model: ExecutionModel | None = None,
    ) -> None:
        if lot_size < 1:
            raise ValueError("lot_size must be positive")
        if minimum_cash_reserve < 0:
            raise ValueError("minimum_cash_reserve must not be negative")
        self.lot_size = Decimal(lot_size)
        self.minimum_cash_reserve = minimum_cash_reserve
        self.execution_model = execution_model

    def execute_next_open(
        self,
        order: OrderIntent,
        bar: PriceBar | None,
        ledger: PortfolioLedger,
        costs: TradingCostModel,
        market_context: ExecutionMarketContext | None = None,
    ) -> ExecutionResult:
        if bar is None:
            if self.execution_model is not None and self.execution_model.require_market_context:
                if market_context is None:
                    return self._result(
                        order, "NO_FILL",
                        reason="execution market context missing for absent bar",
                    )
                if market_context.suspended is True:
                    return self._result(
                        order, "NO_FILL", reason="market context reports suspension"
                    )
                if market_context.suspended is None:
                    return self._result(
                        order, "NO_FILL", reason="suspension status unknown"
                    )
                return self._result(
                    order, "NO_FILL", reason="bar missing despite tradable status"
                )
            return self._result(order, "NO_FILL", reason="no execution bar")
        if bar.symbol != order.symbol or bar.trade_date != order.execution_date:
            return self._result(order, "REJECTED", reason="execution bar does not match order")
        if bar.trade_status != "NORMAL":
            if self.execution_model is not None and self.execution_model.require_market_context:
                if market_context is None or market_context.suspended is None:
                    return self._result(
                        order, "NO_FILL", reason="suspension status unknown for non-normal bar"
                    )
                if market_context.suspended is False:
                    return self._result(
                        order, "REJECTED",
                        reason="bar trade status conflicts with tradable market context",
                    )
                return self._result(
                    order, "NO_FILL", reason=f"market context reports suspension ({bar.trade_status})"
                )
            return self._result(order, "NO_FILL", reason=f"trade status is {bar.trade_status}")
        if order.quantity % self.lot_size != 0:
            return self._result(order, "REJECTED", reason="quantity is not a whole trading lot")

        price = decimal_value(bar.open)
        model = self.execution_model
        if model is not None:
            if model.require_market_context and market_context is None:
                return self._result(order, "NO_FILL", reason="execution market context missing")
            if market_context is not None:
                if market_context.suspended is True:
                    return self._result(order, "NO_FILL", reason="market context reports suspension")
                if market_context.suspended is None and model.require_market_context:
                    return self._result(order, "NO_FILL", reason="suspension status unknown")
                if order.side == "BUY" and market_context.upper_limit_locked is True:
                    return self._result(order, "NO_FILL", reason="upper price limit locked")
                if order.side == "SELL" and market_context.lower_limit_locked is True:
                    return self._result(order, "NO_FILL", reason="lower price limit locked")
                if model.require_limit_status and (
                    market_context.limit_up is None
                    or market_context.limit_down is None
                    or market_context.upper_limit_locked is None
                    or market_context.lower_limit_locked is None
                ):
                    return self._result(order, "NO_FILL", reason="price-limit status incomplete")
                if model.require_quotes and (
                    market_context.bid is None or market_context.ask is None
                ):
                    return self._result(order, "NO_FILL", reason="bid/ask quote missing")
                if market_context.bid is not None and market_context.ask is not None:
                    midpoint = (market_context.bid + market_context.ask) / Decimal("2")
                    spread_bps = (
                        (market_context.ask - market_context.bid)
                        / midpoint
                        * Decimal("10000")
                    )
                    if (
                        model.max_spread_bps is not None
                        and spread_bps > model.max_spread_bps
                    ):
                        return self._result(order, "REJECTED", reason="spread exceeds configured maximum")
                    price = market_context.ask if order.side == "BUY" else market_context.bid
                adverse_bps = model.slippage_bps + model.market_impact_bps
                adjustment = adverse_bps / Decimal("10000")
                price = (
                    price * (Decimal("1") + adjustment)
                    if order.side == "BUY"
                    else price * (Decimal("1") - adjustment)
                )
                if model.require_limit_status:
                    if order.side == "BUY" and price > market_context.limit_up:
                        return self._result(order, "REJECTED", reason="buy price exceeds upper limit")
                    if order.side == "SELL" and price < market_context.limit_down:
                        return self._result(order, "REJECTED", reason="sell price is below lower limit")
        notional = order.quantity * price
        fee = costs.calculate(notional)
        filled_quantity = order.quantity
        status: Literal["FILLED", "PARTIAL"] = "FILLED"
        if order.side == "BUY":
            available_budget = ledger.cash - self.minimum_cash_reserve
            if order.cash_limit is not None:
                available_budget = min(available_budget, order.cash_limit)
            total_cost = notional + fee
            if total_cost > available_budget:
                filled_quantity = self._max_affordable_quantity(
                    order.quantity, price, available_budget, costs
                )
                if filled_quantity <= 0:
                    return self._result(
                        order,
                        "REJECTED",
                        reason="insufficient allocated cash or cash reserve",
                    )
                status = "PARTIAL"
                notional = filled_quantity * price
                fee = costs.calculate(notional)
            ledger.buy(order.symbol, filled_quantity, price, fee)
        else:
            if order.quantity > ledger.positions.get(order.symbol, Decimal("0")):
                return self._result(order, "REJECTED", reason="insufficient position")
            ledger.sell(order.symbol, order.quantity, price, fee)

        return ExecutionResult(
            status, order.symbol, order.side, order.execution_date,
            filled_quantity, price, notional, fee,
            signal_date=order.signal_date,
            requested_quantity=order.quantity,
        )

    def _max_affordable_quantity(
        self,
        requested_quantity: Decimal,
        price: Decimal,
        budget: Decimal,
        costs: TradingCostModel,
    ) -> Decimal:
        """Return the largest whole-lot buy quantity within budget, including fees."""
        if budget <= 0:
            return Decimal("0")
        maximum_lots = int(requested_quantity // self.lot_size)
        low, high = 0, maximum_lots
        while low < high:
            middle = (low + high + 1) // 2
            quantity = Decimal(middle) * self.lot_size
            notional = quantity * price
            if notional + costs.calculate(notional) <= budget:
                low = middle
            else:
                high = middle - 1
        return Decimal(low) * self.lot_size

    @staticmethod
    def _result(
        order: OrderIntent,
        status: Literal["NO_FILL", "REJECTED"],
        reason: str,
    ) -> ExecutionResult:
        return ExecutionResult(
            status, order.symbol, order.side, order.execution_date,
            Decimal("0"), None, Decimal("0"), Decimal("0"), reason,
            signal_date=order.signal_date,
            requested_quantity=order.quantity,
        )
