"""Probe NovAPI's real historical index response schema without guessing fields or units."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from etf_backtesting.adapters.stock_sdk import StockSDKAdapter


def plain(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict("records")
        except TypeError:
            return value.to_dict()
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def describe(value: Any) -> dict[str, Any]:
    converted = plain(value)
    if isinstance(converted, list):
        return {
            "python_type": type(value).__name__,
            "row_count": len(converted),
            "columns": sorted(converted[0]) if converted and isinstance(converted[0], dict) else [],
            "sample": converted[:3],
        }
    if isinstance(converted, dict):
        return {
            "python_type": type(value).__name__,
            "keys": list(converted)[:30],
            "row_count": len(converted),
            "sample": dict(list(converted.items())[:5]),
        }
    return {"python_type": type(value).__name__, "value": converted}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-id", action="append", default=[])
    parser.add_argument("--dates", nargs="+", default=["2020-06-30", "2026-11-06"])
    parser.add_argument("--output", default="reports/novapi/index-api-contract.json")
    args = parser.parse_args()

    adapter = StockSDKAdapter.from_environment()
    report: dict[str, Any] = {
        "source": "NovAPI",
        "endpoint": adapter.online_endpoint,
        "dates": args.dates,
        "indices": [],
    }

    securities_api = getattr(adapter.sdk, "get_all_securities", None)
    if callable(securities_api):
        try:
            securities = securities_api(types=["index"], date=args.dates[-1])
            report["index_security_catalog"] = describe(securities)
        except Exception as exc:
            report["index_security_catalog_error"] = {
                "error_type": type(exc).__name__, "error": str(exc)
            }
    else:
        report["index_security_catalog_error"] = {
            "error_type": "MissingAPI",
            "error": "get_all_securities is not exposed by this SDK build",
        }

    index_ids = args.index_id or ["000300.XSHG"]
    failed = False
    for index_id in index_ids:
        entry: dict[str, Any] = {"index_id": index_id, "snapshots": []}
        for date_text in args.dates:
            snapshot_date = date.fromisoformat(date_text)
            try:
                raw = adapter.read_history_constituents(index_id, snapshot_date)
                stocks = raw.get("stocks") if isinstance(raw, Mapping) else None
                weights = raw.get("weights") if isinstance(raw, Mapping) else None
                entry["snapshots"].append({
                    "date": date_text,
                    "stocks": describe(stocks),
                    "weights": describe(weights),
                })
            except Exception as exc:
                failed = True
                entry["snapshots"].append({
                    "date": date_text,
                    "status": "UNKNOWN",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
        report["indices"].append(entry)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 4 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
