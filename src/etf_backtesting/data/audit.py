"""Source-neutral data quality checks; never silently repair source records."""

from __future__ import annotations

from collections import Counter
from datetime import date
from math import isfinite
from typing import Any, Iterable, Mapping

from etf_backtesting.contracts import AuditFinding, AuditStatus


REQUIRED_OHLC = ("open", "high", "low", "close")


def audit_daily_records(
    symbol: str,
    records: Iterable[Mapping[str, Any]],
    expected_trade_dates: Iterable[str] | None = None,
) -> list[AuditFinding]:
    rows = list(records)
    if not rows:
        return [
            AuditFinding(
                AuditStatus.MISSING, "daily_bars_present",
                "No daily bars were returned by the data source.", symbol,
            )
        ]

    findings: list[AuditFinding] = []
    dates: list[str] = []
    invalid_rows: list[dict[str, object]] = []
    missing_fields: Counter[str] = Counter()

    for index, row in enumerate(rows):
        raw_date = str(row.get("date", ""))
        if len(raw_date) != 8 or not raw_date.isdigit():
            invalid_rows.append({"row": index, "reason": "invalid_date", "value": raw_date})
        else:
            try:
                date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
                dates.append(raw_date)
            except ValueError:
                invalid_rows.append({"row": index, "reason": "impossible_date", "value": raw_date})

        values: dict[str, float] = {}
        for field in REQUIRED_OHLC:
            if row.get(field) is None:
                missing_fields[field] += 1
                continue
            try:
                value = float(row[field])
            except (TypeError, ValueError):
                invalid_rows.append({"row": index, "reason": f"non_numeric_{field}"})
                continue
            if not isfinite(value) or value <= 0:
                invalid_rows.append({"row": index, "reason": f"invalid_{field}", "value": value})
            values[field] = value

        if len(values) == 4:
            if values["high"] < max(values["open"], values["close"], values["low"]):
                invalid_rows.append({"row": index, "reason": "ohlc_high_inconsistent"})
            if values["low"] > min(values["open"], values["close"], values["high"]):
                invalid_rows.append({"row": index, "reason": "ohlc_low_inconsistent"})

        for field in ("volume", "amount"):
            if row.get(field) is not None:
                try:
                    value = float(row[field])
                    if not isfinite(value) or value < 0:
                        invalid_rows.append({"row": index, "reason": f"invalid_{field}"})
                except (TypeError, ValueError):
                    invalid_rows.append({"row": index, "reason": f"non_numeric_{field}"})

    duplicate_dates = sorted(day for day, count in Counter(dates).items() if count > 1)
    if duplicate_dates:
        findings.append(AuditFinding(
            AuditStatus.REJECT, "duplicate_trade_dates",
            "Duplicate daily records exist for one or more trade dates.", symbol,
            {"dates": duplicate_dates},
        ))
    else:
        findings.append(AuditFinding(
            AuditStatus.PASS, "duplicate_trade_dates", "No duplicate valid dates.", symbol,
        ))

    if invalid_rows:
        findings.append(AuditFinding(
            AuditStatus.REJECT, "ohlc_and_record_validity",
            "One or more records have invalid dates, values, or OHLC relationships.",
            symbol, {"invalid_rows": invalid_rows},
        ))
    else:
        findings.append(AuditFinding(
            AuditStatus.PASS, "ohlc_and_record_validity",
            "All returned records passed basic date and OHLC checks.", symbol,
        ))

    if missing_fields:
        findings.append(AuditFinding(
            AuditStatus.MISSING, "required_ohlc_fields",
            "Required OHLC fields are missing in some records.", symbol,
            {"missing_counts": dict(missing_fields)},
        ))
    else:
        findings.append(AuditFinding(
            AuditStatus.PASS, "required_ohlc_fields", "All OHLC fields are present.", symbol,
        ))


    if expected_trade_dates is None:
        findings.append(AuditFinding(
            AuditStatus.UNKNOWN, "trade_date_completeness",
            "No authoritative exchange trading calendar was supplied; gaps cannot be classified.",
            symbol,
        ))
    else:
        expected = set(expected_trade_dates)
        observed = set(dates)
        missing_dates = sorted(expected - observed)
        if missing_dates:
            findings.append(AuditFinding(
                AuditStatus.REJECT, "trade_date_completeness",
                "Expected trading dates are absent from the returned daily bars.",
                symbol, {"missing_dates": missing_dates},
            ))
        else:
            findings.append(AuditFinding(
                AuditStatus.PASS, "trade_date_completeness",
                "All supplied expected trading dates are present.", symbol,
                {"expected_date_count": len(expected)},
            ))

    findings.append(AuditFinding(
        AuditStatus.PASS, "coverage_observed",
        "Observed coverage range from returned records; not proof of full historical completeness.",
        symbol,
        {"count": len(rows), "first_date": min(dates) if dates else None,
         "last_date": max(dates) if dates else None},
    ))
    return findings


def audit_corporate_action_coverage(
    records: Iterable[Mapping[str, Any]] | None,
) -> AuditFinding:
    if records is None:
        return AuditFinding(
            AuditStatus.UNKNOWN, "corporate_actions",
            "No documented corporate-action endpoint was available to this audit.",
        )
    rows = list(records)
    if not rows:
        return AuditFinding(
            AuditStatus.MISSING, "corporate_actions",
            "The source returned no corporate-action records.",
        )
    return AuditFinding(
        AuditStatus.PASS, "corporate_actions",
        "Corporate-action records were returned; event-level validation remains required.",
        evidence={"count": len(rows)},
    )


def audit_adjustment_factor_coverage(
    records: Iterable[Mapping[str, Any]] | None,
    semantics_verified: bool = False,
) -> AuditFinding:
    if records is None:
        return AuditFinding(
            AuditStatus.UNKNOWN, "adjustment_factors",
            "Adjustment-factor data could not be queried.",
        )
    rows = list(records)
    if not rows:
        return AuditFinding(
            AuditStatus.MISSING, "adjustment_factors",
            "No adjustment-factor records were returned.",
        )
    if not semantics_verified:
        return AuditFinding(
            AuditStatus.UNKNOWN, "adjustment_factor_semantics",
            "Factors exist, but their direction, effective-date convention, and relation to distributions are unverified.",
            evidence={"count": len(rows)},
        )
    return AuditFinding(
        AuditStatus.PASS, "adjustment_factors",
        "Adjustment-factor records and semantics were verified.",
        evidence={"count": len(rows)},
    )



def summarize_findings(findings: Iterable[AuditFinding]) -> dict[str, Any]:
    """Aggregate findings with hard-gate precedence: REJECT, MISSING, UNKNOWN, PASS."""
    items = list(findings)
    counts = {status.value: 0 for status in AuditStatus}
    for item in items:
        counts[item.status.value] += 1

    if counts[AuditStatus.REJECT.value]:
        overall = AuditStatus.REJECT
    elif counts[AuditStatus.MISSING.value]:
        overall = AuditStatus.MISSING
    elif counts[AuditStatus.UNKNOWN.value]:
        overall = AuditStatus.UNKNOWN
    else:
        overall = AuditStatus.PASS

    return {
        "overall_status": overall.value,
        "counts": counts,
        "findings": [
            {
                "status": item.status.value,
                "check": item.check,
                "message": item.message,
                "symbol": item.symbol,
                "evidence": item.evidence,
            }
            for item in items
        ],
    }
