from decimal import Decimal

import pytest

from etf_backtesting.engine.ledger import PortfolioLedger


def test_buy_sell_and_distribution_update_ledger() -> None:
    ledger = PortfolioLedger(Decimal(1000))
    ledger.buy("510300", "10", "10", "1")
    assert ledger.cash == Decimal(899)
    assert ledger.positions["510300"] == Decimal(10)

    ledger.credit_cash_distribution("510300", "2")
    assert ledger.cash == Decimal(901)

    ledger.sell("510300", "5", "11", "1")
    assert ledger.cash == Decimal(955)
    assert ledger.positions["510300"] == Decimal(5)
    assert ledger.events[0].cash_delta == Decimal("-101")
    assert ledger.events[1].cash_delta == Decimal("2")
    assert ledger.events[2].cash_delta == Decimal("54")
    assert ledger.events[2].realized_pnl == Decimal("3.5")
    assert ledger.events[2].cost_basis_after == Decimal("50.5")
    assert len(ledger.events) == 3


def test_ledger_rejects_overspending_and_overselling() -> None:
    ledger = PortfolioLedger(Decimal(100))
    with pytest.raises(ValueError, match="insufficient cash"):
        ledger.buy("510300", "20", "10")
    with pytest.raises(ValueError, match="insufficient position"):
        ledger.sell("510300", "1", "10")



def test_external_contribution_is_distinct_ledger_event() -> None:
    ledger = PortfolioLedger(Decimal("100"))
    event = ledger.contribute_cash("500")
    assert event.event_type == "CONTRIBUTION"
    assert event.cash_delta == Decimal("500")
    assert ledger.cash == Decimal("600")
