"""Probe the remote stock_sdk data source from the user's runtime."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from etf_backtesting.adapters.stock_sdk import StockSDKAdapter


DEFAULT_SYMBOLS = ("510300", "510880", "513020", "159928", "159611")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--output",
        default="reports/audit/stock_sdk_probe.json",
        help="JSON output path (default: reports/audit/stock_sdk_probe.json)",
    )
    args = parser.parse_args()

    try:
        adapter = StockSDKAdapter.from_environment()
        report = adapter.probe_universe(args.symbols)
    except Exception as exc:
        print(f"stock_sdk initialization/probe failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

    statuses = [str(item.get("daily_bar_status", "UNKNOWN")) for item in report["symbols"]]
    if "REJECT" in statuses:
        coverage_status = "REJECT"
        exit_code = 2
    elif "MISSING" in statuses:
        coverage_status = "MISSING"
        exit_code = 3
    elif "UNKNOWN" in statuses:
        coverage_status = "UNKNOWN"
        exit_code = 4
    else:
        coverage_status = "PASS"
        exit_code = 0

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_status": coverage_status,
        "calendar_completeness": "UNKNOWN",
        **report,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "coverage_status": coverage_status,
        "output": str(destination),
        "symbols": [
            {
                "symbol": item["symbol"],
                "daily_bar_status": item.get("daily_bar_status"),
                "daily_bar_count": item.get("daily_bar_count"),
                "first_date": item.get("first_date"),
                "last_date": item.get("last_date"),
                "calendar_completeness": item.get("calendar_completeness", "UNKNOWN"),
            }
            for item in report["symbols"]
        ],
    }, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
