"""Minimal cash/position ledger with explicit fees and cash distributions."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable


def _decimal(value: Decimal | str | int | float) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    event_type: str
    symbol: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    cash_after: Decimal
    position_after: Decimal


@dataclass(slots=True)
class PortfolioLedger:
    cash: Decimal
    positions: dict[str, Decimal] = field(default_factory=dict)
    events: list[LedgerEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash = _decimal(self.cash)
        if self.cash < 0:
            raise ValueError("initial cash must not be negative")

    def buy(
        self,
        symbol: str,
        quantity: Decimal | str | int | float,
        price: Decimal | str | int | float,
        fee: Decimal | str | int | float = 0,
    ) -> LedgerEvent:
        qty, px, cost = _decimal(quantity), _decimal(price), _decimal(fee)
        if qty <= 0 or px <= 0 or cost < 0:
            raise ValueError("buy quantity/price must be positive and fee non-negative")
        total = qty * px + cost
        if total > self.cash:
            raise ValueError("insufficient cash")
        self.cash -= total
        self.positions[symbol] = self.positions.get(symbol, Decimal("0")) + qty
        return self._record("BUY", symbol, qty, px, cost)

    def sell(
        self,
        symbol: str,
        quantity: Decimal | str | int | float,
        price: Decimal | str | int | float,
        fee: Decimal | str | int | float = 0,
    ) -> LedgerEvent:
        qty, px, cost = _decimal(quantity), _decimal(price), _decimal(fee)
        held = self.positions.get(symbol, Decimal("0"))
        if qty <= 0 or px <= 0 or cost < 0:
            raise ValueError("sell quantity/price must be positive and fee non-negative")
        if qty > held:
            raise ValueError("insufficient position")
        proceeds = qty * px - cost
        if proceeds < 0:
            raise ValueError("fee exceeds sale proceeds")
        self.cash += proceeds
        self.positions[symbol] = held - qty
        return self._record("SELL", symbol, qty, px, cost)

    def credit_cash_distribution(
        self, symbol: str, amount: Decimal | str | int | float
    ) -> LedgerEvent:
        value = _decimal(amount)
        if value < 0:
            raise ValueError("cash distribution must not be negative")
        self.cash += value
        return self._record("CASH_DISTRIBUTION", symbol, Decimal("0"), Decimal("0"), Decimal("0"))

    def _record(
        self,
        event_type: str,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
        fee: Decimal,
    ) -> LedgerEvent:
        event = LedgerEvent(
            event_type=event_type,
            symbol=symbol,
            quantity=quantity,
            price=price,
            fee=fee,
            cash_after=self.cash,
            position_after=self.positions.get(symbol, Decimal("0")),
        )
        self.events.append(event)
        return event
