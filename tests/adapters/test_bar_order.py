from datetime import date

from etf_backtesting.adapters.free_stockdb import FreeStockDBAdapter


class ReverseOrderClient:
    _fq_dates = {}
    _fq_cums = {}

    def get_data(self, **kwargs):
        return [
            {"date": 20240103, "open": 3.8, "high": 3.9, "low": 3.7, "close": 3.85},
            {"date": 20240102, "open": 3.7, "high": 3.8, "low": 3.6, "close": 3.75},
        ]


def test_daily_bars_are_normalized_to_ascending_dates() -> None:
    bars = FreeStockDBAdapter(ReverseOrderClient()).read_daily_bars("510300")
    assert [bar.trade_date for bar in bars] == [date(2024, 1, 2), date(2024, 1, 3)]
