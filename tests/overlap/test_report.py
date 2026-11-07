from pathlib import Path

from etf_backtesting.overlap.report import build_pairwise_overlap_report, write_overlap_csv


def test_pairwise_report_marks_missing_weight_data_without_faking_overlap() -> None:
    rows = build_pairwise_overlap_report(
        {"IDX_A": {"A", "B"}, "IDX_B": {"B", "C"}},
        {"IDX_A": None, "IDX_B": None},
    )
    assert rows[0]["constituent_jaccard"] == 1 / 3
    assert rows[0]["weighted_overlap"] is None
    assert rows[0]["weight_status"] == "MISSING"


def test_pairwise_report_writes_csv(tmp_path: Path) -> None:
    rows = build_pairwise_overlap_report(
        {"IDX_A": {"A"}, "IDX_B": {"A"}},
        {"IDX_A": {"A": 1.0}, "IDX_B": {"A": 1.0}},
    )
    output = tmp_path / "reports" / "overlap.csv"
    write_overlap_csv(rows, output)
    assert output.exists()
    assert "weighted_overlap" in output.read_text(encoding="utf-8-sig")
