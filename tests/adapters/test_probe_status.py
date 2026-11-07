from datetime import date

from etf_backtesting.adapters.free_stockdb import FreeStockDBAdapter


class FakeClient:
    _fq_dates = {"510300": ["20240102", "20240103"]}
    _fq_cums = {"510300": [1.0, 1.1]}

    def get_data(self, **kwargs):
        return [{"date": 20240102, "open": 3.8, "high": 3.9, "low": 3.7, "close": 3.85}]


def test_probe_marks_factor_semantics_unknown_even_when_rows_exist() -> None:
    report = FreeStockDBAdapter(FakeClient()).probe_symbol("510300")
    assert report["adjustment_factor_count"] == 2
    assert report["adjustment_factor_status"] == "UNKNOWN"
