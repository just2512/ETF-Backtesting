"""Hard-gate checks for industry exposure after proposed ETF allocations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from math import isclose


@dataclass(frozen=True, slots=True)
class ExposureViolation:
    industry: str
    projected_value: Decimal
    projected_fraction: Decimal
    maximum_fraction: Decimal


def check_industry_exposure(
    portfolio_value: Decimal,
    current_industry_values: Mapping[str, Decimal],
    proposed_allocations: Mapping[str, Decimal],
    etf_constituent_weights: Mapping[str, Mapping[str, float]],
    security_industries: Mapping[str, str],
    industry_caps: Mapping[str, Decimal],
) -> list[ExposureViolation]:
    """Return cap breaches; missing look-through data blocks the calculation."""
    if portfolio_value <= 0:
        raise ValueError("portfolio_value must be positive")
    additions: defaultdict[str, Decimal] = defaultdict(Decimal)
    for etf, amount in proposed_allocations.items():
        if amount < 0:
            raise ValueError("proposed allocation must not be negative")
        if etf not in etf_constituent_weights:
            raise ValueError(f"missing constituent weights for {etf}")
        weights = etf_constituent_weights[etf]
        if not isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-4):
            raise ValueError(f"constituent weights for {etf} must sum to 1")
        for security, weight in weights.items():
            if weight < 0:
                raise ValueError(f"negative constituent weight for {security}")
            industry = security_industries.get(security)
            if not industry:
                raise ValueError(f"missing industry classification for {security}")
            additions[industry] += amount * Decimal(str(weight))

    violations = []
    for industry, cap in industry_caps.items():
        if cap < 0 or cap > 1:
            raise ValueError(f"industry cap for {industry} must be between 0 and 1")
        projected = current_industry_values.get(industry, Decimal("0")) + additions[industry]
        fraction = projected / portfolio_value
        if fraction > cap:
            violations.append(ExposureViolation(industry, projected, fraction, cap))
    return sorted(violations, key=lambda item: item.industry)
