"""Resolve ETF tracking indices from NovAPI's catalog and import dated history."""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from etf_backtesting.adapters.stock_sdk import StockSDKAdapter
from etf_backtesting.data.index_history import export_index_snapshots


ETF_CONFIG = Path("config/etf_universe.yaml")
CODE_FIELDS = ("code", "symbol", "security", "index_code", "index", "ts_code")
NAME_FIELDS = ("display_name", "name", "security_name", "displayName", "名称")
WEIGHT_FIELDS = ("weight", "weight_ratio", "weight_pct", "i_weight", "权重")


def records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        raise ValueError("get_all_securities returned no index catalog")
    if callable(getattr(value, "reset_index", None)):
        value = value.reset_index()
    if callable(getattr(value, "to_dict", None)):
        try:
            value = value.to_dict("records")
        except TypeError:
            value = value.to_dict()
    if isinstance(value, Mapping):
        keys = list(value)
        columns = [value[key] for key in keys]
        if columns and all(isinstance(column, (list, tuple)) for column in columns):
            lengths = {len(column) for column in columns}
            if len(lengths) != 1:
                raise ValueError("index catalog columns have inconsistent lengths")
            return [dict(zip(keys, row, strict=True)) for row in zip(*columns, strict=True)]
        return [dict(value)]
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("get_all_securities returned an empty or unsupported catalog")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError("index catalog rows must be mappings")
    return [dict(row) for row in value]


def load_tracking_indices() -> dict[str, str]:
    source = ETF_CONFIG.read_text(encoding="utf-8")
    pairs = re.findall(
        r'- symbol: ["\']([^"\']+)["\']\s+name: ["\'][^"\']*["\']\s+tracking_index: ["\']([^"\']+)["\']',
        source,
    )
    if not pairs:
        raise ValueError(f"could not parse ETF/index pairs from {ETF_CONFIG}")
    return dict(pairs)


def resolve_index_ids(adapter: StockSDKAdapter, as_of: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    getter = getattr(adapter.sdk, "get_all_securities", None)
    if not callable(getter):
        raise TypeError("NovAPI stock_sdk must expose get_all_securities(types, date)")
    raw = getter(types=["index"], date=as_of)
    raw = adapter._raise_on_service_error(raw, "get_all_securities", "index catalog")
    catalog = records(raw)
    if not catalog:
        raise ValueError("NovAPI index catalog is empty")
    fields = set().union(*(row.keys() for row in catalog))
    code_field = next((field for field in CODE_FIELDS if field in fields), None)
    name_field = next((field for field in NAME_FIELDS if field in fields), None)
    if code_field is None or name_field is None:
        raise ValueError(
            "cannot resolve index catalog schema; "
            f"available_fields={sorted(str(field) for field in fields)}"
        )

    requested = load_tracking_indices()
    resolved: dict[str, str] = {}
    unresolved: list[dict[str, str]] = []
    for symbol, tracking_name in requested.items():
        matches = [
            row for row in catalog
            if str(row.get(name_field, "")).strip() == tracking_name
        ]
        if len(matches) == 1:
            code = str(matches[0].get(code_field, "")).strip().upper()
            if code:
                resolved[symbol] = code
                continue
        unresolved.append({
            "etf_symbol": symbol,
            "tracking_index": tracking_name,
            "status": "UNKNOWN" if not matches else "REJECT",
            "match_count": str(len(matches)),
            "reason": "exact provider catalog name did not resolve to one index code",
        })
    return resolved, unresolved


def weight_contract(raw: Any) -> tuple[str, str, str]:
    weights = raw.get("weights") if isinstance(raw, Mapping) else None
    if weights is None:
        raise ValueError("historical index response has no weights payload")
    if callable(getattr(weights, "reset_index", None)):
        weights = weights.reset_index()
    if callable(getattr(weights, "to_dict", None)):
        try:
            rows = weights.to_dict("records")
        except TypeError:
            rows = weights.to_dict()
    else:
        rows = weights

    if isinstance(rows, Mapping):
        keys = list(rows)
        values = list(rows.values())
        if rows and all(not isinstance(v, (Mapping, list, tuple)) for v in values):
            total = sum((Decimal(str(v)) for v in values), Decimal("0"))
            symbol_field, weight_field = "code", "weight"
        elif values and all(isinstance(v, (list, tuple)) for v in values):
            if len({len(v) for v in values}) != 1:
                raise ValueError("weight response columns have inconsistent lengths")
            materialized = [dict(zip(keys, row, strict=True)) for row in zip(*values, strict=True)]
            fields = set().union(*(row.keys() for row in materialized))
            symbol_field = next((field for field in CODE_FIELDS if field in fields), "")
            weight_field = next((field for field in WEIGHT_FIELDS if field in fields), "")
            if not symbol_field or not weight_field:
                raise ValueError(f"unrecognized weight columns: {sorted(fields)}")
            total = sum((Decimal(str(row[weight_field])) for row in materialized), Decimal("0"))
        else:
            raise ValueError("unsupported mapping shape for index weights")
    elif isinstance(rows, (list, tuple)) and rows and all(isinstance(row, Mapping) for row in rows):
        fields = set().union(*(row.keys() for row in rows))
        symbol_field = next((field for field in CODE_FIELDS if field in fields), "")
        weight_field = next((field for field in WEIGHT_FIELDS if field in fields), "")
        if not symbol_field or not weight_field:
            raise ValueError(f"unrecognized weight columns: {sorted(fields)}")
        total = sum((Decimal(str(row[weight_field])) for row in rows), Decimal("0"))
    else:
        raise ValueError(f"unsupported index weights response type: {type(rows).__name__}")

    if abs(total - Decimal("1")) <= Decimal("0.005"):
        scale = "fraction"
    elif abs(total - Decimal("100")) <= Decimal("0.5"):
        scale = "percent"
    else:
        raise ValueError(
            "index weights do not reconcile to 1 or 100; "
            f"source_total={total}; refusing to infer units or normalize"
        )
    return symbol_field, weight_field, scale


def retry(operation: Any, attempts: int, delay_seconds: float) -> Any:
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except (ConnectionError, TimeoutError, OSError) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt == attempts:
                raise ConnectionError(
                    f"NovAPI request failed after {attempts} attempts: " + " | ".join(errors)
                ) from exc
            time.sleep(delay_seconds * (2 ** (attempt - 1)))
    raise RuntimeError("unreachable retry state")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="20220208")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=float, default=2.0)
    parser.add_argument("--output", default="data/snapshots/remote-stock-sdk/index-history")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "source": "NovAPI",
        "requested_start": args.start,
        "requested_end": args.end,
        "resolved_indices": {},
        "unresolved_indices": [],
        "results": [],
    }
    try:
        adapter = StockSDKAdapter.from_environment()
        start_date = date.fromisoformat(
            f"{args.start[:4]}-{args.start[4:6]}-{args.start[6:8]}"
        )
        end_date = date.fromisoformat(
            f"{args.end[:4]}-{args.end[4:6]}-{args.end[6:8]}"
        )
        catalog_date = end_date.isoformat()
        resolved, unresolved = retry(
            lambda: resolve_index_ids(adapter, catalog_date),
            args.retry_attempts,
            args.retry_delay_seconds,
        )
        report["resolved_indices"] = resolved
        report["unresolved_indices"] = unresolved
        trade_days = retry(
            lambda: adapter.read_trade_days(args.start, args.end),
            args.retry_attempts,
            args.retry_delay_seconds,
        )
        report["trading_day_count"] = len(trade_days)
        report["first_trading_day"] = trade_days[0].isoformat() if trade_days else None
        report["last_trading_day"] = trade_days[-1].isoformat() if trade_days else None

        tracking_indices = load_tracking_indices()
        for etf_symbol, index_id in resolved.items():
            try:
                # Determine the provider's actual field names and weight units
                # from one dated response. No fields or units are guessed.
                sample_date = next((day for day in trade_days if day >= start_date), None)
                if sample_date is None:
                    raise ValueError("trading calendar contains no date in the requested range")
                raw = retry(
                    lambda: adapter.read_history_constituents(index_id, sample_date),
                    args.retry_attempts,
                    args.retry_delay_seconds,
                )
                symbol_field, weight_field, scale = weight_contract(raw)
                manifest = export_index_snapshots(
                    adapter,
                    index_id,
                    trade_days,
                    symbol_field=symbol_field,
                    weight_field=weight_field,
                    weight_scale=scale,  # type: ignore[arg-type]
                    output_dir=output / index_id.replace(".", "_"),
                    retry_attempts=args.retry_attempts,
                    retry_delay_seconds=args.retry_delay_seconds,
                )
                report["results"].append({
                    "status": "PASS" if all(
                        item.get("status") == "PASS" for item in manifest["results"]
                    ) else "UNKNOWN",
                    "etf_symbol": etf_symbol,
                    "tracking_index": tracking_indices[etf_symbol],
                    "index_id": index_id,
                    "symbol_field": symbol_field,
                    "weight_field": weight_field,
                    "weight_scale": scale,
                    "snapshot_count": len(trade_days),
                    "manifest": manifest,
                })
            except Exception as exc:
                report["results"].append({
                    "status": "UNKNOWN",
                    "etf_symbol": etf_symbol,
                    "tracking_index": tracking_indices[etf_symbol],
                    "index_id": index_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
    except Exception as exc:
        report["fatal_error"] = {
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        output_file = output / "manifest.json"
        output_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 4

    output_file = output / "manifest.json"
    output_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 4 if report["unresolved_indices"] or any(
        any(item.get("status") != "PASS" for item in result["manifest"]["results"])
        for result in report["results"]
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
