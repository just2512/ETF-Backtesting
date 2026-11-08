from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from etf_backtesting.adapters.stock_sdk import StockSDKAdapter


class OnlineSDK:
    def __init__(self, *, native_error: Exception | None = None) -> None:
        self.native_error = native_error
        self.native_calls: list[tuple[object, ...]] = []
        self.online_endpoint: str | None = None
        self.price_kwargs: dict[str, object] | None = None
        self.calendar_kwargs: dict[str, object] | None = None
        self.constituent_call: tuple[object, ...] | None = None
        self.df_mode_set = False
        self.rd = SimpleNamespace(get=self.native_get)

    def init(self, host: str, port: int) -> None:
        self.native_calls.append((host, port))
        if self.native_error:
            raise self.native_error

    def set_init(self, endpoint: str, *, df: object = None) -> None:
        self.online_endpoint = endpoint
        if df is True:
            self.df_mode_set = True

    def get_price(self, symbol: str, **kwargs: object) -> list[dict[str, object]]:
        self.price_kwargs = kwargs
        return [
            {
                "date": "2024-01-03",
                "open": 3.1,
                "high": 3.3,
                "low": 3.0,
                "close": 3.2,
                "volume": 1000,
                "money": 3200,
            },
            {
                "date": "2024-01-02",
                "open": 3.0,
                "high": 3.2,
                "low": 2.9,
                "close": 3.1,
                "volume": 900,
                "money": 2790,
            },
        ]

    def get_trade_days(self, **kwargs: object) -> list[str]:
        self.calendar_kwargs = kwargs
        return ["2024-01-02", "2024-01-03"]

    def get_history_constituents(self, index_id: str, *, date: str) -> dict[str, object]:
        self.constituent_call = (index_id, date)
        return {"snapshot_date": date, "constituents": []}

    def native_get(self, *args: object) -> object:
        return args


def make_adapter(sdk: OnlineSDK) -> StockSDKAdapter:
    return StockSDKAdapter(sdk, "106.75.217.246", 7899, "106.75.217.246:12328")


def test_online_prices_work_when_native_port_is_refused() -> None:
    sdk = OnlineSDK(native_error=ConnectionRefusedError("7899 refused"))
    adapter = make_adapter(sdk)

    bars = adapter.read_daily_bars("510300")

    assert sdk.online_endpoint == "106.75.217.246:12328"
    assert [bar.trade_date.isoformat() for bar in bars] == ["2024-01-02", "2024-01-03"]
    assert bars[0].source == "stock-sdk-online"
    assert bars[0].amount == 2790
    assert sdk.price_kwargs is not None
    assert sdk.price_kwargs["fq"] is None
    assert sdk.price_kwargs["frequency"] == "daily"


def test_online_range_and_empty_results_are_explicit() -> None:
    sdk = OnlineSDK()
    adapter = make_adapter(sdk)

    adapter.read_daily_bars("510300", "20240101", "20240131")

    assert sdk.price_kwargs is not None
    assert sdk.price_kwargs["start_date"] == "20240101"
    assert sdk.price_kwargs["end_date"] == "20240131"
    with pytest.raises(ValueError, match="supplied together"):
        adapter.read_daily_bars("510300", "20240101")


def test_online_calendar_and_historical_constituents_use_explicit_dates() -> None:
    sdk = OnlineSDK()
    adapter = make_adapter(sdk)

    assert adapter.read_trade_days("20240101", "20240131") == [
        date(2024, 1, 2),
        date(2024, 1, 3),
    ]
    adapter.read_history_constituents("000300.XSHG", date(2020, 6, 30))

    # Live-service contract: YYYYMMDD calendar arguments silently return an
    # empty session list, so the adapter must send dashed ISO dates.
    assert sdk.calendar_kwargs == {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    }
    assert sdk.constituent_call == ("000300.XSHG", "2020-06-30")


def test_online_price_requires_dataframe_mode_for_dated_rows() -> None:
    sdk = OnlineSDK()
    adapter = make_adapter(sdk)

    bars = adapter.read_daily_bars("510300", "20240101", "20240131")
    assert [bar.trade_date.isoformat() for bar in bars] == ["2024-01-02", "2024-01-03"]

    # list-mode get_price drops the date column (verified against the live
    # service), so the adapter must switch the SDK to df mode before querying.
    assert sdk.df_mode_set is True


def test_native_channel_failure_is_reported_only_when_native_is_used() -> None:
    sdk = OnlineSDK(native_error=ConnectionRefusedError("7899 refused"))
    adapter = make_adapter(sdk)

    with pytest.raises(ConnectionError, match="native StockDB initialization failed"):
        adapter.read_native_daily_range("600633", "20260727", "20260729")

    # The online API remains usable despite the independent native failure.
    assert adapter.read_daily_bars("510300")
