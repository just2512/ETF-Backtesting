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
        rd = getattr(sdk, "rd", None)
        has_online_get_price = callable(getattr(sdk, "get_price", None))
        has_native_get_data = callable(getattr(rd, "get_data", None))
        if not has_online_get_price and not has_native_get_data:
            raise TypeError(
                "stock_sdk must expose get_price() or rd.get_data() for historical daily bars"
            )
        if not host or not online_endpoint or port < 1 or port > 65535:
            raise ValueError("valid host, port, and online_endpoint are required")

        self.sdk = sdk
        self.host = host
        self.port = port
        self.online_endpoint = online_endpoint
        self.native_init_error: Exception | None = None
        self._dataframe_mode_was_set = False
        self.history_api = (
            "get_price" if has_online_get_price else "rd.get_data"
        )

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
        # The default cloud path is the HTTP-only free-stockdb SDK. Its
        # compatibility init() is a no-op, so a local/native StockDB host is
        # not required. A custom/native SDK can still override STOCKSDK_HOST.
        host = os.getenv("STOCKSDK_HOST", "127.0.0.1")
        port_text = os.getenv("STOCKSDK_PORT", "7899")
        endpoint = os.getenv("STOCKSDK_ONLINE_ENDPOINT")
        if not endpoint:
            raise ValueError(
                "STOCKSDK_ONLINE_ENDPOINT must be configured; "
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
            sdk_module=os.getenv(
                "STOCKSDK_MODULE",
                "etf_backtesting.adapters.free_stockdb_http_sdk",
            ),
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

        if callable(getattr(self.sdk, "get_price", None)):
            records = self._read_price_dataframe(symbol, start, end)
        else:
            if self.native_init_error is not None:
                raise ConnectionError(
                    "rd.get_data is the only historical API but native StockDB initialization failed"
                ) from self.native_init_error
            rd = getattr(self.sdk, "rd", None)
            getter = getattr(rd, "get_data", None)
            if not callable(getter):
                raise TypeError("stock_sdk.rd must expose get_data()")
            records = getter(
                code=symbol,
                start=start,
                end=end,
                frequency="1d",
                fq=None,
                as_df=True,
            )
        normalized = self._records_from_result(records)
        bars = [self._to_price_bar(symbol, row) for row in normalized]
        bars.sort(key=lambda bar: bar.trade_date)
        dates = [bar.trade_date for bar in bars]
        if len(dates) != len(set(dates)):
            raise ValueError(f"duplicate daily bars returned for {symbol}")
        return bars

    def _read_price_dataframe(self, symbol: str, start: str | None, end: str | None) -> Any:
        """Call online get_price in df mode so each row carries its date.

        In list mode (set_init(df=None)) the SDK drops the date column from
        get_price results, which makes multi-day history ambiguous. The SDK
        documents that df=True returns a DataFrame with dates in the index.
        Open-ended ranges (start/end None) pass through unchanged.
        """
        setter = getattr(self.sdk, "set_init", None)
        if callable(setter) and not self._dataframe_mode_was_set:
            # df=True persists for the process; set once per adapter so callers
            # that manage their own set_init state are not overridden silently.
            setter(self.online_endpoint, df=True)
            self._dataframe_mode_was_set = True
        # Do not wrap SDK exceptions: probe/export layers classify per-symbol
        # failures by the original exception type, and degraded online service
        # errors must stay visible with their real identity.
        records = self.sdk.get_price(
            symbol,
            start_date=start,
            end_date=end,
            frequency="daily",
            fields=["open", "high", "low", "close", "volume", "money"],
            fq=None,
            panel=False,
        )
        # Live-service contract (verified 2026-11-08): the online API reports
        # server-side failures by returning a bare error string ("执行查询时发
        # 生错误") instead of raising. A string is never price data; surface
        # the exact text instead of masking it as a schema problem.
        return self._raise_on_service_error(records, "get_price", symbol)

    @staticmethod
    def _raise_on_service_error(result: Any, api_name: str, context: str = "") -> Any:
        """Convert the provider's bare-text failure response at the API boundary."""
        if isinstance(result, str):
            detail = result.strip()
            suffix = f" for {context}" if context else ""
            raise ConnectionError(
                f"online {api_name}{suffix} returned a service error string: {detail!r}"
            )
        return result

    def _records_from_result(self, records: Any) -> list[Mapping[str, Any]]:
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
        """Read the authoritative online trading calendar for a bounded interval.

        Live-service contract (verified 2026-11-08): get_trade_days silently
        returns an empty list for YYYYMMDD arguments; only dashed ISO dates
        produce sessions. 8-digit input is therefore converted before the call.
        """
        self._validate_range(start, end)
        calendar_api = os.getenv("STOCKSDK_TRADE_DAYS_API", "get_trade_days")
        getter = getattr(self.sdk, calendar_api, None)
        if not callable(getter):
            raise TypeError(
                f"stock_sdk module must expose configured trading-calendar API {calendar_api}()"
            )
        result = getter(
            start_date=self._dashed(start),
            end_date=self._dashed(end),
        )
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

    @staticmethod
    def _dashed(value: str) -> str:
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"

    def read_history_constituents(self, index_id: str, as_of: date) -> Any:
        """Return the provider's dated historical index constituent/weight snapshot."""
        if not index_id:
            raise ValueError("index_id must not be empty; include the provider exchange suffix")
        index_api = os.getenv("STOCKSDK_INDEX_API", "").strip()
        if index_api:
            getter = getattr(self.sdk, index_api, None)
            if not callable(getter):
                raise TypeError(
                    f"stock_sdk module must expose configured historical-index API {index_api}()"
                )
            result = getter(index_id, date=as_of.isoformat())
            return self._raise_on_service_error(result, index_api, index_id)

        stocks_api = os.getenv("STOCKSDK_INDEX_STOCKS_API", "get_index_stocks")
        weights_api = os.getenv("STOCKSDK_INDEX_WEIGHTS_API", "get_index_weights")
        stocks_getter = getattr(self.sdk, stocks_api, None)
        weights_getter = getattr(self.sdk, weights_api, None)
        if callable(stocks_getter) and callable(weights_getter):
            stocks = self._raise_on_service_error(
                stocks_getter(index_id, date=as_of.isoformat()),
                stocks_api,
                index_id,
            )
            weights = self._raise_on_service_error(
                weights_getter(index_id, date=as_of.isoformat()),
                weights_api,
                index_id,
            )
            return {"stocks": stocks, "weights": weights}

        fallback_api = "get_history_constituents"
        fallback_getter = getattr(self.sdk, fallback_api, None)
        if callable(fallback_getter):
            result = fallback_getter(index_id, date=as_of.isoformat())
            return self._raise_on_service_error(result, fallback_api, index_id)
        raise TypeError(
            "stock_sdk must expose either the configured combined index API or "
            f"both {stocks_api}() and {weights_api}()"
        )

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
            "history_api": self.history_api,
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
        result = getter(query_object, statDate=stat_date)
        return self._raise_on_service_error(result, "get_fundamentals", stat_date)

    def read_last_ticks(self, symbol: str, count: int = 10) -> Any:
        """Return online tick slices; ticks are not used as daily history."""
        getter = getattr(self.sdk, "get_last_tick", None)
        if not callable(getter):
            raise TypeError("stock_sdk module must expose get_last_tick()")
        if not symbol or count < 1:
            raise ValueError("symbol must not be empty and count must be positive")
        result = getter(symbol, count=count)
        return self._raise_on_service_error(result, "get_last_tick", symbol)

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
