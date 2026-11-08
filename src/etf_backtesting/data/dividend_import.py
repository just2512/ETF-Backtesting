"""Load official ETF dividend events with explicit per-symbol source coverage."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from etf_backtesting.engine.corporate_actions import ETFDividend


DEFAULT_LISTING_DATES = {
    "510300": date(2012, 5, 28),
    "510880": date(2007, 1, 18),
    "513020": date(2022, 2, 8),
    "159928": date(2013, 9, 16),
    "159611": date(2022, 1, 7),
}


@dataclass(frozen=True, slots=True)
class DividendCoverage:
    symbol: str
    coverage_start: date
    coverage_end: date
    source_name: str
    source_url: str


@dataclass(frozen=True, slots=True)
class DividendSnapshot:
    events: tuple[ETFDividend, ...]
    coverage: tuple[DividendCoverage, ...]
    coverage_start: date
    coverage_end: date
    symbols: tuple[str, ...]
    sha256: str


def _approved_https_url(url: str, approved_domains: set[str]) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and bool(host)
        and any(host == domain or host.endswith("." + domain) for domain in approved_domains)
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no CSV header")
        return [dict(row) for row in reader]


def load_dividend_snapshot(
    events_path: Path,
    coverage_path: Path,
    *,
    symbols: list[str],
    coverage_start: date,
    coverage_end: date,
    approved_domains: set[str],
    listing_dates: dict[str, date] | None = None,
) -> DividendSnapshot:
    """Validate complete source coverage and official event provenance.

    A symbol with no dividend rows is not treated as zero dividends unless its
    full requested interval has a separate coverage attestation.
    """
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("symbols must be non-empty and unique")
    if coverage_start > coverage_end:
        raise ValueError("coverage_start must not be after coverage_end")
    domains = {domain.lower().strip(".") for domain in approved_domains if domain.strip(".")}
    if not domains:
        raise ValueError("at least one approved official source domain is required")

    known_listing_dates = (
        DEFAULT_LISTING_DATES if listing_dates is None else listing_dates
    )
    coverage_rows = _read_csv(coverage_path)
    coverage_by_symbol: dict[str, DividendCoverage] = {}
    for row in coverage_rows:
        symbol = row.get("symbol", "").strip()
        if symbol not in symbols:
            raise ValueError(f"unexpected dividend coverage symbol: {symbol}")
        if symbol in coverage_by_symbol:
            raise ValueError(f"duplicate dividend coverage declaration: {symbol}")
        start = date.fromisoformat(row["coverage_start"])
        end = date.fromisoformat(row["coverage_end"])
        source_name = row.get("source_name", "").strip()
        source_url = row.get("source_url", "").strip()
        active_start = max(
            coverage_start,
            known_listing_dates.get(symbol, coverage_start),
        )
        if start > active_start or end < coverage_end:
            raise ValueError(
                "dividend coverage does not span the symbol's active requested interval "
                f"for {symbol}: required {active_start}..{coverage_end}, got {start}..{end}"
            )
        if not source_name or not _approved_https_url(source_url, domains):
            raise ValueError(f"unapproved or missing coverage source for {symbol}")
        coverage_by_symbol[symbol] = DividendCoverage(
            symbol, start, end, source_name, source_url
        )

    missing_coverage = sorted(set(symbols) - set(coverage_by_symbol))
    if missing_coverage:
        raise ValueError(f"missing official dividend coverage for symbols: {missing_coverage}")

    events: list[ETFDividend] = []
    seen: set[tuple[str, date, date, date]] = set()
    for row in _read_csv(events_path):
        symbol = row.get("symbol", "").strip()
        if symbol not in symbols:
            raise ValueError(f"unexpected dividend event symbol: {symbol}")
        ex_date = date.fromisoformat(row["ex_date"])
        record_date = date.fromisoformat(row["record_date"])
        pay_date = date.fromisoformat(row["pay_date"])
        announcement_date = date.fromisoformat(row["announcement_date"])
        active_start = max(
            coverage_start,
            known_listing_dates.get(symbol, coverage_start),
        )
        if not active_start <= ex_date <= coverage_end:
            raise ValueError(f"dividend ex-date outside the symbol's active covered interval for {symbol}")
        key = (symbol, ex_date, record_date, pay_date)
        if key in seen:
            raise ValueError(f"duplicate dividend event: {key}")
        seen.add(key)
        source_name = row.get("source_name", "").strip()
        source_url = row.get("source_url", "").strip()
        if not source_name or not _approved_https_url(source_url, domains):
            raise ValueError(f"unapproved or missing event source for {symbol}")
        try:
            cash_per_share = Decimal(row["cash_per_share"])
        except (InvalidOperation, KeyError) as exc:
            raise ValueError(f"invalid cash_per_share for {symbol}") from exc
        if not cash_per_share.is_finite() or cash_per_share <= 0:
            raise ValueError(f"cash_per_share must be finite and positive for {symbol}")
        events.append(ETFDividend(
            symbol=symbol,
            ex_date=ex_date,
            record_date=record_date,
            pay_date=pay_date,
            cash_per_share=cash_per_share,
            announcement_date=announcement_date,
            source_name=source_name,
            source_url=source_url,
        ))

    events.sort(key=lambda item: (item.ex_date, item.symbol, item.pay_date))
    coverage = tuple(coverage_by_symbol[symbol] for symbol in sorted(coverage_by_symbol))
    digest = hashlib.sha256(
        events_path.read_bytes() + b"\0" + coverage_path.read_bytes()
    ).hexdigest()
    return DividendSnapshot(
        events=tuple(events),
        coverage=coverage,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        symbols=tuple(sorted(symbols)),
        sha256=digest,
    )


def write_dividend_manifest(snapshot: DividendSnapshot, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "PASS",
        "coverage_start": snapshot.coverage_start.isoformat(),
        "coverage_end": snapshot.coverage_end.isoformat(),
        "symbols": list(snapshot.symbols),
        "event_count": len(snapshot.events),
        "sha256": snapshot.sha256,
        "coverage": [
            {
                "symbol": item.symbol,
                "coverage_start": item.coverage_start.isoformat(),
                "coverage_end": item.coverage_end.isoformat(),
                "source_name": item.source_name,
                "source_url": item.source_url,
            }
            for item in snapshot.coverage
        ],
        "events": [
            {
                "symbol": item.symbol,
                "ex_date": item.ex_date.isoformat(),
                "record_date": item.record_date.isoformat(),
                "pay_date": item.pay_date.isoformat(),
                "cash_per_share": str(item.cash_per_share),
                "announcement_date": item.announcement_date.isoformat(),
                "source_name": item.source_name,
                "source_url": item.source_url,
            }
            for item in snapshot.events
        ],
    }
    temporary = output_path.with_suffix(output_path.suffix + ".part")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True)
    parser.add_argument("--coverage", required=True)
    parser.add_argument("--symbols", nargs="+", default=[
        "510300", "510880", "513020", "159928", "159611"
    ])
    parser.add_argument("--coverage-start", required=True)
    parser.add_argument("--coverage-end", required=True)
    parser.add_argument("--approved-domain", nargs="+", required=True)
    parser.add_argument("--output", default="data/snapshots/dividends/manifest.json")
    args = parser.parse_args()
    try:
        snapshot = load_dividend_snapshot(
            Path(args.events),
            Path(args.coverage),
            symbols=args.symbols,
            coverage_start=date.fromisoformat(args.coverage_start),
            coverage_end=date.fromisoformat(args.coverage_end),
            approved_domains=set(args.approved_domain),
        )
        write_dividend_manifest(snapshot, Path(args.output))
        print(json.dumps({
            "status": "PASS",
            "event_count": len(snapshot.events),
            "symbols": list(snapshot.symbols),
            "coverage_start": snapshot.coverage_start.isoformat(),
            "coverage_end": snapshot.coverage_end.isoformat(),
            "sha256": snapshot.sha256,
            "manifest": args.output,
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"dividend import failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
