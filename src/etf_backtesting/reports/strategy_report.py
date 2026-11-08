"""Reproducible strategy run report and artifact writer."""

from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from etf_backtesting.strategies.comparison import StrategyComparisonResult
from etf_backtesting.strategies.orchestrator import StrategyRunResult
from etf_backtesting.reports.performance import maximum_drawdown, unitized_nav


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def build_strategy_report(
    result: StrategyRunResult,
    *,
    data_snapshot_sha256: str,
    run_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a stable report manifest bound to the exact data and run configuration."""
    if len(data_snapshot_sha256) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in data_snapshot_sha256
    ):
        raise ValueError("data_snapshot_sha256 must be a 64-character hexadecimal digest")
    if not run_config:
        raise ValueError("run_config must include the complete explicit run parameters")

    execution = result.execution
    snapshots = list(execution.snapshots)
    if not snapshots:
        raise ValueError("cannot report a run with no account snapshots")
    account_values = [item.total_value for item in snapshots]
    external_flows = [item.external_contribution for item in snapshots]
    nav_values = unitized_nav(account_values, external_flows, flow_timing="BEGINNING")
    drawdown = maximum_drawdown(nav_values)

    events = execution.ledger.events
    filled = [
        item for item in execution.executions
        if item.status in ("FILLED", "PARTIAL")
    ]
    partial = [item for item in execution.executions if item.status == "PARTIAL"]
    rejected = [item for item in execution.executions if item.status == "REJECTED"]
    no_fill = [item for item in execution.executions if item.status == "NO_FILL"]
    total_contributions = sum(
        (item.cash_delta for item in events if item.event_type == "CONTRIBUTION"),
        Decimal("0"),
    )
    total_distributions = sum(
        (item.cash_delta for item in events if item.event_type == "CASH_DISTRIBUTION"),
        Decimal("0"),
    )
    total_fees = sum((item.fee for item in events), Decimal("0"))
    total_turnover = sum((item.notional for item in filled), Decimal("0"))
    final_snapshot = snapshots[-1]

    config_text = _canonical_json(run_config)
    config_sha = _sha256(config_text)
    identity = {
        "schema_version": "1",
        "strategy": result.strategy,
        "data_snapshot_sha256": data_snapshot_sha256.lower(),
        "config_sha256": config_sha,
    }
    run_id = _sha256(_canonical_json(identity))

    return {
        "schema_version": "1",
        "run_id": run_id,
        "strategy": result.strategy,
        "research_only": result.research_only,
        "gates": {
            "dividend": result.dividend_gate,
            "dividend_snapshot_sha256": result.dividend_snapshot_sha256,
            "execution_rules": result.execution_rules_gate,
            "index_exposure": result.index_exposure_gate,
            "formal_result_allowed": (
                result.dividend_gate == "PASS"
                and result.execution_rules_gate == "PASS"
                and result.index_exposure_gate in ("PASS", "NOT_APPLICABLE")
                and not result.research_only
            ),
        },
        "reproducibility": {
            "data_snapshot_sha256": data_snapshot_sha256.lower(),
            "dividend_snapshot_sha256": result.dividend_snapshot_sha256,
            "run_config_sha256": config_sha,
            "run_config": dict(run_config),
            "flow_timing": "BEGINNING",
            "signal_timing": "AFTER_CLOSE",
            "execution_timing": "NEXT_SESSION_OPEN",
            "price_basis": "UNADJUSTED",
        },
        "summary": {
            "first_date": snapshots[0].trade_date.isoformat(),
            "last_date": final_snapshot.trade_date.isoformat(),
            "initial_account_value": _decimal_text(account_values[0]),
            "final_account_value": _decimal_text(final_snapshot.total_value),
            "final_cash": _decimal_text(final_snapshot.cash),
            "final_holdings_value": _decimal_text(final_snapshot.holdings_value),
            "final_nav": _decimal_text(nav_values[-1]),
            "time_weighted_return": _decimal_text(nav_values[-1] - Decimal("1")),
            "maximum_drawdown": _decimal_text(drawdown),
            "external_contributions": _decimal_text(total_contributions),
            "cash_distributions": _decimal_text(total_distributions),
            "fees": _decimal_text(total_fees),
            "turnover": _decimal_text(total_turnover),
            "filled_orders": len(filled),
            "partial_orders": len(partial),
            "rejected_orders": len(rejected),
            "no_fill_orders": len(no_fill),
            "stale_valuation_sessions": sum(bool(item.stale_symbols) for item in snapshots),
            "minimum_cash": _decimal_text(min(item.cash for item in snapshots)),
            "maximum_holdings_value": _decimal_text(
                max(item.holdings_value for item in snapshots)
            ),
        },
        "positions": {
            symbol: {
                "quantity": _decimal_text(quantity),
                "cost_basis": _decimal_text(execution.ledger.cost_basis.get(symbol, Decimal("0"))),
                "average_entry_price": _decimal_text(execution.ledger.average_entry_price(symbol)),
            }
            for symbol, quantity in sorted(execution.ledger.positions.items())
        },
        "executions": [
            {
                "status": item.status,
                "symbol": item.symbol,
                "side": item.side,
                "signal_date": item.signal_date.isoformat() if item.signal_date else None,
                "execution_date": item.execution_date.isoformat(),
                "quantity": _decimal_text(item.quantity),
                "requested_quantity": _decimal_text(item.requested_quantity),
                "fill_price": _decimal_text(item.fill_price),
                "notional": _decimal_text(item.notional),
                "fee": _decimal_text(item.fee),
                "reason": item.reason,
            }
            for item in execution.executions
        ],
        "ledger_events": [
            {
                "event_type": item.event_type,
                "symbol": item.symbol,
                "quantity": _decimal_text(item.quantity),
                "price": _decimal_text(item.price),
                "fee": _decimal_text(item.fee),
                "cash_delta": _decimal_text(item.cash_delta),
                "cash_after": _decimal_text(item.cash_after),
                "position_after": _decimal_text(item.position_after),
                "cost_basis_after": _decimal_text(item.cost_basis_after),
                "realized_pnl": _decimal_text(item.realized_pnl),
            }
            for item in events
        ],
        "equity_curve": [
            {
                "date": snapshot.trade_date.isoformat(),
                "phase": snapshot.phase,
                "cash": _decimal_text(snapshot.cash),
                "holdings_value": _decimal_text(snapshot.holdings_value),
                "total_value": _decimal_text(snapshot.total_value),
                "external_contribution": _decimal_text(snapshot.external_contribution),
                "cash_distribution": _decimal_text(snapshot.cash_distribution),
                "nav": _decimal_text(nav),
                "drawdown": _decimal_text(nav / max(nav_values[:index + 1]) - Decimal("1")),
                "stale_symbols": list(snapshot.stale_symbols),
            }
            for index, (snapshot, nav) in enumerate(zip(snapshots, nav_values, strict=True))
        ],
    }


def build_comparison_report(
    result: StrategyComparisonResult,
    *,
    data_snapshot_sha256: str,
    run_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one deterministic report set for A/B/C-per-ETF and D shared-pool runs."""
    if len(data_snapshot_sha256) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in data_snapshot_sha256
    ):
        raise ValueError("data_snapshot_sha256 must be a 64-character hexadecimal digest")
    if not run_config:
        raise ValueError("run_config must include the complete explicit run parameters")

    entries: list[dict[str, Any]] = []
    for symbol in sorted(result.single_etf_runs):
        for strategy in ("A", "B", "C"):
            run = result.single_etf_runs[symbol][strategy]
            effective_config = {
                **dict(run_config),
                "strategy": strategy,
                "symbol_scope": symbol,
            }
            report = build_strategy_report(
                run,
                data_snapshot_sha256=data_snapshot_sha256,
                run_config=effective_config,
            )
            entries.append({
                "strategy": strategy,
                "symbol_scope": symbol,
                "run_id": report["run_id"],
                "gates": report["gates"],
                "summary": report["summary"],
                "report": report,
            })

    run = result.shared_pool_run
    effective_config = {
        **dict(run_config),
        "strategy": "D",
        "symbol_scope": "SHARED_POOL",
    }
    report = build_strategy_report(
        run,
        data_snapshot_sha256=data_snapshot_sha256,
        run_config=effective_config,
    )
    entries.append({
        "strategy": "D",
        "symbol_scope": "SHARED_POOL",
        "run_id": report["run_id"],
        "gates": report["gates"],
        "summary": report["summary"],
        "report": report,
    })

    identity = {
        "schema_version": "1",
        "data_snapshot_sha256": data_snapshot_sha256.lower(),
        "run_config_sha256": _sha256(_canonical_json(run_config)),
        "run_ids": [item["run_id"] for item in entries],
        "trading_days": [item.isoformat() for item in result.trading_days],
    }
    return {
        "schema_version": "1",
        "comparison_id": _sha256(_canonical_json(identity)),
        "data_snapshot_sha256": data_snapshot_sha256.lower(),
        "run_config_sha256": identity["run_config_sha256"],
        "run_config": dict(run_config),
        "trading_days": identity["trading_days"],
        "formal_comparison_allowed": all(
            item["gates"]["formal_result_allowed"] for item in entries
        ),
        "runs": entries,
    }


def write_comparison_report(
    comparison: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, str]:
    """Write per-run artifacts plus deterministic JSON and CSV comparison indexes."""
    output_dir.mkdir(parents=True, exist_ok=True)
    run_index: list[dict[str, Any]] = []
    artifact_paths: dict[str, str] = {}

    for item in comparison["runs"]:
        scope = str(item["symbol_scope"])
        strategy = str(item["strategy"])
        safe_scope = "".join(
            character for character in scope if character.isalnum() or character in "-_"
        )
        relative_dir = Path("runs") / safe_scope / strategy
        run_dir = output_dir / relative_dir
        paths = write_strategy_report(item["report"], run_dir)
        report_path = Path(paths["summary"])
        report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
        relative_files = {
            name: (relative_dir / Path(path).name).as_posix()
            for name, path in paths.items()
        }
        artifact_paths[f"{safe_scope}_{strategy}"] = (
            output_dir / relative_dir / Path(paths["summary"]).name
        ).as_posix()
        run_index.append({
            "strategy": strategy,
            "symbol_scope": scope,
            "run_id": item["run_id"],
            "gates": item["gates"],
            "summary": item["summary"],
            "report_sha256": report_sha256,
            "artifacts": relative_files,
        })

    manifest = {
        key: value for key, value in comparison.items() if key != "runs"
    }
    manifest["runs"] = run_index
    manifest_path = output_dir / "comparison.json"
    manifest_temp = manifest_path.with_suffix(".json.part")
    manifest_temp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_temp.replace(manifest_path)

    csv_path = output_dir / "comparison.csv"
    csv_temp = csv_path.with_suffix(".csv.part")
    fields = (
        "strategy", "symbol_scope", "run_id", "formal_result_allowed",
        "dividend_gate", "execution_rules_gate", "index_exposure_gate",
        "first_date", "last_date", "final_nav", "time_weighted_return",
        "maximum_drawdown", "fees", "turnover", "filled_orders",
        "partial_orders", "rejected_orders", "no_fill_orders",
    )
    with csv_temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in run_index:
            gates = item["gates"]
            summary = item["summary"]
            writer.writerow({
                "strategy": item["strategy"],
                "symbol_scope": item["symbol_scope"],
                "run_id": item["run_id"],
                "formal_result_allowed": gates["formal_result_allowed"],
                "dividend_gate": gates["dividend"],
                "execution_rules_gate": gates["execution_rules"],
                "index_exposure_gate": gates["index_exposure"],
                **{key: summary[key] for key in fields[7:]},
            })
    csv_temp.replace(csv_path)
    artifact_paths["comparison_json"] = manifest_path.as_posix()
    artifact_paths["comparison_csv"] = csv_path.as_posix()
    from etf_backtesting.reports.html_report import render_comparison_html

    html_path = render_comparison_html(output_dir)
    artifact_paths["comparison_html"] = html_path.as_posix()
    return artifact_paths


def write_strategy_report(
    report: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, str]:
    """Write JSON, equity CSV, executions CSV, and ledger CSV atomically."""
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": output_dir / "report.json",
        "equity": output_dir / "equity_curve.csv",
        "executions": output_dir / "executions.csv",
        "ledger": output_dir / "ledger_events.csv",
    }
    payloads = {
        "summary": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        "equity": _csv_text(
            report["equity_curve"],
            (
                "date", "phase", "cash", "holdings_value", "total_value",
                "external_contribution", "cash_distribution", "nav", "drawdown",
                "stale_symbols",
            ),
        ),
        "executions": _csv_text(
            report["executions"],
            (
                "status", "symbol", "side", "signal_date", "execution_date",
                "quantity", "requested_quantity", "fill_price", "notional", "fee", "reason",
            ),
        ),
        "ledger": _csv_text(
            report["ledger_events"],
            (
                "event_type", "symbol", "quantity", "price", "fee", "cash_delta",
                "cash_after", "position_after", "cost_basis_after", "realized_pnl",
            ),
        ),
    }
    for name, path in files.items():
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(payloads[name], encoding="utf-8", newline="")
        temporary.replace(path)
    return {name: path.as_posix() for name, path in files.items()}


def _csv_text(rows: list[Mapping[str, Any]], fields: tuple[str, ...]) -> str:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({
            key: json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value
            for key, value in row.items()
        })
    return buffer.getvalue()
