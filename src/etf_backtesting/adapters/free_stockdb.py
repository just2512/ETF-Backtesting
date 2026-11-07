"""Adapter for the user's local free-stockdb service.

The repository contains the SDK source, but market data itself is stored locally.
This adapter therefore connects to a running local StockDB instance and never
assumes that GitHub source presence proves local data coverage.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterable
from datetime import date
from typing import Any

from etf_backtesting.contracts import PriceBar


class FreeStockDBAdapter:
    SOURCE_NAME = "free-stockdb"

    def __init__(self, client: Any) -> None:
        if not callable(getattr(client, "get_data", None)):
            raise TypeError("client must expose get_data()")
        self.client = client

    @classmethod
    def connect(
        cls,
        host: str = "127.0.0.1",
        port: int = 7899,
        password: str = "",
        sdk_module: str = "stock_sdk",
    ) -> FreeStockDBAdapter:
        """Import the installed SDK and connect to the local service."""
        module = importlib.import_module(sdk_module)
        client_type = module.StockDBClient
        return cls(client_type(host=host, port=port, password=password))

    @classmethod
    def from_environment(cls) -> FreeStockDBAdapter:
        return cls.connect(
            host=os.getenv("FREESTOCKDB_HOST", "127.0.0.1"),
            port=int(os.getenv("FREESTOCKDB_PORT", "7899")),
            password=os.getenv("FREESTOCKDB_PASSWORD", ""),
            sdk_module=os.getenv("FREESTOCKDB_SDK_MODULE", "stock_sdk"),
        )

    def read_daily_bars(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        """Read unadjusted daily bars. These prices are used for simulated fills."""
        records = self.client.get_data(
            code=symbol,
            start=start,
            end=end,
            frequency="1d",
            fq=None,
            desc=False,
            as_df=False,
        )
        return [self._to_price_bar(symbol, item) for item in records or []]

    def read_adjustment_factors(self, symbol: str) -> list[dict[str, object]]:
        """Expose SDK-preloaded cumulative factors without guessing their semantics."""
        dates = getattr(self.client, "_fq_dates", {}).get(symbol, [])
        values = getattr(self.client, "_fq_cums", {}).get(symbol, [])
        if len(dates) != len(values):
            raise ValueError(f"adjustment factor date/value length mismatch for {symbol}")
        return [
            {"symbol": symbol, "effective_date": str(day), "factor": float(value),
             "factor_type": "CUMULATIVE_SOURCE_FACTOR"}
            for day, value in zip(dates, values, strict=True)
        ]

    def read_cash_dividends(self, symbol: str) -> None:
        """The inspected public SDK does not expose a documented cash-dividend API."""
        del symbol

    def read_historical_index_constituents(self, index_id: str) -> None:
        """The inspected public SDK does not expose dated historical index constituents."""
        del index_id

    def probe_symbol(self, symbol: str) -> dict[str, object]:
        bars = self.read_daily_bars(symbol)
        factors = self.read_adjustment_factors(symbol)
        return {
            "symbol": symbol,
            "daily_bar_status": "PASS" if bars else "MISSING",
            "daily_bar_count": len(bars),
            "first_date": bars[0].trade_date.isoformat() if bars else None,
            "last_date": bars[-1].trade_date.isoformat() if bars else None,
            "adjustment_factor_status": "PASS" if factors else "MISSING",
            "adjustment_factor_count": len(factors),
            "cash_dividend_status": "MISSING",
            "historical_index_constituent_status": "MISSING",
        }

    @staticmethod
    def _to_price_bar(symbol: str, record: dict[str, Any]) -> PriceBar:
        raw_date = str(record.get("date", ""))
        if len(raw_date) != 8 or not raw_date.isdigit():
            raise ValueError(f"invalid daily date for {symbol}: {raw_date!r}")
        return PriceBar(
            symbol=symbol,
            trade_date=date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8])),
            open=float(record["open"]),
            high=float(record["high"]),
            low=float(record["low"]),
            close=float(record["close"]),
            volume=float(record["volume"]) if record.get("volume") is not None else None,
            amount=float(record["amount"]) if record.get("amount") is not None else None,
            source=FreeStockDBAdapter.SOURCE_NAME,
        )


def probe_universe(
    adapter: FreeStockDBAdapter,
    symbols: Iterable[str],
) -> dict[str, object]:
    results = [adapter.probe_symbol(symbol) for symbol in symbols]
    return {
        "source": FreeStockDBAdapter.SOURCE_NAME,
        "symbols": results,
        "cash_dividend_api": "NOT_EXPOSED_BY_INSPECTED_SDK",
        "historical_index_constituent_api": "NOT_EXPOSED_BY_INSPECTED_SDK",
    }
