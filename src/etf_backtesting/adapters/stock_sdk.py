"""Adapter for the remote/local stock_sdk Python API.

The SDK exposes both native range reads and a documented normalized get_data API.
Only unadjusted daily bars are admitted as executable prices. Fundamentals and live
ticks are exposed as raw supplemental reads and are never mixed into historical bars.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from etf_backtesting.contracts import PriceBar
from etf_backtesting.data.audit import audit_daily_records, summarize_findings


class StockSDKAdapter:
    SOURCE_NAME = "stock-sdk"

    def __init__(
        self,
        sdk: Any,
        host: str,
        port: int,
        online_endpoint: str,
    ) -> None:
        if not callable(getattr(sdk, "init", None)):
            raise TypeError("stock_sdk module must expose init(host, port)")
        if not callable(getattr(sdk, "set_init", None)):
            raise TypeError("stock_sdk module must expose set_init(endpoint)")
        rd = getattr(sdk, "rd", None)
        if not callable(getattr(rd, "get_data", None)):
            raise TypeError("stock_sdk.rd must expose get_data()")
        if not host or not online_endpoint or port < 1 or port > 65535:
            raise ValueError("valid host, port, and online_endpoint are required")

        self.sdk = sdk
        self.host = host
        self.port = port
        self.online_endpoint = online_endpoint
        sdk.init(host, port)
        sdk.set_init(online_endpoint)

    @classmethod
    def connect(
        cls,
        host: str,
        port: int,
        online_endpoint: str,
        sdk_module: str = "stock_sdk",
    ) -> StockSDKAdapter:
        return cls(importlib.import_module(sdk_module), host, port, online_endpoint)

    @classmethod
    def from_environment(cls) -> StockSDKAdapter:
        host = os.getenv("STOCKSDK_HOST")
        port_text = os.getenv("STOCKSDK_PORT", "7899")
        endpoint = os.getenv("STOCKSDK_ONLINE_ENDPOINT")
        if not host or not endpoint:
            raise ValueError(
                "STOCKSDK_HOST and STOCKSDK_ONLINE_ENDPOINT must be configured; "
                "do not embed service addresses or credentials in source control"
            )
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("STOCKSDK_PORT must be an integer") from exc
        return cls.connect(
            host=host,
            port=port,
            online_endpoint=endpoint,
            sdk_module=os.getenv("STOCKSDK_MODULE", "stock_sdk"),
        )

    def read_daily_bars(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        """Read raw, unadjusted daily OHLCV through the SDK's normalized API."""
        if not symbol:
            raise ValueError("symbol must not be empty")
        if (start is None) != (end is None):
            raise ValueError("start and end must be supplied together")
        if start is not None and (len(start) != 8 or not start.isdigit()):
            raise ValueError("start must use YYYYMMDD")
        if end is not None and (len(end) != 8 or not end.isdigit()):
            raise ValueError("end must use YYYYMMDD")
        if start is not None and end is not None and start > end:
            raise ValueError("start must not be later than end")

        records = self.sdk.rd.get_data(
            code=symbol,
            start=start,
            end=end,
            frequency="1d",
            fq=None,
            desc=False,
            as_df=False,
        )
        if records is None:
            return []
        if callable(getattr(records, "to_dict", None)):
            records = records.to_dict("records")
        if not isinstance(records, (list, tuple)):
            raise TypeError("stock_sdk daily query must return a list or DataFrame")

        bars = [self._to_price_bar(symbol, row) for row in records]
        bars.sort(key=lambda bar: bar.trade_date)
        dates = [bar.trade_date for bar in bars]
        if len(dates) != len(set(dates)):
            raise ValueError(f"duplicate daily bars returned for {symbol}")
        return bars

    def probe_symbol(self, symbol: str) -> dict[str, object]:
        """Summarize observed daily coverage without claiming calendar completeness."""
        bars = self.read_daily_bars(symbol)
        records = [
            {
                "date": bar.trade_date.strftime("%Y%m%d"),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "amount": bar.amount,
            }
            for bar in bars
        ]
        findings = audit_daily_records(symbol, records)
        return {
            "symbol": symbol,
            "source": self.SOURCE_NAME,
            "daily_bar_count": len(bars),
            "first_date": bars[0].trade_date.isoformat() if bars else None,
            "last_date": bars[-1].trade_date.isoformat() if bars else None,
            "daily_bar_status": "PASS" if bars else "MISSING",
            "data_quality": summarize_findings(findings),
            "adjustment_factor_status": "UNKNOWN",
            "corporate_action_status": "UNKNOWN",
            "historical_index_constituent_status": "UNKNOWN",
            "calendar_completeness": "UNKNOWN",
        }

    def probe_universe(self, symbols: list[str]) -> dict[str, object]:
        """Probe each symbol independently; a failure for one symbol remains visible."""
        results = []
        for symbol in symbols:
            try:
                results.append(self.probe_symbol(symbol))
            except Exception as exc:
                results.append({
                    "symbol": symbol,
                    "source": self.SOURCE_NAME,
                    "daily_bar_status": "UNKNOWN",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "adjustment_factor_status": "UNKNOWN",
                    "corporate_action_status": "UNKNOWN",
                    "historical_index_constituent_status": "UNKNOWN",
                    "calendar_completeness": "UNKNOWN",
                })
        return {"source": self.SOURCE_NAME, "symbols": results}

    def read_native_daily_range(self, symbol: str, start: str, end: str) -> Any:
        """Expose the native rd.get range response without assuming its schema."""
        self._validate_range(start, end)
        native_get = getattr(self.sdk.rd, "get", None)
        if not callable(native_get):
            raise TypeError("stock_sdk.rd must expose get() for native range reads")
        return native_get("日k", symbol, f"{start}>{end}")

    def read_fundamentals(self, query_object: Any, stat_date: str) -> Any:
        """Return the SDK's online fundamentals response without coercing its schema."""
        getter = getattr(self.sdk, "get_fundamentals", None)
        if not callable(getter):
            raise TypeError("stock_sdk module must expose get_fundamentals()")
        if not stat_date:
            raise ValueError("stat_date must not be empty")
        return getter(query_object, statDate=stat_date)

    def read_last_ticks(self, symbol: str, count: int = 10) -> Any:
        """Return online tick slices as supplied by the SDK; not used as daily history."""
        getter = getattr(self.sdk, "get_last_tick", None)
        if not callable(getter):
            raise TypeError("stock_sdk module must expose get_last_tick()")
        if not symbol or count < 1:
            raise ValueError("symbol must not be empty and count must be positive")
        return getter(symbol, count=count)

    @staticmethod
    def _validate_range(start: str, end: str) -> None:
        if any(len(value) != 8 or not value.isdigit() for value in (start, end)):
            raise ValueError("date range must use YYYYMMDD")
        if start > end:
            raise ValueError("start must not be later than end")

    @classmethod
    def _to_price_bar(cls, symbol: str, row: Any) -> PriceBar:
        if not isinstance(row, Mapping):
            raise TypeError("each stock_sdk daily record must be a mapping")
        raw_date = row.get("date")
        if isinstance(raw_date, datetime):
            trade_date = raw_date.date()
        elif isinstance(raw_date, date):
            trade_date = raw_date
        else:
            value = str(raw_date or "")
            if len(value) == 8 and value.isdigit():
                trade_date = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
            elif len(value) == 10 and value[4] == "-" and value[7] == "-":
                trade_date = date.fromisoformat(value)
            else:
                raise ValueError(f"invalid daily date for {symbol}: {raw_date!r}")

        required = ("open", "high", "low", "close")
        missing = [name for name in required if row.get(name) is None]
        if missing:
            raise ValueError(f"missing OHLC fields for {symbol} on {trade_date}: {missing}")
        return PriceBar(
            symbol=symbol,
            trade_date=trade_date,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]) if row.get("volume") is not None else None,
            amount=float(row["amount"]) if row.get("amount") is not None else None,
            source=cls.SOURCE_NAME,
        )
