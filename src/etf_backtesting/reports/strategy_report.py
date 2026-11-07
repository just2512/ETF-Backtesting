"""Reproducible strategy run report and artifact writer."""

from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

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
    filled = [item for item in execution.executions if item.status == "FILLED"]
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
                "quantity", "fill_price", "notional", "fee", "reason",
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
