from decimal import Decimal

from etf_backtesting.portfolio.cash_pool import (
    BuySignal,
    CashPoolAllocator,
    IndustryExposureContext,
)


def test_cash_pool_prioritizes_deeper_bollinger_deviation_and_keeps_reserve() -> None:
    signals = [
        BuySignal("510300", -0.05, Decimal("500"), Decimal("0"), Decimal("1000")),
        BuySignal("510880", -0.20, Decimal("500"), Decimal("0"), Decimal("1000")),
    ]
    result = CashPoolAllocator().allocate(Decimal("800"), Decimal("200"), signals)
    assert result[0].symbol == "510880"
    assert result[0].allocated_cash == Decimal("500")
    assert result[1].allocated_cash == Decimal("100")
    assert sum(item.allocated_cash for item in result) == Decimal("600")


def test_cash_pool_respects_per_etf_cap() -> None:
    signal = BuySignal("510300", -0.1, Decimal("500"), Decimal("900"), Decimal("1000"))
    result = CashPoolAllocator().allocate(Decimal("1000"), Decimal("0"), [signal])
    assert result[0].allocated_cash == Decimal("100")



def test_cash_pool_enforces_industry_caps_before_allocation() -> None:
    context = IndustryExposureContext(
        portfolio_value=Decimal("1000"),
        current_industry_values={"Technology": Decimal("100")},
        etf_constituent_weights={"510300": {"A": 0.5, "B": 0.5}},
        security_industries={"A": "Technology", "B": "Finance"},
        industry_caps={"Technology": Decimal("0.15")},
    )
    signal = BuySignal("510300", -0.2, Decimal("500"), Decimal("0"), Decimal("1000"))
    result = CashPoolAllocator().allocate(
        Decimal("500"), Decimal("0"), [signal], industry_context=context
    )
    assert result[0].allocated_cash == Decimal("100")
    assert result[0].reason == "INDUSTRY_CAP_LIMIT"

def test_cash_pool_blocks_new_buys_when_market_value_is_already_above_cap() -> None:
    signal = BuySignal("510300", -0.2, Decimal("500"), Decimal("1200"), Decimal("1000"))
    result = CashPoolAllocator().allocate(Decimal("1000"), Decimal("0"), [signal])
    assert result[0].allocated_cash == Decimal("0")
    assert result[0].reason == "CAP_OR_CASH_LIMIT"
\n