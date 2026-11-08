"""Export historical ETF bars from the remote online API into a hashed snapshot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from etf_backtesting.adapters.stock_sdk import StockSDKAdapter


RETRYABLE_REMOTE_ERRORS = (ConnectionError, TimeoutError, OSError)


def _retry_remote_call(operation: Any, attempts: int, delay_seconds: float) -> tuple[Any, int, list[dict[str, str]]]:
    """Retry transient transport/provider failures without rewriting their identity."""
    if attempts < 1 or delay_seconds < 0:
        raise ValueError("attempts must be >= 1 and delay_seconds must be >= 0")
    errors: list[dict[str, str]] = []
    for attempt in range(1, attempts + 1):
        try:
            return operation(), attempt, errors
        except RETRYABLE_REMOTE_ERRORS as exc:
            errors.append({"attempt": str(attempt), "error_type": type(exc).__name__, "error": str(exc)})
            if attempt == attempts:
                raise
            time.sleep(delay_seconds * (2 ** (attempt - 1)))
    raise RuntimeError("unreachable retry state")


DEFAULT_SYMBOLS = ("510300", "510880", "513020", "159928", "159611")
DEFAULT_LISTING_DATES = {
    "510300": date(2012, 5, 28),
    "510880": date(2007, 1, 18),
    "513020": date(2022, 2, 8),
    "159928": date(2013, 9, 16),
    "159611": date(2022, 1, 7),
}
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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_calendar_gap_report(
    path: Path,
    gaps_by_symbol: dict[str, list[date]],
) -> str:
    """Write every missing exchange session without guessing suspension status."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("symbol", "trade_date", "classification", "reason"),
        )
        writer.writeheader()
        for symbol in sorted(gaps_by_symbol):
            for day in sorted(gaps_by_symbol[symbol]):
                writer.writerow({
                    "symbol": symbol,
                    "trade_date": day.isoformat(),
                    "classification": "UNCLASSIFIED",
                    "reason": (
                        "exchange calendar session has no daily bar; "
                        "suspension status was not supplied by the source"
                    ),
                })
    temporary.replace(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_snapshot(
    adapter: StockSDKAdapter,
    symbols: list[str],
    output_dir: Path,
    *,
    start: str = "20000101",
    end: str | None = None,
    expected_first_dates: dict[str, date] | None = None,
    retry_attempts: int = 3,
    retry_delay_seconds: float = 1.0,
) -> dict[str, object]:
    """Export one symbol per request over an explicit full-history date window."""
    if len(start) != 8 or not start.isdigit():
        raise ValueError("start must use YYYYMMDD")
    if end is None:
        end = date.today().strftime("%Y%m%d")
    if len(end) != 8 or not end.isdigit() or start > end:
        raise ValueError("end must use YYYYMMDD and must not precede start")
    expected_dates = (
        DEFAULT_LISTING_DATES if expected_first_dates is None else expected_first_dates
    )
    requested_start = date(int(start[:4]), int(start[4:6]), int(start[6:8]))
    requested_end = date(int(end[:4]), int(end[4:6]), int(end[6:8]))
    symbol_results: list[dict[str, object]] = []
    all_bars: dict[str, list[Any]] = {}
    for symbol in symbols:
        try:
            bars, attempts_used, retry_errors = _retry_remote_call(
                lambda: adapter.read_daily_bars(symbol, start, end),
                retry_attempts,
                retry_delay_seconds,
            )
            if not bars:
                symbol_results.append({
                    "symbol": symbol,
                    "status": "MISSING",
                    "error": "remote history API returned no daily bars",
                    "attempts": attempts_used,
                    "retry_errors": retry_errors,
                    "daily_bar_count": 0,
                    "first_date": None,
                    "last_date": None,
                    "calendar_completeness": "UNKNOWN",
                    "unclassified_calendar_sessions": [],
                })
                continue
            bars = sorted(bars, key=lambda bar: bar.trade_date)
            all_bars[symbol] = bars
            expected_first = expected_dates.get(symbol)
            if expected_first is not None and requested_start > expected_first:
                expected_first = None
            first_date_status = "NOT_CONFIGURED"
            if expected_first is not None:
                if bars[0].trade_date == expected_first:
                    first_date_status = "PASS"
                elif bars[0].trade_date > expected_first:
                    first_date_status = "UNKNOWN"
                else:
                    first_date_status = "REJECT"
            file_path = output_dir / f"{symbol}.csv"
            digest = _write_symbol_csv(file_path, symbol, bars)
            symbol_results.append({
                "symbol": symbol,
                "status": "PASS",
                "attempts": attempts_used,
                "retry_errors": retry_errors,
                "file": file_path.as_posix(),
                "sha256": digest,
                "daily_bar_count": len(bars),
                "first_date": bars[0].trade_date.isoformat(),
                "last_date": bars[-1].trade_date.isoformat(),
                "requested_start": start,
                "requested_end": end,
                "expected_first_date": (
                    expected_first.isoformat() if expected_first is not None else None
                ),
                "first_date_status": first_date_status,
                "history_coverage_status": (
                    "REJECT" if first_date_status == "REJECT"
                    else "PASS" if first_date_status == "PASS"
                    else "UNKNOWN"
                ),
                "calendar_completeness": "UNKNOWN",
                "unclassified_calendar_sessions": [],
            })
        except Exception as exc:
            symbol_results.append({
                "symbol": symbol,
                "attempts": retry_attempts if isinstance(exc, RETRYABLE_REMOTE_ERRORS) else 1,
                "retry_errors": [
                    {"attempt": str(i + 1), "error_type": type(exc).__name__, "error": str(exc)}
                    for i in range(retry_attempts if isinstance(exc, RETRYABLE_REMOTE_ERRORS) else 1)
                ],
                "status": "UNKNOWN",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "daily_bar_count": 0,
                "first_date": None,
                "last_date": None,
                "calendar_completeness": "UNKNOWN",
                "unclassified_calendar_sessions": [],
            })

    populated = list(all_bars.values())
    calendar_error: dict[str, str] | None = None
    if populated:
        calendar_start = start
        calendar_end = end
        try:
            trade_days, calendar_attempts, calendar_retry_errors = _retry_remote_call(
                lambda: adapter.read_trade_days(calendar_start, calendar_end),
                retry_attempts,
                retry_delay_seconds,
            )
            if not trade_days:
                calendar_error = {
                    "type": "EmptyCalendar",
                    "message": "get_trade_days returned no sessions for a non-empty price range",
                }
        except Exception as exc:
            trade_days = []
            calendar_error = {"type": type(exc).__name__, "message": str(exc), "attempts": retry_attempts if isinstance(exc, RETRYABLE_REMOTE_ERRORS) else 1}
    else:
        trade_days = []
        calendar_error = {
            "type": "Unavailable",
            "message": "No successful price series exists from which to request a calendar",
        }

    gaps_by_symbol: dict[str, list[date]] = {}
    for result in symbol_results:
        symbol = str(result["symbol"])
        bars = all_bars.get(symbol, [])
        if not bars:
            continue
        if calendar_error is not None:
            result["calendar_completeness"] = "UNKNOWN"
            result["calendar_error"] = calendar_error
            continue
        expected = [
            day for day in trade_days
            if bars[0].trade_date <= day <= requested_end
        ]
        observed = {bar.trade_date for bar in bars}
        gaps = sorted(set(expected) - observed)
        gaps_by_symbol[symbol] = gaps
        result["calendar_completeness"] = "PASS" if not gaps else "UNKNOWN"
        if result.get("first_date_status") in ("UNKNOWN", "REJECT"):
            result["history_coverage_status"] = result["first_date_status"]
        # A missing bar on a trading day may be a suspension or a data defect.
        # Without an authoritative per-symbol status endpoint, do not classify it.
        result["unclassified_calendar_sessions"] = [
            day.isoformat() for day in gaps
        ]

    gap_report_path = output_dir / "calendar_gaps.csv"
    gap_report_sha256 = _write_calendar_gap_report(gap_report_path, gaps_by_symbol)
    manifest: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_start": start,
        "requested_end": end,
        "source": StockSDKAdapter.SOURCE_NAME,
        "history_api": adapter.history_api,
        "price_basis": "UNADJUSTED",
        "fq": None,
        "frequency": "daily",
        "calendar_source": "get_trade_days",
        "calendar_trade_day_count": len(trade_days),
        "calendar_status": "PASS" if calendar_error is None else "UNKNOWN",\n        "calendar_attempts": locals().get("calendar_attempts", 0),\n        "calendar_retry_errors": locals().get("calendar_retry_errors", []),
        "calendar_error": calendar_error,
        "calendar_gap_report": {
            "file": gap_report_path.as_posix(),
            "sha256": gap_report_sha256,
            "row_count": sum(len(value) for value in gaps_by_symbol.values()),
            "classification": "UNCLASSIFIED",
        },
        "symbols": symbol_results,
    }
    _atomic_write(
        output_dir / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--start", default="20000101")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"))\n    parser.add_argument("--retry-attempts", type=int, default=3)\n    parser.add_argument("--retry-delay-seconds", type=float, default=1.0)
    parser.add_argument(
        "--output",
        default="data/snapshots/remote-stock-sdk",
        help="snapshot directory (default: data/snapshots/remote-stock-sdk)",
    )
    args = parser.parse_args()

    try:
        adapter = StockSDKAdapter.from_environment()
        manifest = export_snapshot(
            adapter, args.symbols, Path(args.output),
            start=args.start, end=args.end,\n            retry_attempts=args.retry_attempts,\n            retry_delay_seconds=args.retry_delay_seconds,\n        )
    except Exception as exc:
        print(
            f"remote snapshot export failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 4

    results = manifest["symbols"]
    missing = any(item["status"] == "MISSING" for item in results)
    rejected = any(
        item["status"] == "REJECT" or item.get("history_coverage_status") == "REJECT"
        for item in results
    )
    unknown = any(
        item["status"] == "UNKNOWN"
        or item["calendar_completeness"] != "PASS"
        or item.get("history_coverage_status") == "UNKNOWN"
        for item in results
    ) or manifest["calendar_status"] != "PASS"
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 5 if rejected else 3 if missing else 4 if unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
