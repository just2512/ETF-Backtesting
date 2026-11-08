"""Export five ETF histories from the local free-stockdb service.

This command is deliberately local-only: it never initializes or calls NovAPI.
It writes unadjusted OHLCV CSVs and a SHA-256 manifest under an ignored data path.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from etf_backtesting.adapters.free_stockdb import FreeStockDBAdapter
from etf_backtesting.data.audit import audit_daily_records, summarize_findings


DEFAULT_SYMBOLS = ("510300", "510880", "513020", "159928", "159611")
LISTING_DATES = {
    "510300": date(2012, 5, 28),
    "510880": date(2007, 1, 18),
    "513020": date(2022, 2, 8),
    "159928": date(2013, 9, 16),
    "159611": date(2022, 1, 7),
}
FIELDS = (
    "symbol", "trade_date", "open", "high", "low", "close",
    "volume", "amount", "trade_status", "source",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def export_local_snapshot(
    adapter: FreeStockDBAdapter,
    symbols: list[str],
    output: Path,
    start: str,
    end: str,
) -> dict[str, Any]:
    if len(start) != 8 or not start.isdigit() or len(end) != 8 or not end.isdigit():
        raise ValueError("start/end must use YYYYMMDD")
    if start > end:
        raise ValueError("start must not be later than end")

    results: list[dict[str, Any]] = []
    output.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        try:
            bars = adapter.read_daily_bars(symbol, start, end)
            if not bars:
                results.append({
                    "symbol": symbol, "status": "MISSING", "daily_bar_count": 0,
                    "error": "local StockDB returned no daily bars",
                    "history_coverage_status": "MISSING",
                    "calendar_completeness": "UNKNOWN",
                })
                continue

            raw = [{
                "date": bar.trade_date.strftime("%Y%m%d"),
                "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close,
                "volume": bar.volume, "amount": bar.amount,
            } for bar in bars]
            findings = audit_daily_records(symbol, raw)
            audit = summarize_findings(findings)
            path = output / f"{symbol}.csv"
            temporary = path.with_suffix(".csv.part")
            with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
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
                        "source": bar.source or FreeStockDBAdapter.SOURCE_NAME,
                    })
            temporary.replace(path)

            expected = LISTING_DATES.get(symbol)
            requested_start = date(int(start[:4]), int(start[4:6]), int(start[6:8]))
            if expected is not None and requested_start <= expected:
                if bars[0].trade_date == expected:
                    first_date_status = "PASS"
                elif bars[0].trade_date > expected:
                    first_date_status = "UNKNOWN"
                else:
                    first_date_status = "REJECT"
            else:
                first_date_status = "NOT_CONFIGURED"

            factors = adapter.read_adjustment_factors(symbol)
            results.append({
                "symbol": symbol,
                "status": "REJECT" if audit["overall_status"] == "REJECT" else "PASS",
                "file": path.as_posix(),
                "sha256": sha256(path),
                "daily_bar_count": len(bars),
                "first_date": bars[0].trade_date.isoformat(),
                "last_date": bars[-1].trade_date.isoformat(),
                "expected_listing_date": expected.isoformat() if expected else None,
                "first_date_status": first_date_status,
                "history_coverage_status": (
                    "REJECT" if first_date_status == "REJECT"
                    else "PASS" if first_date_status == "PASS"
                    else "UNKNOWN"
                ),
                "calendar_completeness": "UNKNOWN",
                "data_quality": audit,
                "adjustment_factor_count": len(factors),
                "adjustment_factor_status": "UNKNOWN" if factors else "MISSING",
                "cash_dividend_status": "MISSING",
                "historical_index_constituent_status": "MISSING",
            })
        except Exception as exc:
            results.append({
                "symbol": symbol,
                "status": "UNKNOWN",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "daily_bar_count": 0,
                "history_coverage_status": "UNKNOWN",
                "calendar_completeness": "UNKNOWN",
            })

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "local-free-stockdb",
        "transport": "127.0.0.1-or-configured-local-service",
        "price_basis": "UNADJUSTED",
        "fq": None,
        "frequency": "daily",
        "requested_start": start,
        "requested_end": end,
        "calendar_source": None,
        "calendar_status": "UNKNOWN",
        "calendar_completeness": "UNKNOWN",
        "cash_dividend_status": "MISSING",
        "historical_index_constituent_status": "MISSING",
        "symbols": results,
        "warning": (
            "Observed first/last dates and row counts do not prove full coverage. "
            "No authoritative calendar, suspension status, cash-dividend event set, "
            "or historical index constituent source is inferred by this local exporter."
        ),
    }
    atomic_json(output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--start", default="20000101")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--output", default="data/snapshots/local-stockdb")
    args = parser.parse_args()

    try:
        adapter = FreeStockDBAdapter.from_environment()
        manifest = export_local_snapshot(
            adapter, args.symbols, Path(args.output), args.start, args.end
        )
    except Exception as exc:
        print(f"local snapshot export failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    statuses = [item.get("status") for item in manifest["symbols"]]
    if "REJECT" in statuses or any(
        item.get("history_coverage_status") == "REJECT" for item in manifest["symbols"]
    ):
        return 5
    if "MISSING" in statuses:
        return 3
    # Local StockDB has no authoritative calendar or event sources in this adapter.
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
