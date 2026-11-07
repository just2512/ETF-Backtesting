"""Strict point-in-time index constituent snapshot normalization and export."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, Mapping


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
) -> dict[str, object]:
    """Fetch each as-of snapshot independently and retain failures in the manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for snapshot_date in dates:
        try:
            raw = adapter.read_history_constituents(index_id, snapshot_date)
            snapshot = normalize_index_snapshot(
                raw,
                index_id,
                snapshot_date,
                symbol_field=symbol_field,
                weight_field=weight_field,
                weight_scale=weight_scale,
                weight_tolerance=weight_tolerance,
            )
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
                "index_id": index_id,
                "snapshot_date": snapshot_date.isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

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
        )
    except Exception as exc:
        print(f"index snapshot export failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if all(item["status"] == "PASS" for item in manifest["results"]) else 4


if __name__ == "__main__":
    raise SystemExit(main())
