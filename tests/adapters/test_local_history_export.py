from datetime import date
import json

from etf_backtesting.contracts import PriceBar
from scripts.export_local_history import export_local_snapshot


class FakeLocalAdapter:
    SOURCE_NAME = "local-free-stockdb"

    def read_daily_bars(self, symbol, start, end):
        if symbol == "510880":
            return []
        return [
            PriceBar(
                symbol=symbol,
                trade_date=date(2007, 1, 18),
                open=2.0,
                high=2.1,
                low=1.9,
                close=2.05,
                volume=100.0,
                amount=205.0,
                source=self.SOURCE_NAME,
            )
        ]

    def read_adjustment_factors(self, symbol):
        return []


def test_local_export_writes_unadjusted_hashed_snapshot_and_keeps_calendar_unknown(tmp_path):
    manifest = export_local_snapshot(
        FakeLocalAdapter(),
        ["510880"],
        tmp_path,
        "20000101",
        "20261108",
    )

    result = manifest["symbols"][0]
    assert result["status"] == "PASS"
    assert result["first_date"] == "2007-01-18"
    assert result["first_date_status"] == "PASS"
    assert result["calendar_completeness"] == "UNKNOWN"
    assert result["adjustment_factor_status"] == "MISSING"
    assert result["cash_dividend_status"] == "MISSING"
    assert len(result["sha256"]) == 64
    assert (tmp_path / "510880.csv").is_file()
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["fq"] is None


def test_local_export_preserves_missing_symbol_without_fabricating_rows(tmp_path):
    manifest = export_local_snapshot(
        FakeLocalAdapter(),
        ["510880"],
        tmp_path,
        "20000101",
        "20261108",
    )
    assert manifest["symbols"][0]["status"] == "MISSING"
    assert manifest["symbols"][0]["daily_bar_count"] == 0
    assert not (tmp_path / "510880.csv").exists()
