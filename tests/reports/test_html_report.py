import json
from pathlib import Path

import pytest

from etf_backtesting.reports.html_report import render_comparison_html


def _write_fixture(root: Path) -> None:
    run_dir = root / "runs" / "510300" / "A"
    run_dir.mkdir(parents=True)
    report = {
        "run_id": "a" * 64,
        "executions": [{
            "execution_date": "2024-01-03",
            "symbol": "510300",
            "side": "BUY",
            "status": "FILLED",
            "quantity": "100",
            "fill_price": "10",
            "notional": "1000",
            "fee": "1",
            "reason": "test <script>alert(1)</script>",
        }],
        "equity_curve": [
            {"date": "2024-01-02", "nav": "1", "drawdown": "0",
             "cash": "10000", "holdings_value": "0", "total_value": "10000"},
            {"date": "2024-01-03", "nav": "1.01", "drawdown": "0",
             "cash": "8999", "holdings_value": "1000", "total_value": "9999"},
        ],
    }
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    manifest = {
        "comparison_id": "b" * 64,
        "data_snapshot_sha256": "c" * 64,
        "run_config_sha256": "d" * 64,
        "run_config": {"initial_cash": "10000"},
        "trading_days": ["2024-01-02", "2024-01-03"],
        "formal_comparison_allowed": False,
        "runs": [{
            "strategy": "A",
            "symbol_scope": "510300",
            "run_id": "a" * 64,
            "gates": {"formal_result_allowed": False},
            "summary": {
                "first_date": "2024-01-02",
                "last_date": "2024-01-03",
                "final_account_value": "9999",
                "final_nav": "1.01",
                "time_weighted_return": "0.01",
                "maximum_drawdown": "0",
                "external_contributions": "0",
                "final_cash": "8999",
                "filled_orders": 1,
                "partial_orders": 0,
                "rejected_orders": 0,
                "no_fill_orders": 0,
                "fees": "1",
                "turnover": "1000",
            },
            "artifacts": {"summary": "runs/510300/A/report.json"},
        }],
    }
    (root / "comparison.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_render_comparison_html_embeds_runs_and_controls(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    output = render_comparison_html(tmp_path)
    html = output.read_text(encoding="utf-8")
    assert output.name == "comparison.html"
    assert 'id="scope"' in html
    assert 'id="main-chart"' in html
    assert 'id="dd-chart"' in html
    assert "510300" in html
    assert "test \\u003cscript\\u003e" in html
    assert "正式比较门禁" in html


def test_render_rejects_report_path_traversal(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    manifest = json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8"))
    manifest["runs"][0]["artifacts"]["summary"] = "../outside.json"
    (tmp_path / "comparison.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        render_comparison_html(tmp_path)


def test_render_requires_each_report_artifact(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    (tmp_path / "runs" / "510300" / "A" / "report.json").unlink()
    with pytest.raises(FileNotFoundError, match="run report"):
        render_comparison_html(tmp_path)
