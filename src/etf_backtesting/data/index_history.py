"""Strict point-in-time index constituent snapshot normalization and export."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, Mapping


RETRYABLE_REMOTE_ERRORS = (ConnectionError, TimeoutError, OSError)


def _retry_remote_call(operation: Any, attempts: int, delay_seconds: float) -> tuple[Any, int, list[dict[str, str]]]:
    """Retry transient transport/provider failures while retaining exact errors."""
    if attempts < 1 or delay_seconds < 0:
        raise ValueError("attempts must be >= 1 and delay_seconds must be >= 0")
    errors: list[dict[str, str]] = []
    for attempt in range(1, attempts + 1):
        try:
            return operation(), attempt, errors
        except RETRYABLE_REMOTE_ERRORS as exc:
            errors.append({"attempt": str(attempt), "error_type": type(exc).__name__, "error": str(exc)})
            if attempt == attempts:
                setattr(exc, "retry_errors", errors)
                setattr(exc, "retry_attempts", attempt)
                raise
            time.sleep(delay_seconds * (2 ** (attempt - 1)))
    raise RuntimeError("unreachable retry state")


WeightScale = Literal["fraction", "percent"]


@dataclass(frozen=True, slots=True)
class IndexWeightSnapshotRow:
    index_id: str
    snapshot_date: date
    constituent_symbol: str
    weight_fraction: Decimal
    source: str = "stock-sdk-online"


@dataclass(frozen=True, slots=True)
class NormalizedIndexSnapshot:
    index_id: str
    snapshot_date: date
    rows: tuple[IndexWeightSnapshotRow, ...]
    input_weight_scale: WeightScale
    source_weight_total: Decimal
    normalized_weight_total: Decimal
    weight_tolerance: Decimal


def _records_from_result(result: Any) -> list[Mapping[str, Any]]:
    if result is None:
        raise ValueError("historical constituent API returned no data")
    if callable(getattr(result, "reset_index", None)):
        result = result.reset_index()
    if callable(getattr(result, "to_dict", None)):
        try:
            result = result.to_dict("records")
        except TypeError:
            pass
    if isinstance(result, Mapping):
        keys = list(result)
        values = [result[key] for key in keys]
        if values and all(isinstance(value, (list, tuple)) for value in values):
            lengths = {len(value) for value in values}
            if len(lengths) != 1:
                raise ValueError("constituent columns have inconsistent lengths")
            result = [
                dict(zip(keys, row, strict=True))
                for row in zip(*values, strict=True)
            ]
        else:
            result = [result]
    if not isinstance(result, (list, tuple)) or not result:
        raise ValueError("historical constituent response must contain records")
    if any(not isinstance(row, Mapping) for row in result):
        raise TypeError("every historical constituent row must be a mapping")
    return [dict(row) for row in result]


def _extract_stock_codes(raw: Any, symbol_field: str) -> list[str]:
    if raw is None:
        raise ValueError("historical index stocks API returned no data")
    if callable(getattr(raw, "reset_index", None)):
        raw = raw.reset_index()
    columns = getattr(raw, "columns", None)
    if columns is not None:
        names = [str(item) for item in list(columns)]
        if symbol_field in names:
            values = raw[symbol_field].tolist()
        elif len(names) == 1:
            values = raw[names[0]].tolist()
        elif getattr(getattr(raw, "index", None), "name", None) == symbol_field:
            values = list(raw.index)
        else:
            raise ValueError(
                f"cannot identify index stock code column; available fields: {names}"
            )
    elif isinstance(raw, Mapping):
        if symbol_field in raw:
            values = raw[symbol_field]
        else:
            raise ValueError(
                f"index stocks mapping must contain the configured field {symbol_field!r}"
            )
    elif isinstance(raw, (list, tuple)):
        if all(isinstance(item, (str, int)) for item in raw):
            values = raw
        elif all(isinstance(item, Mapping) for item in raw):
            values = [item.get(symbol_field) for item in raw]
        else:
            raise TypeError("index stocks response must be codes or records")
    else:
        raise TypeError("unsupported index stocks response type")

    codes = [str(value).strip().upper() for value in values]
    if not codes or any(not value for value in codes):
        raise ValueError("index stocks response contains no codes or empty codes")
    if len(codes) != len(set(codes)):
        raise ValueError("index stocks response contains duplicate codes")
    return codes


def _weight_records(
    raw: Any,
    symbol_field: str,
    weight_field: str,
) -> list[Mapping[str, Any]]:
    if isinstance(raw, Mapping) and symbol_field not in raw and weight_field not in raw:
        if raw and all(not isinstance(value, (Mapping, list, tuple)) for value in raw.values()):
            return [
                {symbol_field: symbol, weight_field: weight}
                for symbol, weight in raw.items()
            ]
    return _records_from_result(raw)


def _combine_separate_index_apis(
    raw: Mapping[str, Any],
    symbol_field: str,
    weight_field: str,
) -> list[Mapping[str, Any]]:
    stocks = _extract_stock_codes(raw["stocks"], symbol_field)
    weights = _weight_records(raw["weights"], symbol_field, weight_field)
    weight_by_symbol: dict[str, Any] = {}
    for position, row in enumerate(weights):
        symbol_value = row.get(symbol_field)
        weight_value = row.get(weight_field)
        if symbol_value is None or weight_value is None:
            raise ValueError(
                f"weight row {position} missing {symbol_field!r}/{weight_field!r}"
            )
        symbol = str(symbol_value).strip().upper()
        if symbol in weight_by_symbol:
            raise ValueError(f"duplicate index weight for {symbol}")
        weight_by_symbol[symbol] = weight_value
    missing = sorted(set(stocks) - set(weight_by_symbol))
    extra = sorted(set(weight_by_symbol) - set(stocks))
    if missing or extra:
        raise ValueError(
            f"index stocks/weights mismatch; missing_weights={missing}, extra_weights={extra}"
        )
    return [
        {symbol_field: symbol, weight_field: weight_by_symbol[symbol]}
        for symbol in stocks
    ]


def normalize_index_snapshot(
    raw: Any,
    index_id: str,
    snapshot_date: date,
    *,
    symbol_field: str,
    weight_field: str,
    weight_scale: WeightScale,
    weight_tolerance: Decimal = Decimal("0.005"),
    source: str = "stock-sdk-online",
) -> NormalizedIndexSnapshot:
    """Normalize only with caller-confirmed provider fields and weight units.

    We deliberately do not infer whether 0.25 means 25% or 0.25%, and do not
    renormalize incomplete constituent lists to 100%.
    """
    if not index_id or not symbol_field or not weight_field:
        raise ValueError("index_id, symbol_field, and weight_field are required")
    if weight_scale not in ("fraction", "percent"):
        raise ValueError("weight_scale must be explicitly 'fraction' or 'percent'")
    if weight_tolerance < 0:
        raise ValueError("weight_tolerance must not be negative")

    if isinstance(raw, Mapping) and "stocks" in raw and "weights" in raw:
        records = _combine_separate_index_apis(raw, symbol_field, weight_field)
    else:
        records = _records_from_result(raw)
    rows: list[IndexWeightSnapshotRow] = []
    seen: set[str] = set()
    source_total = Decimal("0")
    divisor = Decimal("100") if weight_scale == "percent" else Decimal("1")

    for position, record in enumerate(records):
        symbol_value = record.get(symbol_field)
        weight_value = record.get(weight_field)
        if symbol_value is None or weight_value is None:
            raise ValueError(
                f"row {position} missing required fields "
                f"{symbol_field!r}/{weight_field!r}"
            )
        symbol = str(symbol_value).strip().upper()
        if not symbol:
            raise ValueError(f"row {position} has an empty constituent symbol")
        if symbol in seen:
            raise ValueError(f"duplicate constituent symbol: {symbol}")
        seen.add(symbol)
        try:
            source_weight = Decimal(str(weight_value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"invalid weight for {symbol}: {weight_value!r}") from exc
        if not source_weight.is_finite() or source_weight <= 0:
            raise ValueError(f"weight for {symbol} must be finite and positive")
        weight = source_weight / divisor
        if weight > 1:
            raise ValueError(f"weight for {symbol} exceeds 100% after unit conversion")
        source_total += source_weight
        rows.append(IndexWeightSnapshotRow(
            index_id=index_id,
            snapshot_date=snapshot_date,
            constituent_symbol=symbol,
            weight_fraction=weight,
            source=source,
        ))

    normalized_total = sum((row.weight_fraction for row in rows), Decimal("0"))
    if abs(normalized_total - Decimal("1")) > weight_tolerance:
        raise ValueError(
            "constituent weights do not reconcile to 100%: "
            f"total={normalized_total}, tolerance={weight_tolerance}; "
            "do not auto-normalize a potentially incomplete provider response"
        )
    return NormalizedIndexSnapshot(
        index_id=index_id,
        snapshot_date=snapshot_date,
        rows=tuple(sorted(rows, key=lambda row: row.constituent_symbol)),
        input_weight_scale=weight_scale,
        source_weight_total=source_total,
        normalized_weight_total=normalized_total,
        weight_tolerance=weight_tolerance,
    )


def export_index_snapshots(
    adapter: Any,
    index_id: str,
    dates: list[date],
    *,
    symbol_field: str,
    weight_field: str,
    weight_scale: WeightScale,
    output_dir: Path,
    weight_tolerance: Decimal = Decimal("0.005"),
    retry_attempts: int = 3,
    retry_delay_seconds: float = 1.0,
) -> dict[str, object]:
    """Fetch each as-of snapshot independently and retain failures in the manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    successful_snapshots: dict[date, dict[str, Decimal]] = {}
    for snapshot_date in dates:
        try:
            raw, attempts_used, retry_errors = _retry_remote_call(
                lambda: adapter.read_history_constituents(index_id, snapshot_date),
                retry_attempts,
                retry_delay_seconds,
            )
            snapshot = normalize_index_snapshot(
                raw,
                index_id,
                snapshot_date,
                symbol_field=symbol_field,
                weight_field=weight_field,
                weight_scale=weight_scale,
                weight_tolerance=weight_tolerance,
            )
            successful_snapshots[snapshot_date] = {
                row.constituent_symbol: row.weight_fraction for row in snapshot.rows
            }
            file_path = output_dir / f"{index_id.replace('.', '_')}_{snapshot_date.isoformat()}.csv"
            temporary = file_path.with_suffix(".csv.part")
            with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "index_id", "snapshot_date", "constituent_symbol",
                        "weight_fraction", "source",
                    ),
                )
                writer.writeheader()
                for row in snapshot.rows:
                    writer.writerow({
                        "index_id": row.index_id,
                        "snapshot_date": row.snapshot_date.isoformat(),
                        "constituent_symbol": row.constituent_symbol,
                        "weight_fraction": str(row.weight_fraction),
                        "source": row.source,
                    })
            temporary.replace(file_path)
            results.append({
                "status": "PASS",
                "attempts": attempts_used,
                "retry_errors": retry_errors,
                "index_id": index_id,
                "snapshot_date": snapshot_date.isoformat(),
                "constituent_count": len(snapshot.rows),
                "input_weight_scale": weight_scale,
                "source_weight_total": str(snapshot.source_weight_total),
                "normalized_weight_total": str(snapshot.normalized_weight_total),
                "weight_tolerance": str(snapshot.weight_tolerance),
                "file": file_path.as_posix(),
                "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
            })
        except Exception as exc:
            results.append({
                "status": "UNKNOWN",
                "attempts": getattr(exc, "retry_attempts", 1),
                "retry_errors": getattr(
                    exc,
                    "retry_errors",
                    [{"attempt": "1", "error_type": type(exc).__name__, "error": str(exc)}],
                ),
                "index_id": index_id,
                "snapshot_date": snapshot_date.isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

    temporal_diffs: list[dict[str, object]] = []
    temporal_rows: list[dict[str, str]] = []
    successful_dates = sorted(successful_snapshots)
    for previous_date, current_date in zip(successful_dates, successful_dates[1:]):
        previous = successful_snapshots[previous_date]
        current = successful_snapshots[current_date]
        previous_symbols = set(previous)
        current_symbols = set(current)
        added = sorted(current_symbols - previous_symbols)
        removed = sorted(previous_symbols - current_symbols)
        changed = sorted(
            symbol for symbol in previous_symbols & current_symbols
            if previous[symbol] != current[symbol]
        )
        for symbol in added:
            temporal_rows.append({
                "previous_date": previous_date.isoformat(),
                "current_date": current_date.isoformat(),
                "change_type": "ADDED",
                "constituent_symbol": symbol,
                "previous_weight_fraction": "",
                "current_weight_fraction": str(current[symbol]),
            })
        for symbol in removed:
            temporal_rows.append({
                "previous_date": previous_date.isoformat(),
                "current_date": current_date.isoformat(),
                "change_type": "REMOVED",
                "constituent_symbol": symbol,
                "previous_weight_fraction": str(previous[symbol]),
                "current_weight_fraction": "",
            })
        for symbol in changed:
            temporal_rows.append({
                "previous_date": previous_date.isoformat(),
                "current_date": current_date.isoformat(),
                "change_type": "WEIGHT_CHANGED",
                "constituent_symbol": symbol,
                "previous_weight_fraction": str(previous[symbol]),
                "current_weight_fraction": str(current[symbol]),
            })
        temporal_diffs.append({
            "previous_date": previous_date.isoformat(),
            "current_date": current_date.isoformat(),
            "previous_constituent_count": len(previous),
            "current_constituent_count": len(current),
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_weight_count": len(changed),
            "snapshots_differ": bool(added or removed or changed),
        })

    temporal_path = output_dir / "temporal_diff.csv"
    temporal_temp = temporal_path.with_suffix(".csv.part")
    with temporal_temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "previous_date", "current_date", "change_type",
                "constituent_symbol", "previous_weight_fraction",
                "current_weight_fraction",
            ),
        )
        writer.writeheader()
        writer.writerows(temporal_rows)
    temporal_temp.replace(temporal_path)
    temporal_sha256 = hashlib.sha256(temporal_path.read_bytes()).hexdigest()
    temporal_status = (
        "PASS" if any(item["snapshots_differ"] for item in temporal_diffs)
        else "UNKNOWN"
    )

    manifest: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "stock-sdk-online",
        "index_id": index_id,
        "query_dates": [value.isoformat() for value in dates],
        "symbol_field": symbol_field,
        "weight_field": weight_field,
        "weight_scale": weight_scale,
        "weight_tolerance": str(weight_tolerance),
        "results": results,
        "historical_date_semantics": {
            "status": temporal_status,
            "evidence": (
                "at least one dated pair returned different constituents or weights"
                if temporal_status == "PASS"
                else "fewer than two successful dates or no differences observed"
            ),
            "comparisons": temporal_diffs,
            "diff_file": temporal_path.as_posix(),
            "diff_sha256": temporal_sha256,
            "diff_row_count": len(temporal_rows),
        },
    }
    manifest_path = output_dir / "manifest.json"
    temporary_manifest = manifest_path.with_suffix(".json.part")
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_manifest.replace(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-id", required=True)
    parser.add_argument("--dates", nargs="+", required=True, help="YYYY-MM-DD as-of dates")
    parser.add_argument("--symbol-field", required=True)
    parser.add_argument("--weight-field", required=True)
    parser.add_argument("--weight-scale", choices=("fraction", "percent"), required=True)
    parser.add_argument("--weight-tolerance", default="0.005")
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=float, default=1.0)
    parser.add_argument("--output", default="data/snapshots/index-constituents")
    args = parser.parse_args()
    try:
        dates = [date.fromisoformat(value) for value in args.dates]
        if dates != sorted(set(dates)):
            raise ValueError("--dates must be unique and ascending")
        from etf_backtesting.adapters.stock_sdk import StockSDKAdapter

        adapter = StockSDKAdapter.from_environment()
        manifest = export_index_snapshots(
            adapter,
            args.index_id,
            dates,
            symbol_field=args.symbol_field,
            weight_field=args.weight_field,
            weight_scale=args.weight_scale,
            output_dir=Path(args.output),
            weight_tolerance=Decimal(args.weight_tolerance),
            retry_attempts=args.retry_attempts,
            retry_delay_seconds=args.retry_delay_seconds,
        )
    except Exception as exc:
        print(f"index snapshot export failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if all(item["status"] == "PASS" for item in manifest["results"]) else 4


if __name__ == "__main__":
    raise SystemExit(main())
