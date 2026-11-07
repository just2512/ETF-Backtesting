"""Inspect the exact installed remote stock_sdk contract without reading local market data."""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping


def _signature(value: Any) -> str | None:
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return None


def _sample_payload(raw: Any) -> dict[str, object]:
    """Describe raw provider columns and sample rows without guessing their meaning."""
    if raw is None:
        return {"status": "MISSING", "row_count": 0, "columns": [], "sample_rows": []}

    columns = getattr(raw, "columns", None)
    if columns is not None:
        names = [str(item) for item in list(columns)]
        row_count = len(raw)
        sample_rows = raw.head(5).to_dict(orient="records")
        dtypes = {str(key): str(value) for key, value in raw.dtypes.items()}
        source_rows = raw.to_dict(orient="records")
        index_name = getattr(raw.index, "name", None)
        index_sample = [str(value) for value in list(raw.index[:5])]
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
            source_rows = [
                dict(zip(names, row, strict=True))
                for row in zip(*values, strict=True)
            ]
        else:
            source_rows = [dict(raw)]
        row_count = len(source_rows)
        sample_rows = source_rows[:5]
        dtypes = {}
        index_name = None
        index_sample = []
    elif isinstance(raw, (list, tuple)):
        row_count = len(raw)
        sample_rows = list(raw[:5])
        first = raw[0] if raw else None
        names = list(first) if isinstance(first, Mapping) else []
        source_rows = sample_rows if names else []
        dtypes = {}
        index_name = None
        index_sample = []
    else:
        return {
            "status": "UNKNOWN",
            "python_type": type(raw).__name__,
            "repr": repr(raw)[:2000],
            "columns": [],
            "sample_rows": [],
        }

    numeric_summary: dict[str, dict[str, str | int]] = {}
    if source_rows and all(isinstance(row, Mapping) for row in source_rows):
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
        "status": "PASS" if row_count and names else "MISSING" if not row_count else "UNKNOWN",
        "python_type": type(raw).__name__,
        "row_count": row_count,
        "columns": names,
        "dtypes": dtypes,
        "index_name": index_name,
        "index_sample": index_sample,
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
        module_name = os.getenv("STOCKSDK_MODULE", "stock_sdk")
        sdk = importlib.import_module(module_name)
        host = os.getenv("STOCKSDK_HOST")
        port = int(os.getenv("STOCKSDK_PORT", "7899"))
        online_endpoint = os.getenv("STOCKSDK_ONLINE_ENDPOINT")
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

        native_init_error = None
        native_init = getattr(sdk, "init", None)
        if callable(native_init):
            try:
                native_init(host, port)
            except Exception as exc:
                native_init_error = f"{type(exc).__name__}: {exc}"
        else:
            native_init_error = "MISSING: init(host, port)"

        online_init_error = None
        online_init = getattr(sdk, "set_init", None)
        if callable(online_init) and online_endpoint:
            try:
                online_init(online_endpoint)
            except Exception as exc:
                online_init_error = f"{type(exc).__name__}: {exc}"
        else:
            online_init_error = "MISSING: set_init() or STOCKSDK_ONLINE_ENDPOINT"

        history_getter = getattr(sdk, "get_history_constituents", None)
        if callable(history_getter) and online_init_error is None:
            try:
                raw_index = history_getter(args.index_id, date=snapshot_date.isoformat())
                index_schema = _sample_payload(raw_index)
            except Exception as exc:
                index_schema = {
                    "status": "UNKNOWN",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "columns": [],
                    "sample_rows": [],
                }
        else:
            index_schema = {
                "status": "MISSING",
                "error": "get_history_constituents() or online initialization unavailable",
                "columns": [],
                "sample_rows": [],
            }

        calendar_getter = getattr(sdk, "get_trade_days", None)
        if callable(calendar_getter) and online_init_error is None:
            try:
                trade_days = calendar_getter(
                    start_date=calendar_start,
                    end_date=calendar_end,
                )
                trade_days = list(trade_days or [])
                calendar_status = "PASS" if trade_days else "UNKNOWN"
                calendar = {
                    "start": calendar_start,
                    "end": calendar_end,
                    "status": calendar_status,
                    "session_count": len(trade_days),
                    "first_session": str(trade_days[0]) if trade_days else None,
                    "last_session": str(trade_days[-1]) if trade_days else None,
                }
            except Exception as exc:
                calendar = {
                    "start": calendar_start,
                    "end": calendar_end,
                    "status": "UNKNOWN",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
        else:
            calendar = {
                "start": calendar_start,
                "end": calendar_end,
                "status": "MISSING",
                "error": "get_trade_days() or online initialization unavailable",
            }

        payload = {
            "status": (
                "PASS"
                if online_init_error is None
                and index_schema["status"] == "PASS"
                and calendar["status"] == "PASS"
                else "UNKNOWN"
            ),
            "sdk_module": module_name,
            "sdk_module_file": getattr(sdk, "__file__", None),
            "sdk_signatures": signatures,
            "native_init_status": "PASS" if native_init_error is None else "UNKNOWN",
            "native_init_error": native_init_error,
            "online_init_status": "PASS" if online_init_error is None else "REJECT",
            "online_init_error": online_init_error,
            "index_snapshot": {
                "index_id": args.index_id,
                "requested_date": snapshot_date.isoformat(),
                "schema": index_schema,
            },
            "trading_calendar": calendar,
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
        return 0 if payload["status"] == "PASS" else 4
    except Exception as exc:
        print(
            f"remote SDK contract probe failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
