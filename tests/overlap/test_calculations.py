import pytest

from etf_backtesting.overlap.calculations import (
    constituent_jaccard,
    portfolio_exposure,
    top_duplicate_holdings,
    weighted_overlap,
)


def test_constituent_jaccard_uses_union() -> None:
    assert constituent_jaccard({"A", "B"}, {"B", "C"}) == pytest.approx(1 / 3)


def test_weighted_overlap_sums_shared_minimum_weights() -> None:
    assert weighted_overlap({"A": 0.6, "B": 0.4}, {"A": 0.2, "C": 0.8}) == pytest.approx(0.2)


def test_weighted_overlap_rejects_non_normalized_weights() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        weighted_overlap({"A": 0.5}, {"A": 1.0})


def test_portfolio_exposure_aggregates_duplicate_securities() -> None:
    result = portfolio_exposure(
        {"ETF1": 0.5, "ETF2": 0.25},
        {"ETF1": {"A": 0.6, "B": 0.4}, "ETF2": {"A": 0.2, "C": 0.8}},
    )
    assert result == {"A": 0.35, "B": 0.2, "C": 0.2}


def test_top_duplicate_holdings_is_deterministic() -> None:
    result = top_duplicate_holdings(
        {"ETF1": 0.5},
        {"ETF1": {"A": 0.7, "B": 0.3}},
        limit=1,
    )
    assert result == [("A", 0.35)]
