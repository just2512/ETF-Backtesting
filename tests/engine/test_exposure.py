from decimal import Decimal

import pytest

from etf_backtesting.portfolio.exposure import check_industry_exposure


def test_industry_exposure_passes_when_below_cap() -> None:
    violations = check_industry_exposure(
        Decimal("1000"),
        {"Technology": Decimal("100")},
        {"510300": Decimal("100")},
        {"510300": {"A": 0.6, "B": 0.4}},
        {"A": "Technology", "B": "Finance"},
        {"Technology": Decimal("0.2"), "Finance": Decimal("0.2")},
    )
    assert violations == []


def test_industry_exposure_rejects_cap_breach() -> None:
    violations = check_industry_exposure(
        Decimal("1000"),
        {"Technology": Decimal("100")},
        {"510300": Decimal("100")},
        {"510300": {"A": 0.6, "B": 0.4}},
        {"A": "Technology", "B": "Finance"},
        {"Technology": Decimal("0.12")},
    )
    assert len(violations) == 1
    assert violations[0].projected_fraction == Decimal("0.16")


def test_industry_exposure_blocks_missing_lookthrough() -> None:
    with pytest.raises(ValueError, match="missing industry"):
        check_industry_exposure(
            Decimal("1000"), {}, {"510300": Decimal("100")},
            {"510300": {"A": 1.0}}, {}, {"Technology": Decimal("0.2")}
        )
