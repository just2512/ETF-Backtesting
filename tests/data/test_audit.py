from etf_backtesting.contracts import AuditStatus
from etf_backtesting.data.audit import (
    audit_adjustment_factor_coverage,
    audit_corporate_action_coverage,
    audit_daily_records,
)


def test_valid_daily_records_pass_basic_checks() -> None:
    findings = audit_daily_records("510300", [
        {"date": "20240102", "open": 3.8, "high": 3.9, "low": 3.7, "close": 3.85,
         "volume": 100, "amount": 385}
    ])
    assert all(item.status == AuditStatus.PASS for item in findings)


def test_duplicate_dates_are_rejected() -> None:
    row = {"date": "20240102", "open": 3.8, "high": 3.9, "low": 3.7, "close": 3.85}
    findings = audit_daily_records("510300", [row, row])
    duplicate = next(item for item in findings if item.check == "duplicate_trade_dates")
    assert duplicate.status == AuditStatus.REJECT


def test_empty_bars_are_missing_not_pass() -> None:
    assert audit_daily_records("510300", [])[0].status == AuditStatus.MISSING


def test_missing_dividend_api_is_unknown_not_zero_dividend() -> None:
    finding = audit_corporate_action_coverage(None)
    assert finding.status == AuditStatus.UNKNOWN


def test_factor_rows_without_verified_semantics_are_unknown() -> None:
    finding = audit_adjustment_factor_coverage([{"factor": 1.2}])
    assert finding.status == AuditStatus.UNKNOWN
