from datetime import date
from decimal import Decimal

from etf_backtesting.strategies.bollinger_accumulate import (
    BollingerAccumulator,
    BollingerUpperBandSeller,
)
from etf_backtesting.strategies.fixed_dca import fixed_dca_signal


def test_fixed_dca_only_emits_on_scheduled_date() -> None:
    day = date(2024, 1, 2)
    assert fixed_dca_signal("510300", day, Decimal("1000"), False) is None
    assert fixed_dca_signal("510300", day, Decimal("1000"), True).budget == Decimal("1000")


def test_accumulator_triggers_each_tier_once_and_resets_at_middle_band() -> None:
    strategy = BollingerAccumulator()
    day = date(2024, 1, 2)
    assert [x.tier_index for x in strategy.on_close("510300", day, -0.15)] == [0, 1]
    assert strategy.on_close("510300", day, -0.20)[0].tier_index == 2
    assert strategy.on_close("510300", day, -0.35)[0].tier_index == 3
    assert strategy.on_close("510300", day, -0.35) == []
    assert strategy.on_close("510300", day, 0.5) == []
    assert [x.tier_index for x in strategy.on_close("510300", day, -0.35)] == [0, 1, 2, 3]


def test_upper_band_seller_triggers_once_until_reentry() -> None:
    strategy = BollingerUpperBandSeller()
    day = date(2024, 1, 2)
    assert strategy.on_close("510300", day, 1.1)
    assert not strategy.on_close("510300", day, 1.2)
    assert not strategy.on_close("510300", day, 0.9)
    assert strategy.on_close("510300", day, 1.1)
