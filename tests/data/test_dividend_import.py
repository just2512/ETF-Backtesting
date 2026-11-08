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


def test_full_history_dividend_coverage_starts_at_each_etf_listing_date(
    tmp_path: Path,
) -> None:
    events, coverage = write_inputs(tmp_path)
    coverage.write_text(
        "symbol,coverage_start,coverage_end,source_name,source_url\n"
        + "".join(
            f"{symbol},{listing},2026-12-31,Exchange notice,https://notice.{DOMAIN}/coverage/{symbol}\n"
            for symbol, listing in {
                "510300": "2012-05-28",
                "510880": "2007-01-18",
                "513020": "2022-02-08",
                "159928": "2013-09-16",
                "159611": "2022-01-07",
            }.items()
        ),
        encoding="utf-8",
    )

    snapshot = load_dividend_snapshot(
        events,
        coverage,
        symbols=SYMBOLS,
        coverage_start=date(2007, 1, 18),
        coverage_end=date(2026, 12, 31),
        approved_domains={DOMAIN},
    )

    coverage_by_symbol = {item.symbol: item.coverage_start for item in snapshot.coverage}
    assert coverage_by_symbol["510880"] == date(2007, 1, 18)
    assert coverage_by_symbol["510300"] == date(2012, 5, 28)
    assert coverage_by_symbol["159928"] == date(2013, 9, 16)


def test_dividend_coverage_rejects_late_start_for_oldest_etf(tmp_path: Path) -> None:
    events, coverage = write_inputs(tmp_path)
    coverage.write_text(
        coverage.read_text(encoding="utf-8").replace(
            "510880,2012-01-01,2026-12-31",
            "510880,2012-01-01,2026-12-31",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="symbol's active requested interval"):
        load_dividend_snapshot(
            events,
            coverage,
            symbols=SYMBOLS,
            coverage_start=date(2007, 1, 18),
            coverage_end=date(2026, 12, 31),
            approved_domains={DOMAIN},
        )
