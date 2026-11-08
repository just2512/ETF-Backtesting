from __future__ import annotations

import json

import pytest

from etf_backtesting.adapters import free_stockdb_http_sdk as sdk


def test_get_price_reads_prefix_rows_and_filters_dates(monkeypatch):
    monkeypatch.setattr(sdk, "_endpoint", "https://stockdb.example")
    captured = {}

    def fake_request(params, timeout=30.0):
        captured.update(params)
        return [
            ["日k:510300:20200102", json.dumps({"open": 4, "high": 5, "low": 3, "close": 4.5, "volume": 10, "money": 20})],
            ["日k:510300:20200103", {"open": 5, "high": 6, "low": 4, "close": 5.5, "volume": 11, "amount": 21}],
            ["日k:510300:20200106", {"open": 6, "high": 7, "low": 5, "close": 6.5, "volume": 12, "amount": 22}],
        ]

    monkeypatch.setattr(sdk, "_request_json", fake_request)
    rows = sdk.get_price("510300", start_date="2020-01-03", end_date="20200106", fq=None)
    assert captured == {"cmd": "get", "t": "日k:510300:*"}
    assert [row["date"] for row in rows] == ["20200103", "20200106"]
    assert rows[0]["amount"] == 21
    assert rows[0]["code"] == "510300"


def test_get_price_rejects_malformed_rows(monkeypatch):
    monkeypatch.setattr(sdk, "_endpoint", "https://stockdb.example")
    monkeypatch.setattr(sdk, "_request_json", lambda *_args, **_kwargs: [["wrong-key", {}]])
    with pytest.raises(ValueError, match="outside the requested symbol prefix"):
        sdk.get_price("510300")


def test_get_price_empty_prefix_is_missing(monkeypatch):
    monkeypatch.setattr(sdk, "_endpoint", "https://stockdb.example")
    monkeypatch.setattr(sdk, "_request_json", lambda *_args, **_kwargs: {"status": "not_found"})
    assert sdk.get_price("510300") == []


def test_calendar_and_index_apis_are_explicitly_unsupported():
    with pytest.raises(NotImplementedError, match="trading-calendar"):
        sdk.get_trade_days(start_date="2020-01-01", end_date="2020-01-31")
    with pytest.raises(NotImplementedError, match="constituent"):
        sdk.get_index_stocks("000300.XSHG", date="2020-01-31")
    with pytest.raises(NotImplementedError, match="weight"):
        sdk.get_index_weights("000300.XSHG", date="2020-01-31")


def test_init_does_not_require_native_stockdb():
    sdk.init("127.0.0.1", 7899)
    sdk.set_init("https://stockdb.example", df=True)
    assert sdk._endpoint == "https://stockdb.example"


def test_adapter_from_environment_needs_no_native_host(monkeypatch):
    from etf_backtesting.adapters.stock_sdk import StockSDKAdapter

    monkeypatch.delenv("STOCKSDK_HOST", raising=False)
    monkeypatch.delenv("STOCKSDK_PORT", raising=False)
    monkeypatch.setenv("STOCKSDK_ONLINE_ENDPOINT", "https://stockdb.example")
    monkeypatch.setenv(
        "STOCKSDK_MODULE",
        "etf_backtesting.adapters.free_stockdb_http_sdk",
    )
    adapter = StockSDKAdapter.from_environment()
    assert adapter.native_init_error is None
    assert adapter.online_endpoint == "https://stockdb.example"
    assert adapter.history_api == "get_price"
