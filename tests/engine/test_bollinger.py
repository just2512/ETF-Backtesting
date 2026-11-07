import pytest

from etf_backtesting.indicators.bollinger import bollinger_bands


def test_bollinger_waits_for_full_window() -> None:
    result = bollinger_bands([1.0, 2.0, 3.0], period=3)
    assert result[0] is None
    assert result[1] is None
    assert result[2] is not None
    assert result[2].middle == pytest.approx(2.0)


def test_constant_prices_have_no_percent_b_division() -> None:
    point = bollinger_bands([2.0] * 20)[-1]
    assert point is not None
    assert point.percent_b is None


def test_invalid_prices_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        bollinger_bands([1.0, 0.0], period=2)
