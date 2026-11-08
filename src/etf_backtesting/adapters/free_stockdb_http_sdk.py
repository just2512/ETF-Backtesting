"""HTTP-only client for a self-hosted free-stockdb HTTP server.

It intentionally avoids the native stockdb.pyd dependency. The upstream HTTP
server exposes a documented cmd=get prefix scan; calendar and index endpoints
are not part of that protocol and remain explicitly unsupported.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_endpoint = ""


def init(host: str = "127.0.0.1", port: int = 7899, **_: Any) -> None:
    """Compatibility shim; no native socket is opened."""
    del host, port


def set_init(ip: str = "", df: bool | None = None, **_: Any) -> None:
    """Configure the HTTP base URL."""
    del df
    global _endpoint
    _endpoint = ip.rstrip("/")


def _request_json(params: dict[str, str], timeout: float = 30.0) -> Any:
    if not _endpoint:
        raise ValueError("STOCKSDK_ONLINE_ENDPOINT must be configured")
    request = Request(
        f"{_endpoint}/?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "ETF-Backtesting/1.0"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ConnectionError(f"free-stockdb HTTP request failed: {exc}") from exc
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("free-stockdb returned invalid UTF-8 JSON") from exc


def _normalize_date(value: str) -> str:
    text = str(value).replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError("date arguments must use YYYYMMDD or YYYY-MM-DD")
    date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    return text


def get_price(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    frequency: str = "daily",
    fields: list[str] | None = None,
    fq: Any = None,
    panel: bool = False,
) -> list[dict[str, Any]]:
    """Read unadjusted daily bars from StockDB's dated key prefix."""
    del fields, panel
    if frequency not in ("daily", "1d", "D"):
        raise ValueError("free-stockdb HTTP adapter supports daily bars only")
    if fq is not None:
        raise ValueError("free-stockdb raw daily-bar adapter requires fq=None")
    if not symbol or any(ch in symbol for ch in ":*"):
        raise ValueError("symbol must be a plain ETF code")
    start = _normalize_date(start_date) if start_date else None
    end = _normalize_date(end_date) if end_date else None
    if start and end and start > end:
        raise ValueError("start_date must not be later than end_date")

    result = _request_json({"cmd": "get", "t": f"日k:{symbol}:*"})
    if isinstance(result, dict) and result.get("status") == "not_found":
        return []
    if not isinstance(result, list):
        raise ValueError("prefix query must return a list of [key, value] rows")

    prefix = f"日k:{symbol}:"
    rows: list[dict[str, Any]] = []
    for entry in result:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("free-stockdb returned a malformed key/value row")
        key, raw_value = entry
        if not isinstance(key, str) or not key.startswith(prefix):
            raise ValueError("free-stockdb returned a key outside the requested symbol prefix")
        day = key[len(prefix):]
        if len(day) != 8 or not day.isdigit():
            raise ValueError(f"invalid daily-bar key: {key!r}")
        if (start and day < start) or (end and day > end):
            continue
        value = raw_value
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"daily-bar value is not JSON for {key!r}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"daily-bar value must be an object for {key!r}")
        row = dict(value)
        row["date"] = day
        row.setdefault("code", symbol)
        if "amount" not in row and row.get("money") is not None:
            row["amount"] = row["money"]
        rows.append(row)
    rows.sort(key=lambda row: str(row["date"]))
    if len({row["date"] for row in rows}) != len(rows):
        raise ValueError(f"duplicate daily bars returned for {symbol}")
    return rows


def get_trade_days(*_: Any, **__: Any) -> list[date]:
    raise NotImplementedError(
        "free-stockdb HTTP protocol has no authoritative trading-calendar endpoint"
    )


def get_index_stocks(*_: Any, **__: Any) -> Any:
    raise NotImplementedError(
        "free-stockdb HTTP protocol has no historical index-constituent endpoint"
    )


def get_index_weights(*_: Any, **__: Any) -> Any:
    raise NotImplementedError(
        "free-stockdb HTTP protocol has no historical index-weight endpoint"
    )
