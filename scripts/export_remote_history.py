"""Export historical ETF bars from the remote online API into a hashed snapshot.

This script never reads local LevelDB data. Output is written under data/snapshots/,
which is excluded from version control.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from etf_backtesting.adapters.stock_sdk import StockSDKAdapter


DEFAULT_SYMBOLS = ("510300", "510880", "513020", "159928", "159611")
BAR_FIELDS = (
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "trade_status",
    "source",
)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(content, encoding="utf-8", newline="")
    temporary.replace(path)


def _write_symbol_csv(path: Path, symbol: str, bars: list[Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BAR_FIELDS)
        writer.writeheader()
        for bar in bars:
            writer.writerow({
                "symbol": symbol,
                "trade_date": bar.trade_date.isoformat(),
                "open": format(bar.open, ".12g"),
                "high": format(bar.high, ".12g"),
                "low": format(bar.low, ".12g"),
                "close": format(bar.close, ".12g"),
                "volume": "" if bar.volume is None else format(bar.volume, ".12g"),
                "amount": "" if bar.amount is None else format(bar.amount, ".12g"),
                "trade_status": bar.trade_status,
                "source": bar.source or StockSDKAdapter.SOURCE_NAME,
            })
    temporary.replace(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def export_snapshot(
    adapter: StockSDKAdapter,
    symbols: list[str],
    output_dir: Path,
) -> dict[str, object]:
    symbol_results: list[dict[str, object]] = []
    all_bars: dict[str, list[Any]] = {}
    for symbol in symbols:
        bars = adapter.read_daily_bars(symbol)
        if not bars:
            symbol_results.append({
                "symbol": symbol,
                "status": "MISSING",
                "daily_bar_count": 0,
                "first_date": None,
                "last_date": None,
            })
            continue
        all_bars[symbol] = bars
        file_path = output_dir / f"{symbol}.csv"
        digest = _write_symbol_csv(file_path, symbol, bars)
        symbol_results.append({
            "symbol": symbol,
            "status": "PASS",
            "file": file_path.as_posix(),
            "sha256": digest,
            "daily_bar_count": len(bars),
            "first_date": bars[0].trade_date.isoformat(),
            "last_date": bars[-1].trade_date.isoformat(),
        })

    populated = list(all_bars.values())
    if populated:
        calendar_start = min(bars[0].trade_date for bars in populated).strftime("%Y%m%d")
        calendar_end = max(bars[-1].trade_date for bars in populated).strftime("%Y%m%d")
        trade_days = adapter.read_trade_days(calendar_start, calendar_end)
    else:
        trade_days = []

    for result in symbol_results:
        symbol = str(result["symbol"])
        bars = all_bars.get(symbol, [])
        if not bars:
            result["calendar_completeness"] = "UNKNOWN"
            result["unclassified_calendar_sessions"] = []
            continue
        expected = [
            day for day in trade_days
            if bars[0].trade_date <= day <= bars[-1].trade_date
        ]
        observed = {bar.trade_date for bar in bars}
        gaps = sorted(set(expected) - observed)
        result["calendar_completeness"] = "PASS" if not gaps else "UNKNOWN"
        # A missing bar on a trading day may be a suspension or a data defect.
        # Without an authoritative per-symbol status endpoint, do not classify it.
        result["unclassified_calendar_sessions"] = [
            day.isoformat() for day in gaps
        ]

    manifest: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": StockSDKAdapter.SOURCE_NAME,
        "price_basis": "UNADJUSTED",
        "fq": None,
        "frequency": "daily",
        "calendar_source": "get_trade_days",
        "calendar_trade_day_count": len(trade_days),
        "symbols": symbol_results,
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    _atomic_write(output_dir / "manifest.json", manifest_text)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--output",
        default="data/snapshots/remote-stock-sdk",
        help="snapshot directory (default: data/snapshots/remote-stock-sdk)",
    )
    args = parser.parse_args()

    try:
        adapter = StockSDKAdapter.from_environment()
        manifest = export_snapshot(adapter, args.symbols, Path(args.output))
    except Exception as exc:
        print(f"remote snapshot export failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

    results = manifest["symbols"]
    missing = any(item["status"] != "PASS" for item in results)
    unknown_calendar = any(item["calendar_completeness"] != "PASS" for item in results)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 3 if missing else 4 if unknown_calendar else 0


if __name__ == "__main__":
    raise SystemExit(main())
