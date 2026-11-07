import pytest

from etf_backtesting.adapters.free_stockdb import FreeStockDBAdapter


class FakeClient:
    _fq_dates = {"510300": ["20240102"]}
    _fq_cums = {"510300": [1.0]}

    def get_data(self, **kwargs):
        self.kwargs = kwargs
        return [{"date": 20240102, "close": 3.82}]


def test_adjusted_indicator_series_is_blocked_until_semantics_verified() -> None:
    client = FakeClient()
    adapter = FreeStockDBAdapter(client)
    with pytest.raises(ValueError, match="independently verified"):
        adapter.read_indicator_close_records("510300")
    assert not hasattr(client, "kwargs")


def test_adjusted_indicator_series_uses_vendor_qfq_after_explicit_verification() -> None:
    client = FakeClient()
    records = FreeStockDBAdapter(client).read_indicator_close_records(
        "510300", factor_semantics_verified=True
    )
    assert client.kwargs["fq"] == "qfq"
    assert records[0]["price_basis"] == "VENDOR_QFQ"
    assert records[0]["adjusted_close"] == 3.82
