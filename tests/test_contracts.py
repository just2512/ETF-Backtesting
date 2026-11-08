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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("open", float("nan")),
        ("high", float("inf")),
        ("low", float("-inf")),
        ("close", float("nan")),
        ("volume", float("nan")),
        ("amount", float("inf")),
    ],
)
def test_price_bar_rejects_non_finite_market_values(field: str, value: float) -> None:
    values = {
        "open": 3.8,
        "high": 3.9,
        "low": 3.7,
        "close": 3.85,
        "volume": 1000.0,
        "amount": 3850.0,
    }
    values[field] = value

    with pytest.raises(ValueError, match="finite"):
        PriceBar("510300", date(2024, 1, 2), **values)
