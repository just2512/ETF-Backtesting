"""Adapter for the remote stock_sdk online API and optional native channel.

Historical executable prices come from the online get_price API with fq=None.
The native rd channel is independent: failure to initialize it must not prevent
online historical backtests from running.
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
    SOURCE_NAME = "stock-sdk-online"

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
        if not callable(getattr(sdk, "get_price", None)):
            raise TypeError("stock_sdk module must expose online get_price()")
        if not host or not online_endpoint or port < 1 or port > 65535:
            raise ValueError("valid host, port, and online_endpoint are required")

        self.sdk = sdk
        self.host = host
        self.port = port
        self.online_endpoint = online_endpoint
        self.native_init_error: Exception | None = None

        # The native StockDB port and online API are separate services. A
        # refused native connection must not short-circuit online initialization.
        try:
            sdk.init(host, port)
        except Exception as exc:  # surfaced through native-channel methods
            self.native_init_error = exc
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
        """Read online, unadjusted daily OHLCV; never fall back to local rd data."""
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

        records = self.sdk.get_price(
            symbol,
            start_date=start,
            end_date=end,
            frequency="daily",
            fields=["open", "high", "low", "close", "volume", "money"],
            fq=None,
            panel=False,
        )
        normalized = self._records_from_result(records)
        bars = [self._to_price_bar(symbol, row) for row in normalized]
        bars.sort(key=lambda bar: bar.trade_date)
        dates = [bar.trade_date for bar in bars]
        if len(dates) != len(set(dates)):
            raise ValueError(f"duplicate daily bars returned for {symbol}")
        return bars

    @staticmethod
    def _records_from_result(records: Any) -> list[Mapping[str, Any]]:
        if records is None:
            return []
        if callable(getattr(records, "reset_index", None)):
            records = records.reset_index()
        if callable(getattr(records, "to_dict", None)):
            try:
                records = records.to_dict("records")
            except TypeError:
                pass
        if isinstance(records, Mapping):
            # Some SDK builds return a column-oriented mapping.
            keys = list(records)
            values = [records[key] for key in keys]
            if values and all(isinstance(value, (list, tuple)) for value in values):
                if len({len(value) for value in values}) != 1:
                    raise ValueError("online get_price returned columns with different lengths")
                records = [dict(zip(keys, row, strict=True)) for row in zip(*values, strict=True)]
            else:
                records = [records]
        if not isinstance(records, (list, tuple)):
            raise TypeError("online get_price must return a DataFrame, mapping, or records")
        normalized: list[Mapping[str, Any]] = []
        for row in records:
            if not isinstance(row, Mapping):
                raise TypeError("each online daily record must be a mapping")
            item = dict(row)
            if "date" not in item:
                for candidate in ("time", "index", "level_0"):
                    if candidate in item:
                        item["date"] = item[candidate]
                        break
            if "amount" not in item and item.get("money") is not None:
                item["amount"] = item["money"]
            normalized.append(item)
        return normalized

    def read_trade_days(self, start: str, end: str) -> list[date]:
        """Read the authoritative online trading calendar for a bounded interval."""
        self._validate_range(start, end)
        getter = getattr(self.sdk, "get_trade_days", None)
        if not callable(getter):
            raise TypeError("stock_sdk module must expose get_trade_days()")
        result = getter(start_date=start, end_date=end)
        days = []
        for value in (() if result is None else result):
            if isinstance(value, datetime):
                days.append(value.date())
            elif isinstance(value, date):
                days.append(value)
            else:
                text = str(value)[:10]
                days.append(date.fromisoformat(text.replace("/", "-")))
        if days != sorted(set(days)):
            raise ValueError("online trading calendar must be unique and ascending")
        return days

    def read_history_constituents(self, index_id: str, as_of: date) -> Any:
        """Return the provider's dated historical index constituent/weight snapshot."""
        getter = getattr(self.sdk, "get_history_constituents", None)
        if not callable(getter):
            raise TypeError("stock_sdk module must expose get_history_constituents()")
        if not index_id:
            raise ValueError("index_id must not be empty; include the provider exchange suffix")
        return getter(index_id, date=as_of.isoformat())

    def probe_symbol(self, symbol: str) -> dict[str, object]:
        """Summarize online observed coverage without claiming calendar completeness."""
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
            "price_basis": "UNADJUSTED_FQ_NONE",
            "daily_bar_count": len(bars),
            "first_date": bars[0].trade_date.isoformat() if bars else None,
            "last_date": bars[-1].trade_date.isoformat() if bars else None,
            "daily_bar_status": "PASS" if bars else "MISSING",
            "data_quality": summarize_findings(findings),
            "adjustment_factor_status": "NOT_REQUIRED_FOR_EXECUTION_PRICES",
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
            except (ValueError, TypeError) as exc:
                results.append({
                    "symbol": symbol,
                    "source": self.SOURCE_NAME,
                    "daily_bar_status": "REJECT",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "corporate_action_status": "UNKNOWN",
                    "historical_index_constituent_status": "UNKNOWN",
                    "calendar_completeness": "UNKNOWN",
                })
            except Exception as exc:
                results.append({
                    "symbol": symbol,
                    "source": self.SOURCE_NAME,
                    "daily_bar_status": "UNKNOWN",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "corporate_action_status": "UNKNOWN",
                    "historical_index_constituent_status": "UNKNOWN",
                    "calendar_completeness": "UNKNOWN",
                })
        return {"source": self.SOURCE_NAME, "symbols": results}

    def read_native_daily_range(self, symbol: str, start: str, end: str) -> Any:
        """Use the optional native rd channel without coupling it to online reads."""
        self._validate_range(start, end)
        if self.native_init_error is not None:
            raise ConnectionError("native StockDB initialization failed") from self.native_init_error
        rd = getattr(self.sdk, "rd", None)
        native_get = getattr(rd, "get", None)
        if not callable(native_get):
            raise TypeError("stock_sdk.rd must expose get() for native range reads")
        return native_get("日k", symbol, f"{start}>{end}")

    def read_fundamentals(self, query_object: Any, stat_date: str) -> Any:
        """Return online fundamentals without coercing provider-specific schemas."""
        getter = getattr(self.sdk, "get_fundamentals", None)
        if not callable(getter):
            raise TypeError("stock_sdk module must expose get_fundamentals()")
        if not stat_date:
            raise ValueError("stat_date must not be empty")
        return getter(query_object, statDate=stat_date)

    def read_last_ticks(self, symbol: str, count: int = 10) -> Any:
        """Return online tick slices; ticks are not used as daily history."""
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
    def _to_price_bar(cls, symbol: str, row: Mapping[str, Any]) -> PriceBar:
        raw_date = row.get("date")
        if isinstance(raw_date, datetime):
            trade_date = raw_date.date()
        elif isinstance(raw_date, date):
            trade_date = raw_date
        elif callable(getattr(raw_date, "to_pydatetime", None)):
            converted = raw_date.to_pydatetime()
            trade_date = converted.date() if isinstance(converted, datetime) else converted
        else:
            value = str(raw_date or "")[:10]
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
