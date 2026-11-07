from datetime import date

import pytest

from etf_backtesting.contracts import IndexConstituent, PriceBar


def test_price_bar_accepts_valid_ohlc() -> None:
    bar = PriceBar("510300", date(2024, 1, 2), 3.8, 3.9, 3.7, 3.85)
    assert bar.close == 3.85


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ((3.8, 3.7, 3.6, 3.65), "high"),
        ((3.8, 3.9, 3.85, 3.88), "low"),
        ((0, 3.9, 3.7, 3.8), "positive"),
    ],
)
def test_price_bar_rejects_invalid_ohlc(values: tuple[float, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        PriceBar("510300", date(2024, 1, 2), *values)


def test_index_constituent_uses_half_open_effective_interval() -> None:
    item = IndexConstituent("IDX", "600000", date(2024, 1, 1), date(2024, 2, 1))
    assert item.active_on(date(2024, 1, 31))
    assert not item.active_on(date(2024, 2, 1))
