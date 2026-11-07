from datetime import date
from pathlib import Path

import pytest
from decimal import Decimal

from etf_backtesting.data.index_history import (
    export_index_snapshots,
    normalize_index_snapshot,
)


def test_normalize_fraction_weights_and_keep_asof_date() -> None:
    snapshot = normalize_index_snapshot(
        [
            {"ticker": "600000.XSHG", "weight": "0.4"},
            {"ticker": "000001.XSHE", "weight": "0.6"},
        ],
        "000300.XSHG",
        date(2020, 6, 30),
        symbol_field="ticker",
        weight_field="weight",
        weight_scale="fraction",
    )

    assert snapshot.snapshot_date == date(2020, 6, 30)
    assert snapshot.normalized_weight_total == 1
    assert [row.constituent_symbol for row in snapshot.rows] == [
        "000001.XSHE", "600000.XSHG"
    ]
    assert all(row.snapshot_date == date(2020, 6, 30) for row in snapshot.rows)


def test_normalize_percent_weights_only_when_scale_is_explicit() -> None:
    snapshot = normalize_index_snapshot(
        [{"code": "A", "weight_pct": "25"}, {"code": "B", "weight_pct": "75"}],
        "TEST.XSHG",
        date(2024, 1, 2),
        symbol_field="code",
        weight_field="weight_pct",
        weight_scale="percent",
    )

    assert snapshot.source_weight_total == 100
    assert snapshot.normalized_weight_total == 1
    assert [row.weight_fraction for row in snapshot.rows] == [
        Decimal("0.25"), Decimal("0.75")
    ]


def test_incomplete_weight_total_is_rejected_without_auto_normalization() -> None:
    with pytest.raises(ValueError, match="do not auto-normalize"):
        normalize_index_snapshot(
            [{"code": "A", "weight": 0.4}, {"code": "B", "weight": 0.5}],
            "TEST.XSHG",
            date(2024, 1, 2),
            symbol_field="code",
            weight_field="weight",
            weight_scale="fraction",
        )


def test_duplicate_symbols_and_missing_field_contract_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        normalize_index_snapshot(
            [{"code": "A", "weight": 0.5}, {"code": "A", "weight": 0.5}],
            "TEST.XSHG",
            date(2024, 1, 2),
            symbol_field="code",
            weight_field="weight",
            weight_scale="fraction",
        )
    with pytest.raises(ValueError, match="missing required fields"):
        normalize_index_snapshot(
            [{"symbol": "A", "weight": 1}],
            "TEST.XSHG",
            date(2024, 1, 2),
            symbol_field="code",
            weight_field="weight",
            weight_scale="fraction",
        )


def test_index_export_keeps_per_date_failures_and_hashes_successes(tmp_path: Path) -> None:
    class FakeAdapter:
        def read_history_constituents(self, index_id: str, as_of: date):
            if as_of == date(2020, 6, 30):
                raise TimeoutError("historical endpoint timed out")
            return [
                {"code": "A", "weight": "0.4"},
                {"code": "B", "weight": "0.6"},
            ]

    manifest = export_index_snapshots(
        FakeAdapter(),
        "TEST.XSHG",
        [date(2020, 6, 30), date(2021, 6, 30)],
        symbol_field="code",
        weight_field="weight",
        weight_scale="fraction",
        output_dir=tmp_path,
    )

    failed, passed = manifest["results"]
    assert failed["status"] == "UNKNOWN"
    assert failed["error_type"] == "TimeoutError"
    assert passed["status"] == "PASS"
    assert passed["constituent_count"] == 2
    assert len(passed["sha256"]) == 64
    assert (tmp_path / "manifest.json").exists()
