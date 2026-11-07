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
class OrderIntent:
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    signal_date: date
    execution_date: date

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.execution_date <= self.signal_date:
            raise ValueError("execution date must be later than signal date")


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: Literal["FILLED", "NO_FILL", "REJECTED"]
    symbol: str
    side: str
    execution_date: date
    quantity: Decimal
    fill_price: Decimal | None
    notional: Decimal
    fee: Decimal
    reason: str | None = None


class ExecutionEngine:
    def __init__(self, lot_size: int = 100) -> None:
        if lot_size < 1:
            raise ValueError("lot_size must be positive")
        self.lot_size = Decimal(lot_size)

    def execute_next_open(
        self,
        order: OrderIntent,
        bar: PriceBar | None,
        ledger: PortfolioLedger,
        costs: TradingCostModel,
    ) -> ExecutionResult:
        if bar is None:
            return self._result(order, "NO_FILL", reason="no execution bar")
        if bar.symbol != order.symbol or bar.trade_date != order.execution_date:
            return self._result(order, "REJECTED", reason="execution bar does not match order")
        if bar.trade_status != "NORMAL":
            return self._result(order, "NO_FILL", reason=f"trade status is {bar.trade_status}")
        if order.quantity % self.lot_size != 0:
            return self._result(order, "REJECTED", reason="quantity is not a whole trading lot")

        price = decimal_value(bar.open)
        notional = order.quantity * price
        fee = costs.calculate(notional)
        if order.side == "BUY":
            if notional + fee > ledger.cash:
                return self._result(order, "REJECTED", reason="insufficient cash")
            ledger.buy(order.symbol, order.quantity, price, fee)
        else:
            if order.quantity > ledger.positions.get(order.symbol, Decimal("0")):
                return self._result(order, "REJECTED", reason="insufficient position")
            ledger.sell(order.symbol, order.quantity, price, fee)

        return ExecutionResult(
            "FILLED", order.symbol, order.side, order.execution_date,
            order.quantity, price, notional, fee,
        )

    @staticmethod
    def _result(
        order: OrderIntent,
        status: Literal["NO_FILL", "REJECTED"],
        reason: str,
    ) -> ExecutionResult:
        return ExecutionResult(
            status, order.symbol, order.side, order.execution_date,
            Decimal("0"), None, Decimal("0"), Decimal("0"), reason,
        )
