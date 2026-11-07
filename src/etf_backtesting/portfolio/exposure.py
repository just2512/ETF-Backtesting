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



def max_allocation_under_industry_caps(
    requested_amount: Decimal,
    portfolio_value: Decimal,
    current_industry_values: Mapping[str, Decimal],
    constituent_weights: Mapping[str, float],
    security_industries: Mapping[str, str],
    industry_caps: Mapping[str, Decimal],
) -> Decimal:
    """Return the maximum additional ETF allocation that keeps every cap satisfied."""
    if requested_amount < 0 or portfolio_value <= 0:
        raise ValueError("requested amount must be non-negative and portfolio value positive")
    if not isclose(sum(constituent_weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-4):
        raise ValueError("constituent weights must sum to 1")
    industry_weights: defaultdict[str, Decimal] = defaultdict(Decimal)
    for security, weight in constituent_weights.items():
        if weight < 0:
            raise ValueError(f"negative constituent weight for {security}")
        industry = security_industries.get(security)
        if not industry:
            raise ValueError(f"missing industry classification for {security}")
        industry_weights[industry] += Decimal(str(weight))

    maximum = requested_amount
    for industry, cap in industry_caps.items():
        if cap < 0 or cap > 1:
            raise ValueError(f"industry cap for {industry} must be between 0 and 1")
        weight = industry_weights.get(industry, Decimal("0"))
        if weight == 0:
            continue
        remaining_capacity = cap * portfolio_value - current_industry_values.get(
            industry, Decimal("0")
        )
        if remaining_capacity <= 0:
            return Decimal("0")
        maximum = min(maximum, remaining_capacity / weight)
    return max(Decimal("0"), maximum)
