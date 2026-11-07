from datetime import date

import pytest

from etf_backtesting.adapters.free_stockdb import FreeStockDBAdapter


class FakeClient:
    _fq_dates = {"510300": ["20240102", "20240103"]}
    _fq_cums = {"510300": [1.0, 1.1]}

    def get_data(self, **kwargs):
        self.kwargs = kwargs
        return [{
            "date": 20240102, "open": 3.8, "high": 3.9, "low": 3.7, "close": 3.85,
            "volume": 100, "amount": 385,
        }]


def test_adapter_requests_unadjusted_prices_for_execution() -> None:
    client = FakeClient()
    bars = FreeStockDBAdapter(client).read_daily_bars("510300")
    assert client.kwargs["fq"] is None
    assert bars[0].trade_date == date(2024, 1, 2)
    assert bars[0].source == "free-stockdb"


def test_adapter_exposes_factor_rows_without_interpreting_semantics() -> None:
    factors = FreeStockDBAdapter(FakeClient()).read_adjustment_factors("510300")
    assert factors[0]["factor_type"] == "CUMULATIVE_SOURCE_FACTOR"
    assert factors[0]["factor"] == 1.0


def test_adapter_does_not_claim_dividend_api_exists() -> None:
    assert FreeStockDBAdapter(FakeClient()).read_cash_dividends("510300") is None


def test_adapter_rejects_malformed_daily_date() -> None:
    client = FakeClient()
    client.get_data = lambda **kwargs: [{"date": "2024-01-02", "open": 3.8,
        "high": 3.9, "low": 3.7, "close": 3.85}]
    with pytest.raises(ValueError, match="invalid daily date"):
        FreeStockDBAdapter(client).read_daily_bars("510300")
