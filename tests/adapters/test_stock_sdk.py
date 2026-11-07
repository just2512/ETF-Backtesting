from datetime import date

import pytest

from etf_backtesting.adapters.stock_sdk import StockSDKAdapter


class FakeRD:
    def get(self, *args):
        return args


class FakeSDK:
    def __init__(self):
        self.rd = FakeRD()
        self.init_args = None
        self.endpoint = None
        self.price_calls = []
        self.price_rows = [
            {"date": 20240103, "open": 3.9, "high": 4.0, "low": 3.8, "close": 3.95,
             "volume": 200, "money": 790},
            {"date": 20240102, "open": 3.8, "high": 3.9, "low": 3.7, "close": 3.85,
             "volume": 100, "money": 385},
        ]

    def init(self, host, port):
        self.init_args = (host, port)

    def set_init(self, endpoint):
        self.endpoint = endpoint

    def get_price(self, symbol, **kwargs):
        self.price_calls.append((symbol, kwargs))
        return self.price_rows

    def get_fundamentals(self, query, statDate):
        return {"query": query, "statDate": statDate}

    def get_last_tick(self, symbol, count):
        return {"symbol": symbol, "count": count}


def make_adapter():
    sdk = FakeSDK()
    return sdk, StockSDKAdapter(sdk, "127.0.0.1", 7899, "127.0.0.1:12328")


def test_initializes_both_sdk_endpoints():
    sdk, _ = make_adapter()
    assert sdk.init_args == ("127.0.0.1", 7899)
    assert sdk.endpoint == "127.0.0.1:12328"


def test_daily_bars_use_online_unadjusted_api_and_are_chronological():
    sdk, adapter = make_adapter()
    bars = adapter.read_daily_bars("510300", "20240102", "20240103")
    assert [bar.trade_date for bar in bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert all(bar.source == "stock-sdk-online" for bar in bars)
    assert sdk.price_calls[0] == (
        "510300",
        {
            "start_date": "20240102",
            "end_date": "20240103",
            "frequency": "daily",
            "fields": ["open", "high", "low", "close", "volume", "money"],
            "fq": None,
            "panel": False,
        },
    )


def test_daily_query_rejects_partial_or_reversed_range():
    _, adapter = make_adapter()
    with pytest.raises(ValueError, match="supplied together"):
        adapter.read_daily_bars("510300", "20240101")
    with pytest.raises(ValueError, match="later"):
        adapter.read_daily_bars("510300", "20240103", "20240102")


def test_daily_query_rejects_duplicate_dates():
    sdk, adapter = make_adapter()
    sdk.price_rows = [sdk.price_rows[0], sdk.price_rows[0]]
    with pytest.raises(ValueError, match="duplicate"):
        adapter.read_daily_bars("510300")


def test_native_range_and_online_endpoints_are_kept_separate():
    sdk, adapter = make_adapter()
    assert adapter.read_native_daily_range("510300", "20240102", "20240103") == (
        "日k", "510300", "20240102>20240103"
    )
    assert adapter.read_fundamentals("cash-flow-query", "2024q4")["statDate"] == "2024q4"
    assert adapter.read_last_ticks("000001", count=5) == {"symbol": "000001", "count": 5}


def test_malformed_online_daily_record_is_rejected():
    sdk, adapter = make_adapter()
    sdk.price_rows = [{"date": "2024-01-02", "open": 3.8, "high": 3.9, "low": 3.7}]
    with pytest.raises(ValueError, match="missing OHLC"):
        adapter.read_daily_bars("510300")


def test_probe_reports_observed_coverage_and_unadjusted_price_basis():
    _, adapter = make_adapter()
    report = adapter.probe_symbol("510300")
    assert report["daily_bar_count"] == 2
    assert report["first_date"] == "2024-01-02"
    assert report["last_date"] == "2024-01-03"
    assert report["calendar_completeness"] == "UNKNOWN"
    assert report["adjustment_factor_status"] == "NOT_REQUIRED_FOR_EXECUTION_PRICES"
    assert report["price_basis"] == "UNADJUSTED_FQ_NONE"


def test_universe_probe_keeps_per_symbol_connection_failures_visible():
    sdk, adapter = make_adapter()
    original = sdk.get_price

    def get_price(symbol, **kwargs):
        if symbol == "BAD":
            raise ConnectionError("service unavailable")
        return original(symbol, **kwargs)

    sdk.get_price = get_price
    report = adapter.probe_universe(["510300", "BAD"])
    assert report["symbols"][0]["daily_bar_status"] == "PASS"
    assert report["symbols"][1]["daily_bar_status"] == "UNKNOWN"
    assert report["symbols"][1]["error_type"] == "ConnectionError"


def test_native_connection_failure_does_not_block_online_reads():
    sdk = FakeSDK()

    def fail_native_init(host, port):
        raise ConnectionRefusedError("native port refused")

    sdk.init = fail_native_init
    adapter = StockSDKAdapter(sdk, "106.75.217.246", 7899, "106.75.217.246:12328")

    assert adapter.read_daily_bars("510300")
    with pytest.raises(ConnectionError, match="native StockDB initialization failed"):
        adapter.read_native_daily_range("510300", "20240102", "20240103")
