from decimal import Decimal

import pytest

from etf_backtesting.reports.performance import mark_to_market, maximum_drawdown, unitized_nav


def test_mark_to_market_includes_cash_and_all_positions() -> None:
    value = mark_to_market(
        Decimal("100"),
        {"510300": Decimal("100"), "510880": Decimal("50")},
        {"510300": Decimal("4"), "510880": Decimal("3")},
    )
    assert value == Decimal("650")


def test_mark_to_market_rejects_missing_held_asset_price() -> None:
    with pytest.raises(ValueError, match="missing closing prices"):
        mark_to_market(Decimal("100"), {"510300": Decimal("100")}, {})


def test_maximum_drawdown_uses_running_peak() -> None:
    values = [Decimal("100"), Decimal("120"), Decimal("90"), Decimal("110")]
    assert maximum_drawdown(values) == Decimal("-0.25")



def test_unitized_nav_excludes_end_of_period_contributions() -> None:
    nav = unitized_nav(
        [Decimal("100"), Decimal("200"), Decimal("180")],
        [Decimal("0"), Decimal("100"), Decimal("0")],
    )
    assert nav == [Decimal("1"), Decimal("1"), Decimal("0.9")]
    assert maximum_drawdown(nav) == Decimal("-0.1")
