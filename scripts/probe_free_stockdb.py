"""Run locally beside the installed free-stockdb Python SDK."""

from __future__ import annotations

import json
import sys

from etf_backtesting.adapters.free_stockdb import FreeStockDBAdapter, probe_universe


ETF_SYMBOLS = ("510300", "510880", "513020", "159928", "159611")


def main() -> int:
    try:
        adapter = FreeStockDBAdapter.from_environment()
        report = probe_universe(adapter, ETF_SYMBOLS)
    except Exception as exc:  # local SDK and service errors must be visible in the report
        report = {
            "source": "free-stockdb",
            "connection_status": "UNKNOWN",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
