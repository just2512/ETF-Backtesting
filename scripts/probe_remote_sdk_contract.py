"""Inspect the exact installed remote stock_sdk contract without reading local market data."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from etf_backtesting.adapters.stock_sdk import StockSDKAdapter


def _signature(value: Any) -> str | None:
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return None


def _sample_payload(raw: Any) -> dict[str, object]:
    """Describe raw provider columns and sample rows without guessing their meaning."""
    if raw is None:
        return {"status": "MISSING", "row_count": 0, "columns": [], "sample_rows": []}

    if callable(getattr(raw, "columns", None)):
        pass
    columns = getattr(raw, "columns", None)
    if columns is not None:
        names = [str(item) for item in list(columns)]
        row_count = len(raw)
        sample_rows = raw.head(5).to_dict(orient="records")
        dtypes = {str(key): str(value) for key, value in raw.dtypes.items()}
    elif isinstance(raw, Mapping):
        names = [str(key) for key in raw]
        values = list(raw.values())
        if values and all(isinstance(value, (list, tuple)) for value in values):
            lengths = {len(value) for value in values}
            if len(lengths) != 1:
                return {
                    "status": "REJECT",
                    "error": "column-oriented response has inconsistent lengths",
                    "columns": names,
                    "sample_rows": [],
                }
            rows = [
                dict(zip(names, row, strict=True))
                for row in zip(*values, strict=True)
            ]
        else:
            rows = [dict(raw)]
        row_count = len(rows)
        sample_rows = rows[:5]
        dtypes = {}
    elif isinstance(raw, (list, tuple)):
        row_count = len(raw)
        sample_rows = list(raw[:5])
        first = raw[0] if raw else None
        names = list(first) if isinstance(first, Mapping) else []
        dtypes = {}
    else:
        return {
            "status": "UNKNOWN",
            "python_type": type(raw).__name__,
            "repr": repr(raw)[:2000],
            "columns": [],
            "sample_rows": [],
        }

    numeric_summary: dict[str, dict[str, str | int]] = {}
    if sample_rows and all(isinstance(row, Mapping) for row in sample_rows):
        # Compute candidate numeric summaries across the full returned frame when possible.
        source_rows = raw.to_dict(orient="records") if columns is not None else sample_rows
        for name in names:
            values: list[Decimal] = []
            for row in source_rows:
                try:
                    value = Decimal(str(row.get(name)))
                except (InvalidOperation, TypeError, ValueError):
                    continue
                if value.is_finite():
                    values.append(value)
            if values:
                numeric_summary[name] = {
                    "count": len(values),
                    "min": str(min(values)),
                    "max": str(max(values)),
                    "sum": str(sum(values, Decimal("0"))),
                }

    return {
        "status": "PASS" if row_count else "MISSING",
        "python_type": type(raw).__name__,
        "row_count": row_count,
        "columns": names,
        "dtypes": dtypes,
        "numeric_column_summaries": numeric_summary,
        "sample_rows": sample_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-id", default="000300.XSHG")
    parser.add_argument("--date", default="2020-06-30")
    parser.add_argument("--calendar-start", default="2020-06-01")
    parser.add_argument("--calendar-end", default="2020-07-31")
    parser.add_argument("--output", default="reports/audit/remote_sdk_contract.json")
    args = parser.parse_args()

    try:
        snapshot_date = date.fromisoformat(args.date)
        calendar_start = date.fromisoformat(args.calendar_start).strftime("%Y%m%d")
        calendar_end = date.fromisoformat(args.calendar_end).strftime("%Y%m%d")
        adapter = StockSDKAdapter.from_environment()
        sdk = adapter.sdk
        functions = (
            "init",
            "set_init",
            "get_price",
            "get_trade_days",
            "get_history_constituents",
            "get_fundamentals",
            "get_last_tick",
        )
        signatures = {
            name: _signature(getattr(sdk, name, None))
            for name in functions
        }
        raw_index = adapter.read_history_constituents(args.index_id, snapshot_date)
        index_schema = _sample_payload(raw_index)
        trade_days = adapter.read_trade_days(calendar_start, calendar_end)
        payload = {
            "status": "PASS" if index_schema["status"] == "PASS" else "UNKNOWN",
            "sdk_module": getattr(sdk, "__name__", type(sdk).__name__),
            "sdk_module_file": getattr(sdk, "__file__", None),
            "sdk_signatures": signatures,
            "native_init_error": (
                None if adapter.native_init_error is None
                else f"{type(adapter.native_init_error).__name__}: {adapter.native_init_error}"
            ),
            "online_endpoint": adapter.online_endpoint,
            "index_snapshot": {
                "index_id": args.index_id,
                "requested_date": snapshot_date.isoformat(),
                "schema": index_schema,
            },
            "trading_calendar": {
                "start": calendar_start,
                "end": calendar_end,
                "status": "PASS" if trade_days else "UNKNOWN",
                "session_count": len(trade_days),
                "first_session": trade_days[0].isoformat() if trade_days else None,
                "last_session": trade_days[-1].isoformat() if trade_days else None,
            },
            "weight_unit_decision": "NOT_INFERRED",
            "symbol_field_decision": "NOT_INFERRED",
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".part")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        if not callable(getattr(sdk, "get_history_constituents", None)):
            return 4
        return 0 if index_schema["status"] == "PASS" and trade_days else 4
    except Exception as exc:
        print(
            f"remote SDK contract probe failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
