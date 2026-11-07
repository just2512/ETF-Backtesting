"""Deterministic overlap calculations over same-date constituent snapshots."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date
from math import isclose

from etf_backtesting.contracts import IndexConstituent


def constituent_jaccard(
    constituents_a: set[str],
    constituents_b: set[str],
) -> float:
    union = constituents_a | constituents_b
    if not union:
        return 1.0
    return len(constituents_a & constituents_b) / len(union)


def weighted_overlap(
    weights_a: Mapping[str, float],
    weights_b: Mapping[str, float],
) -> float:
    """Return sum(min(wA_i, wB_i)); weights must be normalized to 1."""
    if not weights_a or not weights_b:
        raise ValueError("both constituent weight maps are required")
    for label, weights in (("A", weights_a), ("B", weights_b)):
        if any(value < 0 for value in weights.values()):
            raise ValueError(f"index {label} contains negative weights")
        if not isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-4):
            raise ValueError(f"index {label} weights must sum to 1")
    return sum(min(weights_a.get(code, 0.0), weights_b.get(code, 0.0))
               for code in weights_a.keys() | weights_b.keys())


def portfolio_exposure(
    etf_allocations: Mapping[str, float],
    index_weights: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    """Aggregate security exposures from ETF allocation and dated index weights."""
    if set(etf_allocations) - set(index_weights):
        missing = sorted(set(etf_allocations) - set(index_weights))
        raise ValueError(f"missing index weights for ETF(s): {missing}")
    if any(value < 0 for value in etf_allocations.values()):
        raise ValueError("ETF allocations must not be negative")
    total_allocation = sum(etf_allocations.values())
    if total_allocation > 1.0 + 1e-9:
        raise ValueError("ETF allocations must not exceed 1")
    result: defaultdict[str, float] = defaultdict(float)
    for etf, allocation in etf_allocations.items():
        weights = index_weights[etf]
        if any(value < 0 for value in weights.values()):
            raise ValueError(f"negative constituent weight for {etf}")
        if not isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-4):
            raise ValueError(f"constituent weights for {etf} must sum to 1")
        for security, weight in weights.items():
            result[security] += allocation * weight
    return dict(sorted(result.items()))


def top_duplicate_holdings(
    etf_allocations: Mapping[str, float],
    index_weights: Mapping[str, Mapping[str, float]],
    limit: int = 20,
) -> list[tuple[str, float]]:
    if limit < 1:
        raise ValueError("limit must be positive")
    exposures = portfolio_exposure(etf_allocations, index_weights)
    return sorted(exposures.items(), key=lambda item: (-item[1], item[0]))[:limit]



def active_constituent_weights(
    records: Iterable[IndexConstituent],
    index_id: str,
    as_of: date,
) -> dict[str, float]:
    """Rebuild an index snapshot using effective dates, never today's holdings."""
    active = [
        row for row in records
        if row.index_id == index_id and row.active_on(as_of)
    ]
    if not active:
        raise ValueError(f"no active constituent records for {index_id} on {as_of}")
    if any(row.weight is None for row in active):
        raise ValueError("historical constituent weights are incomplete for this date")
    weights: dict[str, float] = {}
    for row in active:
        if row.weight is None or row.weight < 0:
            raise ValueError("historical constituent weights must be non-negative")
        if row.constituent_symbol in weights:
            raise ValueError(f"duplicate active constituent: {row.constituent_symbol}")
        weights[row.constituent_symbol] = row.weight
    if not isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-4):
        raise ValueError("active historical index weights must sum to 1")
    return dict(sorted(weights.items()))
