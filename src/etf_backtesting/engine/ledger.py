"""Cash, position, average-cost, and distribution ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


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
    cash_delta: Decimal
    cost_basis_after: Decimal
    realized_pnl: Decimal


@dataclass(slots=True)
class PortfolioLedger:
    cash: Decimal
    positions: dict[str, Decimal] = field(default_factory=dict)
    cost_basis: dict[str, Decimal] = field(default_factory=dict)
    events: list[LedgerEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash = _decimal(self.cash)
        self.positions = {key: _decimal(value) for key, value in self.positions.items()}
        self.cost_basis = {key: _decimal(value) for key, value in self.cost_basis.items()}
        if self.cash < 0:
            raise ValueError("initial cash must not be negative")
        for symbol, quantity in self.positions.items():
            if quantity < 0:
                raise ValueError("initial positions must not be negative")
            if quantity > 0 and symbol not in self.cost_basis:
                raise ValueError(f"initial cost basis is required for {symbol}")
        if any(value < 0 for value in self.cost_basis.values()):
            raise ValueError("initial cost basis must not be negative")

    def average_entry_price(self, symbol: str) -> Decimal | None:
        quantity = self.positions.get(symbol, Decimal("0"))
        if quantity <= 0:
            return None
        return self.cost_basis.get(symbol, Decimal("0")) / quantity

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
        self.cost_basis[symbol] = self.cost_basis.get(symbol, Decimal("0")) + total
        return self._record("BUY", symbol, qty, px, cost, -total, Decimal("0"))

    def sell(
        self,
        symbol: str,
        quantity: Decimal | str | int | float,
        price: Decimal | str | int | float,
        fee: Decimal | str | int | float = 0,
    ) -> LedgerEvent:
        qty, px, cost = _decimal(quantity), _decimal(price), _decimal(fee)
        held = self.positions.get(symbol, Decimal("0"))
        basis = self.cost_basis.get(symbol, Decimal("0"))
        if qty <= 0 or px <= 0 or cost < 0:
            raise ValueError("sell quantity/price must be positive and fee non-negative")
        if qty > held:
            raise ValueError("insufficient position")
        proceeds = qty * px - cost
        if proceeds < 0:
            raise ValueError("fee exceeds sale proceeds")
        removed_basis = basis if qty == held else basis * qty / held
        self.cash += proceeds
        self.positions[symbol] = held - qty
        self.cost_basis[symbol] = basis - removed_basis
        realized_pnl = proceeds - removed_basis
        return self._record("SELL", symbol, qty, px, cost, proceeds, realized_pnl)

    def credit_cash_distribution(
        self, symbol: str, amount: Decimal | str | int | float
    ) -> LedgerEvent:
        value = _decimal(amount)
        if value < 0:
            raise ValueError("cash distribution must not be negative")
        self.cash += value
        return self._record(
            "CASH_DISTRIBUTION", symbol, Decimal("0"), Decimal("0"),
            Decimal("0"), value, Decimal("0")
        )

    def contribute_cash(self, amount: Decimal | str | int | float) -> LedgerEvent:
        value = _decimal(amount)
        if value <= 0:
            raise ValueError("cash contribution must be positive")
        self.cash += value
        return self._record(
            "CONTRIBUTION", "", Decimal("0"), Decimal("0"),
            Decimal("0"), value, Decimal("0")
        )

    def _record(
        self,
        event_type: str,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
        fee: Decimal,
        cash_delta: Decimal,
        realized_pnl: Decimal,
    ) -> LedgerEvent:
        event = LedgerEvent(
            event_type=event_type,
            symbol=symbol,
            quantity=quantity,
            price=price,
            fee=fee,
            cash_after=self.cash,
            position_after=self.positions.get(symbol, Decimal("0")),
            cash_delta=cash_delta,
            cost_basis_after=self.cost_basis.get(symbol, Decimal("0")),
            realized_pnl=realized_pnl,
        )
        self.events.append(event)
        return event
