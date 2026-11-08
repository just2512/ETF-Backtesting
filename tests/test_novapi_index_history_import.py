from __future__ import annotations

from scripts.export_novapi_index_history import load_tracking_indices, weight_contract


def test_tracking_index_names_are_read_from_the_project_universe():
    indices = load_tracking_indices()
    assert indices == {
        "510300": "沪深300指数",
        "510880": "上证红利指数",
        "513020": "中证港股通科技指数",
        "159928": "中证主要消费指数",
        "159611": "中证全指电力公用事业指数",
    }


def test_weight_contract_detects_fraction_units_without_normalizing():
    raw = {"stocks": ["A", "B"], "weights": {"A": "0.4", "B": "0.6"}}
    assert weight_contract(raw) == ("code", "weight", "fraction")


def test_weight_contract_detects_percent_units_without_normalizing():
    raw = {"stocks": ["A", "B"], "weights": {"A": "40", "B": "60"}}
    assert weight_contract(raw) == ("code", "weight", "percent")


def test_weight_contract_rejects_incomplete_or_unknown_totals():
    raw = {"stocks": ["A", "B"], "weights": {"A": "0.4", "B": "0.5"}}
    try:
        weight_contract(raw)
    except ValueError as exc:
        assert "refusing to infer units or normalize" in str(exc)
    else:
        raise AssertionError("incomplete weights must not be accepted")
