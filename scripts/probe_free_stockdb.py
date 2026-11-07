"""Run locally beside the installed free-stockdb Python SDK."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from etf_backtesting.adapters.free_stockdb import FreeStockDBAdapter, probe_universe


ETF_SYMBOLS = ("510300", "510880", "513020", "159928", "159611")


def emit_report(report: dict[str, Any], output: str | None) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
        print(f"Probe report written to {path}")
    else:
        print(rendered)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe local free-stockdb ETF history coverage.")
    parser.add_argument(
        "--output",
        help="Optional JSON output path; defaults to stdout. Local reports should stay out of Git.",
    )
    args = parser.parse_args()

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
        emit_report(report, args.output)
        return 2

    emit_report(report, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
