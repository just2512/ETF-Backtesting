from datetime import date
from pathlib import Path

from etf_backtesting.contracts import PriceBar
from etf_backtesting.data.remote_export import export_snapshot


class FakeRemoteAdapter:
    def read_daily_bars(self, symbol: str):
        if symbol == "BAD":
            raise ConnectionError("online API unavailable")
        return [
            PriceBar(symbol, date(2024, 1, 2), 10, 11, 9, 10.5, 1000, 10500,
                     source="stock-sdk-online"),
            PriceBar(symbol, date(2024, 1, 4), 10.5, 11, 10, 10.8, 1200, 12960,
                     source="stock-sdk-online"),
        ]

    def read_trade_days(self, start: str, end: str):
        assert start == "20240102"
        assert end == "20240104"
        return [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]


def test_remote_export_writes_hashed_unadjusted_snapshot(tmp_path: Path) -> None:
    manifest = export_snapshot(FakeRemoteAdapter(), ["510300"], tmp_path)

    symbol = manifest["symbols"][0]
    assert manifest["fq"] is None
    assert manifest["price_basis"] == "UNADJUSTED"
    assert symbol["status"] == "PASS"
    assert symbol["daily_bar_count"] == 2
    assert len(symbol["sha256"]) == 64
    assert symbol["calendar_completeness"] == "UNKNOWN"
    assert symbol["unclassified_calendar_sessions"] == ["2024-01-03"]
    assert (tmp_path / "510300.csv").exists()
    assert (tmp_path / "manifest.json").exists()


def test_remote_export_keeps_other_symbols_when_one_symbol_fails(tmp_path: Path) -> None:
    manifest = export_snapshot(FakeRemoteAdapter(), ["510300", "BAD"], tmp_path)

    good, bad = manifest["symbols"]
    assert good["status"] == "PASS"
    assert bad["status"] == "UNKNOWN"
    assert bad["error_type"] == "ConnectionError"
    assert (tmp_path / "510300.csv").exists()
    assert not (tmp_path / "BAD.csv").exists()


def test_empty_online_calendar_never_passes_completeness(tmp_path: Path) -> None:
    class EmptyCalendarAdapter(FakeRemoteAdapter):
        def read_trade_days(self, start: str, end: str):
            return []

    manifest = export_snapshot(EmptyCalendarAdapter(), ["510300"], tmp_path)

    assert manifest["calendar_status"] == "UNKNOWN"
    assert manifest["symbols"][0]["calendar_completeness"] == "UNKNOWN"
    assert manifest["symbols"][0]["calendar_error"]["type"] == "EmptyCalendar"


def test_calendar_service_failure_does_not_discard_downloaded_bars(tmp_path: Path) -> None:
    class BrokenCalendarAdapter(FakeRemoteAdapter):
        def read_trade_days(self, start: str, end: str):
            raise TimeoutError("calendar timeout")

    manifest = export_snapshot(BrokenCalendarAdapter(), ["510300"], tmp_path)

    assert manifest["symbols"][0]["status"] == "PASS"
    assert manifest["symbols"][0]["calendar_completeness"] == "UNKNOWN"
    assert manifest["calendar_error"]["type"] == "TimeoutError"
    assert (tmp_path / "510300.csv").exists()
