from datetime import date
from pathlib import Path

import pytest

from etf_backtesting.data.dividend_import import load_dividend_snapshot, write_dividend_manifest


SYMBOLS = ["510300", "510880", "513020", "159928", "159611"]
DOMAIN = "example-exchange.cn"


def write_inputs(tmp_path: Path, *, include_all_coverage: bool = True):
    coverage = tmp_path / "coverage.csv"
    events = tmp_path / "events.csv"
    covered = SYMBOLS if include_all_coverage else SYMBOLS[:-1]
    coverage.write_text(
        "symbol,coverage_start,coverage_end,source_name,source_url\n"
        + "".join(
            f"{symbol},2012-01-01,2026-12-31,Exchange notice,https://notice.{DOMAIN}/coverage/{symbol}\n"
            for symbol in covered
        ),
        encoding="utf-8",
    )
    events.write_text(
        "symbol,ex_date,record_date,pay_date,cash_per_share,announcement_date,source_name,source_url\n"
        f"510300,2024-06-10,2024-06-07,2024-06-20,0.05,2024-06-01,Exchange notice,https://notice.{DOMAIN}/event/510300\n",
        encoding="utf-8",
    )
    return events, coverage


def test_dividend_snapshot_requires_complete_per_symbol_coverage_and_provenance(
    tmp_path: Path,
) -> None:
    events, coverage = write_inputs(tmp_path)
    snapshot = load_dividend_snapshot(
        events,
        coverage,
        symbols=SYMBOLS,
        coverage_start=date(2012, 1, 1),
        coverage_end=date(2026, 12, 31),
        approved_domains={DOMAIN},
    )
    manifest = tmp_path / "manifest.json"
    write_dividend_manifest(snapshot, manifest)

    assert len(snapshot.events) == 1
    assert snapshot.events[0].announcement_date == date(2024, 6, 1)
    assert len(snapshot.sha256) == 64
    assert manifest.exists()
    assert "coverage" in manifest.read_text(encoding="utf-8")


def test_dividend_snapshot_does_not_assume_missing_symbol_means_zero_events(
    tmp_path: Path,
) -> None:
    events, coverage = write_inputs(tmp_path, include_all_coverage=False)
    with pytest.raises(ValueError, match="missing official dividend coverage"):
        load_dividend_snapshot(
            events,
            coverage,
            symbols=SYMBOLS,
            coverage_start=date(2012, 1, 1),
            coverage_end=date(2026, 12, 31),
            approved_domains={DOMAIN},
        )


def test_dividend_snapshot_rejects_unapproved_source_domain(tmp_path: Path) -> None:
    events, coverage = write_inputs(tmp_path)
    events.write_text(
        events.read_text(encoding="utf-8").replace(
            f"https://notice.{DOMAIN}/event/510300",
            "https://untrusted.invalid/event/510300",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unapproved or missing event source"):
        load_dividend_snapshot(
            events,
            coverage,
            symbols=SYMBOLS,
            coverage_start=date(2012, 1, 1),
            coverage_end=date(2026, 12, 31),
            approved_domains={DOMAIN},
        )


def test_dividend_snapshot_rejects_announcement_after_ex_date(tmp_path: Path) -> None:
    events, coverage = write_inputs(tmp_path)
    events.write_text(
        events.read_text(encoding="utf-8").replace(
            "2024-06-01,Exchange notice",
            "2024-06-12,Exchange notice",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="announcement must not postdate"):
        load_dividend_snapshot(
            events,
            coverage,
            symbols=SYMBOLS,
            coverage_start=date(2012, 1, 1),
            coverage_end=date(2026, 12, 31),
            approved_domains={DOMAIN},
        )


def test_empty_event_file_is_valid_only_with_complete_symbol_coverage(
    tmp_path: Path,
) -> None:
    events, coverage = write_inputs(tmp_path)
    events.write_text(
        "symbol,ex_date,record_date,pay_date,cash_per_share,announcement_date,source_name,source_url\n",
        encoding="utf-8",
    )
    snapshot = load_dividend_snapshot(
        events,
        coverage,
        symbols=SYMBOLS,
        coverage_start=date(2012, 1, 1),
        coverage_end=date(2026, 12, 31),
        approved_domains={DOMAIN},
    )

    assert snapshot.events == ()
    assert len(snapshot.coverage) == len(SYMBOLS)
    assert len(snapshot.sha256) == 64
