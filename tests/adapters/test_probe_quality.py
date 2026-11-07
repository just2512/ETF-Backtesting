from etf_backtesting.adapters.free_stockdb import FreeStockDBAdapter


class FakeClient:
    _fq_dates = {"510300": ["20240102"]}
    _fq_cums = {"510300": [1.0]}

    def get_data(self, **kwargs):
        return [{"date": 20240102, "open": 3.8, "high": 3.9, "low": 3.7, "close": 3.85}]


def test_probe_includes_quality_checks_and_calendar_unknown() -> None:
    report = FreeStockDBAdapter(FakeClient()).probe_symbol("510300")
    findings = {item["check"]: item for item in report["data_quality_findings"]}
    assert findings["ohlc_and_record_validity"]["status"] == "PASS"
    assert findings["trade_date_completeness"]["status"] == "UNKNOWN"
